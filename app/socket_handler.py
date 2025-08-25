import os
import socketio
from app.state import game_state
import logging
from app.secure_session import get_session_from_cookie_value, SESSION_COOKIE_NAME
from app.auth_service import AuthService, AuthenticationError

# Create Socket.IO server with restricted CORS
_allowed_origins_env = os.getenv("ALLOWED_ORIGINS", "http://localhost:1313")
_allowed_origins = [o.strip() for o in _allowed_origins_env.split(",") if o.strip()]

# Optional Dragonfly (Redis protocol) manager for multi-process scaling and reliable broadcasts
_dragonfly_url = os.getenv("DRAGONFLY_URL", "")
client_manager = None
if _dragonfly_url:
    try:
        # Convert dragonfly:// to redis:// scheme for compatibility
        redis_url = _dragonfly_url.replace("dragonfly://", "redis://", 1) if _dragonfly_url.startswith("dragonfly://") else _dragonfly_url
        client_manager = socketio.AsyncRedisManager(redis_url)
        logger = logging.getLogger("music_bingo")
        logger.info("[SIO] Using Dragonfly manager", extra={"original_url": _dragonfly_url, "redis_url": redis_url})
    except Exception as e:
        logger = logging.getLogger("music_bingo")
        logger.warning(
            "[SIO] Failed to init Dragonfly manager, falling back to in-memory",
            extra={"error": str(e), "url": _dragonfly_url},
        )

sio = socketio.AsyncServer(
    cors_allowed_origins=_allowed_origins,
    async_mode="asgi",
    client_manager=client_manager,
)
sio_app = socketio.ASGIApp(sio)

logger = logging.getLogger("music_bingo")
auth_service = AuthService()


def check_bingo_status(card_id):
    """Check if a card has achieved bingo."""
    state = game_state.get_state()
    card = state["cards"].get(card_id)
    if not card:
        return False
    matches = card.get("matches", [])
    # Check rows
    for row in range(5):
        if all(pos in matches for pos in range(row * 5, (row + 1) * 5)):
            return True
    # Check columns
    for col in range(5):
        if all(pos in matches for pos in range(col, 25, 5)):
            return True
    return False


@sio.event
async def connect(sid, environ):
    """Handle client connection with proper authentication and error logging."""
    # Expect Authorization: Bearer <token> header OR session cookie
    scope = environ.get("asgi.scope") or {}
    headers = {}
    for k, v in scope.get("headers", []):
        try:
            headers[k.decode()] = v.decode()
        except (UnicodeDecodeError, AttributeError) as e:
            logger.debug(f"[SIO] Failed to decode header {k}: {e}")
            continue

    token = None
    auth_header = headers.get("authorization")
    if auth_header and auth_header.lower().startswith("bearer "):
        token = auth_header.split(" ", 1)[1]
    # Do not use ?token= for browser clients; rely on cookie as fallback
    # As a last resort, accept our secure session cookie
    if not token:
        cookie_header = headers.get("cookie", "")
        cookies = {}
        for part in cookie_header.split(";"):
            if "=" in part:
                k, v = part.strip().split("=", 1)
                cookies[k] = v
        raw_cookie = cookies.get(SESSION_COOKIE_NAME)
        if raw_cookie:
            try:
                from app.config import get_config

                config = get_config()
                session_data = await get_session_from_cookie_value(raw_cookie, config.secret_key)
                if (
                    session_data
                    and session_data.get("user")
                    and session_data["user"].get("id")
                ):
                    await sio.save_session(sid, {"user_id": session_data["user"]["id"]})
                    logger.info(
                        "[SIO] Client connected via secure session cookie",
                        extra={"user_id": session_data["user"]["id"]},
                    )
                    await sio.emit(
                        "connection_status", {"status": "connected"}, room=sid
                    )
                    return
            except Exception as e:
                logger.warning(f"[SIO-AUTH] Session cookie validation failed: {e}")

    if not token:
        logger.warning("[SIO-AUTH] Missing token on connect; rejecting")
        return False  # Reject connection

    try:
        user = await auth_service.get_current_user(token)
        await sio.save_session(sid, {"user_id": user.id})
        logger.info("[SIO] Client connected", extra={"user_id": user.id})
        await sio.emit("connection_status", {"status": "connected"}, room=sid)
    except AuthenticationError as e:
        logger.warning(
            "[SIO-AUTH] Invalid token on connect; rejecting", extra={"error": e.message}
        )
        return False
    except Exception as e:
        logger.error(f"[SIO-AUTH] Unexpected error during authentication: {e}", exc_info=True)
        return False


