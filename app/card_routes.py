from flask import Blueprint, jsonify, request, send_file
from app.state import game_state
from app.utils import generate_bingo_cards
from app.pdf_generator import generate_pdf
import random
import uuid
from io import BytesIO

bp = Blueprint("card", __name__)


def check_bingo_status(card, played_tracks):
    """Check if a card has a bingo condition."""
    matches = card.get("matches", [])

    # Check rows
    for row in range(5):
        row_positions = range(row * 5, (row + 1) * 5)
        if all(pos in matches for pos in row_positions):
            return True

    # Check columns
    for col in range(5):
        col_positions = range(col, 25, 5)
        if all(pos in matches for pos in col_positions):
            return True

    return False


@bp.route("/api/generate_cards", methods=["POST"])
def api_generate_cards():
    """Generate new bingo cards."""
    try:
        data = request.json
        num_cards = int(data.get("num_cards"))

        state = game_state.get_state()
        if len(state.get("unplayed_tracks", [])) < 25:
            return jsonify({"error": "Not enough unplayed tracks"}), 400

        def create_cards(state):
            state["cards"] = {}
            for _ in range(num_cards):
                card_id = str(uuid.uuid4())[:8]
                state["cards"][card_id] = {
                    "tracks": random.sample(state["unplayed_tracks"], 25),
                    "bingo_status": "Not checked",
                    "matches": [],
                }
            return state["cards"]

        new_cards = game_state.update_state(create_cards)
        return jsonify({"message": f"Generated {num_cards} cards", "cards": new_cards})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/get_cards", methods=["GET"])
def api_get_cards():
    """Get all current bingo cards."""
    try:
        state = game_state.get_state()
        return jsonify({"cards": state.get("cards", {})})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/check_card/<card_id>", methods=["GET"])
def api_check_card(card_id):
    """Check a specific card for matches and bingo."""
    try:
        state = game_state.get_state()

        if card_id not in state["cards"]:
            return jsonify({"error": "Invalid card ID"}), 404

        def update_card_status(state):
            card = state["cards"][card_id]
            played_tracks = state.get("played_tracks", [])

            # Update matches
            matches = []
            for position, track in enumerate(card["tracks"]):
                if any(pt["id"] == track["id"] for pt in played_tracks):
                    matches.append(position)

            card["matches"] = matches
            has_bingo = check_bingo_status(card, played_tracks)
            card["bingo_status"] = "BINGO!" if has_bingo else "No bingo yet"

            return {
                "card_id": card_id,
                "status": card["bingo_status"],
                "matches": matches,
                "has_bingo": has_bingo
            }

        result = game_state.update_state(update_card_status)
        return jsonify(result)
    except Exception as e:
        current_app.logger.error(f"Error checking card {card_id}: {e}")
        return jsonify({"error": str(e)}), 500


@bp.route("/api/download_cards_pdf", methods=["GET"])
def api_download_cards_pdf():
    """Generate and download PDF version of all cards."""
    try:
        state = game_state.get_state()
        cards = state.get("cards", {})

        if not cards:
            return jsonify({"error": "No cards available"}), 404

        pdf_data = generate_pdf(cards)
        return send_file(
            BytesIO(pdf_data),
            mimetype="application/pdf",
            as_attachment=True,
            download_name="bingo_cards.pdf",
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500
