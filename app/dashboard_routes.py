from flask import Blueprint, render_template, current_app
from app.card_status import summarize_card_statuses
from app.state import game_state

bp = Blueprint("dashboard", __name__)


@bp.route("/", methods=["GET"])
def dashboard():
    """Render the dashboard with game and card statuses."""
    current_app.logger.info("Dashboard route accessed.")

    # Fetch the game state
    state = game_state.get_state()

    # Summarize card statuses
    cards = state.get("cards", {})
    played_tracks = state.get("played_tracks", [])
    card_summaries = summarize_card_statuses(cards, played_tracks)

    # Render the dashboard template
    return render_template(
        "dashboard.html",
        game_state={
            "num_tracks": len(state.get("unplayed_tracks", [])),
            "cards": cards,
            "bingo_mode": state.get("bingo_mode", "default"),
        },
        card_summaries=card_summaries,
    )
