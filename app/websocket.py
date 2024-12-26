# First, let's set up WebSocket support for real-time updates
# websocket.py
from flask_socketio import SocketIO, emit
from app.state import GAME_STATE

socketio = SocketIO()


def init_websocket(app):
    socketio.init_app(app, cors_allowed_origins="*")

    @socketio.on("connect")
    def handle_connect():
        emit("game_state", GAME_STATE)

    @socketio.on("card_update")
    def handle_card_update(data):
        card_id = data.get("card_id")
        if card_id in GAME_STATE["cards"]:
            emit(
                "card_status",
                {"card_id": card_id, "status": GAME_STATE["cards"][card_id]},
                broadcast=True,
            )

    @socketio.on("track_played")
    def handle_track_played(track_data):
        emit("new_track", track_data, broadcast=True)
