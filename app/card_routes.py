from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from app.state import game_state
from app.pdf_generator import generate_pdf
import random
from io import BytesIO
import logging

router = APIRouter()
logger = logging.getLogger("music_bingo")


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

    # Check diagonal (top-left to bottom-right)
    diagonal1_positions = [0, 6, 12, 18, 24]
    if all(pos in matches for pos in diagonal1_positions):
        return True

    # Check diagonal (top-right to bottom-left)
    diagonal2_positions = [4, 8, 12, 16, 20]
    if all(pos in matches for pos in diagonal2_positions):
        return True

    return False


@router.post("/api/generate_cards")
async def api_generate_cards(request: Request):
    """Generate new bingo cards."""
    try:
        data = await request.json()
        num_cards = int(data.get("num_cards"))
        state = game_state.get_state()

        if len(state.get("unplayed_tracks", [])) < 25:
            raise HTTPException(status_code=400, detail="Not enough unplayed tracks")

        def create_cards(state):
            state["cards"] = {}
            used_ids = set()
            for _ in range(num_cards):
                while True:
                    card_id = str(random.randint(100, 999))
                    if card_id not in used_ids:
                        used_ids.add(card_id)
                        break
                state["cards"][card_id] = {
                    "tracks": random.sample(state["unplayed_tracks"], 25),
                    "bingo_status": "Not checked",
                    "matches": [],
                }
            return state["cards"]

        new_cards = game_state.update_state(create_cards)
        return {"message": f"Generated {num_cards} cards", "cards": new_cards}

    except ValueError as e:
        logger.error(f"Invalid number of cards requested: {e}")
        raise HTTPException(status_code=400, detail="Invalid number of cards")
    except Exception as e:
        logger.error(f"Error generating cards: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/get_cards")
async def api_get_cards():
    """Get all current bingo cards."""
    try:
        state = game_state.get_state()
        return {"cards": state.get("cards", {})}
    except Exception as e:
        logger.error(f"Error getting cards: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/check_card/{card_id}")
async def api_check_card(card_id: str):
    """Check a specific card for matches and bingo."""
    try:
        state = game_state.get_state()
        if card_id not in state["cards"]:
            raise HTTPException(status_code=404, detail="Invalid card ID")

        def update_card_status(state):
            card = state["cards"][card_id]
            played_tracks = state.get("played_tracks", [])
            matches = []

            # Check each position on the card against played tracks
            for position, track in enumerate(card["tracks"]):
                if any(pt["id"] == track["id"] for pt in played_tracks):
                    matches.append(position)

            card["matches"] = matches
            has_bingo = check_bingo_status(card, played_tracks)
            card["bingo_status"] = "BINGO!" if has_bingo else "No bingo"

            return {
                "card_id": card_id,
                "status": card["bingo_status"],
                "matches": matches,
                "has_bingo": has_bingo
            }

        result = game_state.update_state(update_card_status)
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error checking card {card_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/download_cards_pdf")
async def api_download_cards_pdf():
    """Generate and download PDF version of all cards."""
    try:
        state = game_state.get_state()
        cards = state.get("cards", {})

        if not cards:
            raise HTTPException(status_code=404, detail="No cards available")

        pdf_data = generate_pdf(cards)

        return StreamingResponse(
            BytesIO(pdf_data),
            media_type="application/pdf",
            headers={"Content-Disposition": "attachment; filename=bingo_cards.pdf"}
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating PDF: {e}")
        raise HTTPException(status_code=500, detail=str(e))
