import socketio
from app.state import game_state
import logging

# Create Socket.IO server
sio = socketio.AsyncServer(cors_allowed_origins="*", async_mode='asgi')
sio_app = socketio.ASGIApp(sio)

logger = logging.getLogger("music_bingo")


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
    logger.info("WebSocket client connected.")
    print("Client connected")
    await sio.emit("connection_status", {"status": "connected"}, room=sid)


@sio.event
async def disconnect(sid):
    logger.info("WebSocket client disconnected.")
    print("Client disconnected")


@sio.event
async def card_validated(sid, data):
    card_id = data.get("card_id")
    if not card_id:
        await sio.emit("error", {"error": "No card ID provided"}, room=sid)
        return
    state = game_state.get_state()
    card = state["cards"].get(card_id)
    if card:
        await sio.emit("card_status_update", {
            "card_id": card_id,
            "status": card.get("bingo_status", "Not checked"),
            "matches": card.get("matches", []),
        }, room=sid)


@sio.event
async def check_bingo(sid, data):
    card_id = data.get("card_id")
    if not card_id:
        await sio.emit("bingo_result", {"error": "No card ID provided"}, room=sid)
        return
    result = check_bingo_status(card_id)
    await sio.emit("bingo_result", {"card_id": card_id, "result": result}, room=sid)


@sio.event
async def track_played(sid, track_data):
    if not track_data:
        await sio.emit("error", {"error": "No track data provided"}, room=sid)
        return
    logger.info(f"Track played: {track_data}")
    await sio.emit("new_track", track_data)


@sio.event
async def join(sid, data):
    room = data.get("room")
    if room:
        await sio.enter_room(sid, room)
        logger.info(f"Client joined room: {room}")
        await sio.emit("room_joined", {"room": room}, room=room)
    else:
        await sio.emit("error", {"error": "No room specified"}, room=sid)


@sio.event
async def leave(sid, data):
    room = data.get("room")
    if room:
        await sio.leave_room(sid, room)
        logger.info(f"Client left room: {room}")
        await sio.emit("room_left", {"room": room}, room=room)
    else:
        await sio.emit("error", {"error": "No room specified"}, room=sid)


@sio.event
async def request_game_state(sid):
    state = game_state.get_state()
    await sio.emit("game_state", state, room=sid)


@sio.event
async def play_track(sid, data):
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
        await sio.emit("error", {"error": "Track not found in unplayed tracks"}, room=sid)
