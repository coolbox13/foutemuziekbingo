from flask_socketio import SocketIO, emit, join_room, leave_room
from flask import current_app
from app.state import game_state
from app.helpers import handle_error

# Create SocketIO instance without app yet
socketio = SocketIO()

def init_socketio(app):
    """Initialize SocketIO with the app and configure event handlers."""
    socketio.init_app(app, cors_allowed_origins="*", logger=True, engineio_logger=True)

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

@socketio.on("connect")
def handle_connect():
    current_app.logger.info("WebSocket client connected.")
    print("Client connected")
    emit("connection_status", {"status": "connected"})

@socketio.on("disconnect")
def handle_disconnect():
    current_app.logger.info("WebSocket client disconnected.")
    print("Client disconnected")

@socketio.on("card_validated")
def handle_card_validation(data):
    card_id = data.get("card_id")
    if not card_id:
        emit("error", {"error": "No card ID provided"})
        return
    state = game_state.get_state()
    card = state["cards"].get(card_id)
    if card:
        emit("card_status_update", {
            "card_id": card_id,
            "status": card.get("bingo_status", "Not checked"),
            "matches": card.get("matches", []),
        })

@socketio.on("check_bingo")
def handle_check_bingo(data):
    card_id = data.get("card_id")
    if not card_id:
        emit("bingo_result", {"error": "No card ID provided"})
        return
    result = check_bingo_status(card_id)
    emit("bingo_result", {"card_id": card_id, "result": result})

@socketio.on("track_played")
def handle_track_played(track_data):
    if not track_data:
        emit("error", {"error": "No track data provided"})
        return
    current_app.logger.info(f"Track played: {track_data}")
    emit("new_track", track_data)

@socketio.on("join")
def handle_join(data):
    room = data.get("room")
    if room:
        join_room(room)
        current_app.logger.info(f"Client joined room: {room}")
        emit("room_joined", {"room": room}, room=room)
    else:
        emit("error", {"error": "No room specified"})

@socketio.on("leave")
def handle_leave(data):
    room = data.get("room")
    if room:
        leave_room(room)
        current_app.logger.info(f"Client left room: {room}")
        emit("room_left", {"room": room}, room=room)
    else:
        emit("error", {"error": "No room specified"})

@socketio.on("request_game_state")
def handle_request_game_state():
    state = game_state.get_state()
    emit("game_state", state)

@socketio.on("play_track")
def handle_play_track(data):
    track_id = data.get("track_id")
    if not track_id:
        emit("error", {"error": "No track ID provided"})
        return
    current_app.logger.info(f"Requested to play track: {track_id}")
    state = game_state.get_state()
    track = next((t for t in state["unplayed_tracks"] if t["id"] == track_id), None)
    if track:
        def update_track_lists(state):
            if track in state["unplayed_tracks"]:
                state["unplayed_tracks"].remove(track)
            state["played_tracks"].append(track)
        game_state.update_state(update_track_lists)
        emit("track_played", {"track_id": track_id, "track": track})
    else:
        emit("error", {"error": "Track not found in unplayed tracks"})
