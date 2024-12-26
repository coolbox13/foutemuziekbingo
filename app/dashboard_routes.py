from flask import Blueprint, render_template, current_app, jsonify
from app.card_status import summarize_card_statuses
from app.state import game_state

bp = Blueprint("dashboard", __name__)


def get_dashboard_data():
    """Get all necessary data for the dashboard."""
    state = game_state.get_state()
    cards = state.get("cards", {})
    played_tracks = state.get("played_tracks", [])

    return {
        "game_state": {
            "num_tracks": len(state.get("unplayed_tracks", [])),
            "played_tracks": len(played_tracks),
            "cards": len(cards),
            "current_playlist": state.get("current_playlist"),
            "bingo_mode": state.get("bingo_mode", "default"),
        },
        "card_summaries": summarize_card_statuses(cards, played_tracks),
    }


@bp.route("/", methods=["GET"])
def dashboard():
    """Render the main dashboard."""
    try:
        current_app.logger.info("Dashboard route accessed")
        dashboard_data = get_dashboard_data()
        return render_template("dashboard.html", **dashboard_data)
    except Exception as e:
        current_app.logger.error(f"Error rendering dashboard: {e}")
        return render_template(
            "error.html", error_message="Failed to load dashboard. Please try again."
        )


@bp.route("/api/dashboard_data", methods=["GET"])
def api_dashboard_data():
    """Get current dashboard data via API."""
    try:
        dashboard_data = get_dashboard_data()
        return jsonify(dashboard_data)
    except Exception as e:
        current_app.logger.error(f"Error getting dashboard data: {e}")
        return jsonify({"error": str(e)}), 500


@bp.route("/api/dashboard_stats", methods=["GET"])
def api_dashboard_stats():
    """Get current game statistics."""
    try:
        state = game_state.get_state()
        cards = state.get("cards", {})

        # Calculate statistics
        stats = {
            "total_tracks": len(state.get("unplayed_tracks", []))
            + len(state.get("played_tracks", [])),
            "played_tracks": len(state.get("played_tracks", [])),
            "remaining_tracks": len(state.get("unplayed_tracks", [])),
            "total_cards": len(cards),
            "cards_with_matches": sum(
                1 for card in cards.values() if card.get("matches")
            ),
            "bingos": sum(
                1 for card in cards.values() if card.get("bingo_status") == "BINGO!"
            ),
        }

        return jsonify(stats)
    except Exception as e:
        current_app.logger.error(f"Error getting dashboard stats: {e}")
        return jsonify({"error": str(e)}), 500