@sio.event
async def disconnect(sid):
    """Handle client disconnection with proper logging."""
    try:
        session = await sio.get_session(sid)
        user_id = session.get("user_id") if session else None
        logger.info(
            "[SIO] WebSocket client disconnected",
            extra={"session_id": sid, "user_id": user_id}
        )
    except Exception as e:
        logger.warning(f"[SIO] Error during disconnect handling: {e}")


@sio.event
async def card_validated(sid, data):
    """Handle card validation event with proper error handling."""
    try:
        session = await sio.get_session(sid)
        if not session or not session.get("user_id"):
            logger.warning("[SIO] Unauthorized card_validated request", extra={"session_id": sid})
            await sio.emit("error", {"error": "Unauthorized"}, room=sid)
            return

        card_id = data.get("card_id")
        if not card_id:
            logger.warning("[SIO] card_validated request missing card_id", extra={"session_id": sid})
            await sio.emit("error", {"error": "No card ID provided"}, room=sid)
            return

        state = game_state.get_state()
        card = state["cards"].get(card_id)
        if card:
            await sio.emit(
                "card_status_update",
                {
                    "card_id": card_id,
                    "status": card.get("bingo_status", "Not checked"),
                    "matches": card.get("matches", []),
                },
                room=sid,
            )
            logger.debug(f"[SIO] Card status updated for {card_id}", extra={"session_id": sid})
        else:
            logger.warning(f"[SIO] Card {card_id} not found", extra={"session_id": sid})
    except Exception as e:
        logger.error(f"[SIO] Error in card_validated: {e}", exc_info=True)
        await sio.emit("error", {"error": "Internal server error"}, room=sid)


@sio.event
async def check_bingo(sid, data):
    """Handle bingo check event with proper error handling."""
    try:
        session = await sio.get_session(sid)
        if not session or not session.get("user_id"):
            logger.warning("[SIO] Unauthorized check_bingo request", extra={"session_id": sid})
            await sio.emit("bingo_result", {"error": "Unauthorized"}, room=sid)
            return

        card_id = data.get("card_id")
        if not card_id:
            logger.warning("[SIO] check_bingo request missing card_id", extra={"session_id": sid})
            await sio.emit("bingo_result", {"error": "No card ID provided"}, room=sid)
            return

        result = check_bingo_status(card_id)
        await sio.emit("bingo_result", {"card_id": card_id, "result": result}, room=sid)
        logger.info(f"[SIO] Bingo check completed for {card_id}: {result}", extra={"session_id": sid})
    except Exception as e:
        logger.error(f"[SIO] Error in check_bingo: {e}", exc_info=True)
        await sio.emit("bingo_result", {"error": "Internal server error"}, room=sid)


@sio.event
async def track_played(sid, track_data):
    """Handle track played event with proper error handling."""
    try:
        session = await sio.get_session(sid)
        if not session or not session.get("user_id"):
            logger.warning("[SIO] Unauthorized track_played request", extra={"session_id": sid})
            await sio.emit("error", {"error": "Unauthorized"}, room=sid)
            return

        if not track_data:
            logger.warning("[SIO] track_played request missing track_data", extra={"session_id": sid})
            await sio.emit("error", {"error": "No track data provided"}, room=sid)
            return

        logger.info(f"[SIO] Track played: {track_data.get('name', 'unknown')}",
                    extra={"session_id": sid, "track_id": track_data.get("id")})
        await sio.emit("new_track", track_data)
    except Exception as e:
        logger.error(f"[SIO] Error in track_played: {e}", exc_info=True)
        await sio.emit("error", {"error": "Internal server error"}, room=sid)


