from flask import Blueprint, jsonify, request, send_file
from app.state import ThreadSafeGameState
from app.utils import generate_bingo_cards
from app.card_status import validate_card
from app.pdf_generator import generate_pdf
import random
import uuid
from io import BytesIO


def check_bingo_status(card, played_tracks):
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


bp = Blueprint("card", __name__)
game_state = ThreadSafeGameState()


@bp.route("/api/generate_cards", methods=["POST"])
def api_generate_cards():
    data = request.json
    num_cards = int(data.get("num_cards"))  # Remove default

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
            }
        return state["cards"]

    new_cards = game_state.update_state(create_cards)
    return jsonify({"message": f"Generated {num_cards} cards", "cards": new_cards})


@bp.route("/api/get_cards", methods=["GET"])
def api_get_cards():
    state = game_state.get_state()
    return jsonify({"cards": state.get("cards", {})})


@bp.route("/api/check_card/<card_id>", methods=["GET"])
def api_check_card(card_id):
    state = game_state.get_state()
    card = state["cards"].get(card_id)
    played_tracks = state.get("played_tracks", [])

    if not card:
        return jsonify({"error": "Invalid card ID"}), 404

    matches = []
    for position, track in enumerate(card["tracks"]):
        if any(pt["id"] == track["id"] for pt in played_tracks):
            matches.append(position)

    card["matches"] = matches
    game_state.save_state(state)

    has_bingo = check_bingo_status(card, played_tracks)
    card["bingo_status"] = "BINGO!" if has_bingo else "No bingo yet"

    return jsonify(
        {"status": card["bingo_status"], "matches": matches, "has_bingo": has_bingo}
    )


@bp.route("/api/download_cards_pdf", methods=["GET"])
def api_download_cards_pdf():
    try:
        state = game_state.get_state()
        cards = state.get("cards", {})
        if not cards:
            return jsonify({"error": "No cards available"}), 404

        print(f"Cards data: {cards}")  # Debug log
        pdf_data = generate_pdf(cards)
        return send_file(
            BytesIO(pdf_data),
            mimetype="application/pdf",
            as_attachment=True,
            download_name="bingo_cards.pdf",
        )
    except Exception as e:
        print(f"PDF generation error: {str(e)}")  # Debug log
        return jsonify({"error": str(e)}), 500
