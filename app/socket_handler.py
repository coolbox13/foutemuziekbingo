import os
import socketio
from app.state import game_state
import logging
from urllib.parse import parse_qs
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
        client_manager = socketio.AsyncRedisManager(_dragonfly_url)
        logger = logging.getLogger("music_bingo")
        logger.info("[SIO] Using Dragonfly manager", extra={"url": _dragonfly_url})
    except Exception as e:
        logger = logging.getLogger("music_bingo")
        logger.warning(
            "[SIO] Failed to init Dragonfly manager, falling back to in-memory",
            extra={"error": str(e)},
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
    # Expect Authorization: Bearer <token> header OR session cookie
    scope = environ.get("asgi.scope") or {}
    headers = {}
    for k, v in scope.get("headers", []):
        try:
            headers[k.decode()] = v.decode()
        except Exception:
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
                from app.auth_routes import SECRET_KEY

                session_data = get_session_from_cookie_value(raw_cookie, SECRET_KEY)
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
            except Exception:
                pass

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


@sio.event
async def disconnect(sid):
    logger.info("WebSocket client disconnected.")


@sio.event
async def card_validated(sid, data):
    session = await sio.get_session(sid)
    if not session or not session.get("user_id"):
        await sio.emit("error", {"error": "Unauthorized"}, room=sid)
        return
    card_id = data.get("card_id")
    if not card_id:
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


@sio.event
async def check_bingo(sid, data):
    session = await sio.get_session(sid)
    if not session or not session.get("user_id"):
        await sio.emit("bingo_result", {"error": "Unauthorized"}, room=sid)
        return
    card_id = data.get("card_id")
    if not card_id:
        await sio.emit("bingo_result", {"error": "No card ID provided"}, room=sid)
        return
    result = check_bingo_status(card_id)
    await sio.emit("bingo_result", {"card_id": card_id, "result": result}, room=sid)


@sio.event
async def track_played(sid, track_data):
    session = await sio.get_session(sid)
    if not session or not session.get("user_id"):
        await sio.emit("error", {"error": "Unauthorized"}, room=sid)
        return
    if not track_data:
        await sio.emit("error", {"error": "No track data provided"}, room=sid)
        return
    logger.info(f"Track played: {track_data}")
    await sio.emit("new_track", track_data)


@sio.event
async def join(sid, data):
    session = await sio.get_session(sid)
    if not session or not session.get("user_id"):
        await sio.emit("error", {"error": "Unauthorized"}, room=sid)
        return
    room = data.get("room")
    if room:
        await sio.enter_room(sid, room)
        logger.info(f"Client joined room: {room}")
        await sio.emit("room_joined", {"room": room}, room=room)
    else:
        await sio.emit("error", {"error": "No room specified"}, room=sid)


@sio.event
async def leave(sid, data):
    session = await sio.get_session(sid)
    if not session or not session.get("user_id"):
        await sio.emit("error", {"error": "Unauthorized"}, room=sid)
        return
    room = data.get("room")
    if room:
        await sio.leave_room(sid, room)
        logger.info(f"Client left room: {room}")
        await sio.emit("room_left", {"room": room}, room=room)
    else:
        await sio.emit("error", {"error": "No room specified"}, room=sid)


@sio.event
async def request_game_state(sid):
    session = await sio.get_session(sid)
    if not session or not session.get("user_id"):
        await sio.emit("error", {"error": "Unauthorized"}, room=sid)
        return
    state = game_state.get_state()
    await sio.emit("game_state", state, room=sid)


@sio.event
async def play_track(sid, data):
    session = await sio.get_session(sid)
    if not session or not session.get("user_id"):
        await sio.emit("error", {"error": "Unauthorized"}, room=sid)
        return
    track_id = data.get("track_id")
    if not track_id:
        await sio.emit("error", {"error": "No track ID provided"}, room=sid)
        return
    logger.info(f"Requested to play track: {track_id}")
    state = game_state.get_state()
    track = next((t for t in state["unplayed_tracks"] if t["id"] == track_id), None)
    if track:

        def update_track_lists(state):
            if track in state["unplayed_tracks"]:
                state["unplayed_tracks"].remove(track)
            state["played_tracks"].append(track)

        game_state.update_state(update_track_lists)
        await sio.emit("track_played", {"track_id": track_id, "track": track}, room=sid)
    else:
        await sio.emit(
            "error", {"error": "Track not found in unplayed tracks"}, room=sid
        )