@sio.event
async def join(sid, data):
    """Handle room join event with proper error handling."""
    try:
        session = await sio.get_session(sid)
        if not session or not session.get("user_id"):
            logger.warning("[SIO] Unauthorized join request", extra={"session_id": sid})
            await sio.emit("error", {"error": "Unauthorized"}, room=sid)
            return

        room = data.get("room")
        if room:
            await sio.enter_room(sid, room)
            logger.info(f"[SIO] Client joined room: {room}", extra={"session_id": sid})
            await sio.emit("room_joined", {"room": room}, room=room)
        else:
            logger.warning("[SIO] join request missing room", extra={"session_id": sid})
            await sio.emit("error", {"error": "No room specified"}, room=sid)
    except Exception as e:
        logger.error(f"[SIO] Error in join: {e}", exc_info=True)
        await sio.emit("error", {"error": "Internal server error"}, room=sid)


@sio.event
async def leave(sid, data):
    """Handle room leave event with proper error handling."""
    try:
        session = await sio.get_session(sid)
        if not session or not session.get("user_id"):
            logger.warning("[SIO] Unauthorized leave request", extra={"session_id": sid})
            await sio.emit("error", {"error": "Unauthorized"}, room=sid)
            return

        room = data.get("room")
        if room:
            await sio.leave_room(sid, room)
            logger.info(f"[SIO] Client left room: {room}", extra={"session_id": sid})
            await sio.emit("room_left", {"room": room}, room=room)
        else:
            logger.warning("[SIO] leave request missing room", extra={"session_id": sid})
            await sio.emit("error", {"error": "No room specified"}, room=sid)
    except Exception as e:
        logger.error(f"[SIO] Error in leave: {e}", exc_info=True)
        await sio.emit("error", {"error": "Internal server error"}, room=sid)


@sio.event
async def request_game_state(sid, data=None):
    """Handle game state request with proper error handling."""
    try:
        session = await sio.get_session(sid)
        if not session or not session.get("user_id"):
            logger.warning("[SIO] Unauthorized request_game_state", extra={"session_id": sid})
            await sio.emit("error", {"error": "Unauthorized"}, room=sid)
            return

        state = game_state.get_state()
        await sio.emit("game_state", state, room=sid)
        logger.debug("[SIO] Game state sent", extra={"session_id": sid})
    except Exception as e:
        logger.error(f"[SIO] Error in request_game_state: {e}", exc_info=True)
        await sio.emit("error", {"error": "Internal server error"}, room=sid)


@sio.event
async def play_track(sid, data):
    """Handle play track event with proper error handling."""
    try:
        session = await sio.get_session(sid)
        if not session or not session.get("user_id"):
            logger.warning("[SIO] Unauthorized play_track request", extra={"session_id": sid})
            await sio.emit("error", {"error": "Unauthorized"}, room=sid)
            return

        track_id = data.get("track_id")
        if not track_id:
            logger.warning("[SIO] play_track request missing track_id", extra={"session_id": sid})
            await sio.emit("error", {"error": "No track ID provided"}, room=sid)
            return

        logger.info(f"[SIO] Requested to play track: {track_id}", extra={"session_id": sid})
        state = game_state.get_state()
        track = next((t for t in state["unplayed_tracks"] if t["id"] == track_id), None)
        if track:
            def update_track_lists(state):
                if track in state["unplayed_tracks"]:
                    state["unplayed_tracks"].remove(track)
                state["played_tracks"].append(track)

            game_state.update_state(update_track_lists)
            await sio.emit("track_played", {"track_id": track_id, "track": track}, room=sid)
            logger.info(f"[SIO] Track {track_id} moved to played", extra={"session_id": sid})
        else:
            logger.warning(f"[SIO] Track {track_id} not found in unplayed tracks", extra={"session_id": sid})
            await sio.emit(
                "error", {"error": "Track not found in unplayed tracks"}, room=sid
            )
    except Exception as e:
        logger.error(f"[SIO] Error in play_track: {e}", exc_info=True)
        await sio.emit("error", {"error": "Internal server error"}, room=sid)
