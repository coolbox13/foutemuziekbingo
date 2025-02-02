from flask import Blueprint, jsonify, current_app
from app.state import game_state
from app.helpers import handle_error

bp = Blueprint("game", __name__)

@bp.route("/api/new_round", methods=["POST"])
def api_new_round():
    """Start a new round by resetting the game state."""
    try:
        game_state.reset_to_default()
        return jsonify({"message": "New round started"})
    except Exception as e:
        return handle_error(e)
