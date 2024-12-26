from app import socketio
from flask_socketio import emit, join_room, leave_room
from flask import current_app
from app.state import game_state


@socketio.on("connect", namespace="/")
def handle_connect(auth):
    if current_app:
        current_app.logger.info("WebSocket client connected.")
    print("Client connected")
    emit("connection_status", {"status": "connected"}, namespace="/")


@socketio.on("disconnect", namespace="/")
def handle_disconnect():
    if current_app:
        current_app.logger.info("WebSocket client disconnected.")
    print("Client disconnected")


@socketio.on("card_validated", namespace="/")
def handle_card_validation(data):
    card_id = data.get("card_id")
    if not card_id:
        emit("error", {"error": "No card ID provided"}, namespace="/")
        return

    state = game_state.get_state()
    card = state["cards"].get(card_id)
    if card:
        emit(
            "card_status_update",
            {
                "card_id": card_id,
                "status": card.get("bingo_status", "Not checked"),
                "matches": card.get("matches", []),
            },
            namespace="/",
        )


@socketio.on("check_bingo", namespace="/")
def handle_check_bingo(data):
    card_id = data.get("card_id")
    if not card_id:
        emit("bingo_result", {"error": "No card ID provided"}, namespace="/")
        return

    result = check_bingo_status(card_id)  # Assuming a helper function exists
    emit("bingo_result", {"card_id": card_id, "result": result}, namespace="/")


@socketio.on("track_played", namespace="/")
def handle_track_played(track_data):
    if not track_data:
        emit("error", {"error": "No track data provided"}, namespace="/")
        return

    if current_app:
        current_app.logger.info(f"Track played: {track_data}")
    emit("new_track", track_data, namespace="/")


@socketio.on("join")
def handle_join(data):
    room = data.get("room")
    if room:
        join_room(room)
        if current_app:
            current_app.logger.info(f"Client joined room: {room}")
        emit("room_joined", {"room": room}, room=room)
    else:
        emit("error", {"error": "No room specified"}, namespace="/")


@socketio.on("leave")
def handle_leave(data):
    room = data.get("room")
    if room:
        leave_room(room)
        if current_app:
            current_app.logger.info(f"Client left room: {room}")
        emit("room_left", {"room": room}, room=room)
    else:
        emit("error", {"error": "No room specified"}, namespace="/")


@socketio.on("request_game_state")
def handle_request_game_state():
    state = game_state.get_state()
    emit("game_state", state)


@socketio.on("play_track")
def handle_play_track(data):
    track_id = data.get("track_id")
    if not track_id:
        emit("error", {"error": "No track ID provided"}, namespace="/")
        return

    if current_app:
        current_app.logger.info(f"Requested to play track: {track_id}")

    # Placeholder for actual playback handling logic
    success = play_track_by_id(track_id)  # Assuming a helper function exists

    if success:
        emit("track_played", {"track_id": track_id}, namespace="/")
    else:
        emit("error", {"error": "Failed to play track"}, namespace="/")


# Helper functions (placeholders for actual logic)
def check_bingo_status(card_id):
    # Implement your bingo checking logic here
    return True  # Placeholder


def play_track_by_id(track_id):
    # Implement your track playback logic here
    return True  # Placeholder
