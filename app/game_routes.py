from flask import Blueprint, jsonify, current_app
from app.state import game_state

bp = Blueprint("game", __name__)


@bp.route("/api/new_round", methods=["POST"])
def api_new_round():
    """Start a new round by resetting the game state."""
    try:
        game_state.reset_to_default()
        return jsonify({"message": "New round started"})
    except Exception as e:
        current_app.logger.error(f"Error starting new round: {e}")
        return jsonify({"error": str(e)}), 500
