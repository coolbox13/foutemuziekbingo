from fastapi import APIRouter, HTTPException, Request, Depends
from fastapi.responses import StreamingResponse
from app.state import game_state
from app.pdf_generator import generate_pdf
from app.auth_service import get_current_user
from app.models import User
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
async def api_generate_cards(request: Request, current_user: User = Depends(get_current_user)):
    """Generate new bingo cards - requires authentication."""
    try:
        logger.info(
            f"[CARD-AUTH-001] User {current_user.id} generating cards",
            extra={"user_id": current_user.id, "spotify_id": current_user.spotify_id}
        )

        data = await request.json()
        num_cards = int(data.get("num_cards"))
        state = game_state.get_state()

        unplayed_tracks = state.get("unplayed_tracks", [])
        if len(unplayed_tracks) < 25:
            logger.warning(
                f"[CARD-AUTH-002] Insufficient tracks for user {current_user.id}",
                extra={
                    "user_id": current_user.id, 
                    "track_count": len(unplayed_tracks),
                    "has_playlist_loaded": len(unplayed_tracks) > 0
                }
            )
            if len(unplayed_tracks) == 0:
                raise HTTPException(
                    status_code=400, 
                    detail="No playlist loaded. Please select a playlist first before generating cards."
                )
            else:
                raise HTTPException(
                    status_code=400, 
                    detail=f"Not enough tracks. Need at least 25 tracks, but only {len(unplayed_tracks)} available."
                )

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
                    "created_by": current_user.id,  # Track who created the card
                }
            return state["cards"]

        new_cards = game_state.update_state(create_cards)

        logger.info(
            "[CARD-AUTH-003] Cards generated successfully",
            extra={"user_id": current_user.id, "num_cards": num_cards, "card_ids": list(new_cards.keys())}
        )

        return {"message": f"Generated {num_cards} cards", "cards": new_cards}

    except ValueError as e:
        logger.error(
            f"[CARD-AUTH-ERROR] Invalid number of cards requested by user {current_user.id}: {e}",
            extra={"user_id": current_user.id, "error": str(e)}
        )
        raise HTTPException(status_code=400, detail="Invalid number of cards")
    except Exception as e:
        logger.error(
            f"[CARD-AUTH-ERROR] Error generating cards for user {current_user.id}: {e}",
            extra={"user_id": current_user.id, "error": str(e)}
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/get_cards")
async def api_get_cards(current_user: User = Depends(get_current_user)):
    """Get all current bingo cards - requires authentication."""
    try:
        logger.info(
            f"[CARD-AUTH-004] User {current_user.id} retrieving cards",
            extra={"user_id": current_user.id}
        )

        state = game_state.get_state()
        cards = state.get("cards", {})

        logger.info(
            "[CARD-AUTH-005] Cards retrieved successfully",
            extra={"user_id": current_user.id, "card_count": len(cards)}
        )

        return {"cards": cards}
    except Exception as e:
        logger.error(
            f"[CARD-AUTH-ERROR] Error getting cards for user {current_user.id}: {e}",
            extra={"user_id": current_user.id, "error": str(e)}
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/check_card/{card_id}")
async def api_check_card(card_id: str, current_user: User = Depends(get_current_user)):
    """Check a specific card for matches and bingo - requires authentication."""
    try:
        logger.info(
            f"[CARD-AUTH-006] User {current_user.id} checking card {card_id}",
            extra={"user_id": current_user.id, "card_id": card_id}
        )

        state = game_state.get_state()
        if card_id not in state["cards"]:
            logger.warning(
                f"[CARD-AUTH-007] Invalid card ID {card_id} for user {current_user.id}",
                extra={"user_id": current_user.id, "card_id": card_id}
            )
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
                "has_bingo": has_bingo,
            }

        result = game_state.update_state(update_card_status)

        logger.info(
            "[CARD-AUTH-008] Card checked successfully",
            extra={
                "user_id": current_user.id,
                "card_id": card_id,
                "has_bingo": result.get("has_bingo", False),
                "match_count": len(result.get("matches", []))
            }
        )

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"[CARD-AUTH-ERROR] Error checking card {card_id} for user {current_user.id}: {e}",
            extra={"user_id": current_user.id, "card_id": card_id, "error": str(e)}
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/download_cards_pd")
async def api_download_cards_pdf(current_user: User = Depends(get_current_user)):
    """Generate and download PDF version of all cards - requires authentication."""
    try:
        logger.info(
            f"[CARD-AUTH-009] User {current_user.id} downloading cards PDF",
            extra={"user_id": current_user.id}
        )

        state = game_state.get_state()
        cards = state.get("cards", {})

        if not cards:
            logger.warning(
                f"[CARD-AUTH-010] No cards available for PDF download for user {current_user.id}",
                extra={"user_id": current_user.id}
            )
            raise HTTPException(status_code=404, detail="No cards available")

        pdf_data = generate_pdf(cards)

        logger.info(
            "[CARD-AUTH-011] PDF generated successfully",
            extra={"user_id": current_user.id, "pdf_size": len(pdf_data)}
        )

        return StreamingResponse(
            BytesIO(pdf_data),
            media_type="application/pd",
            headers={"Content-Disposition": "attachment; filename=bingo_cards.pdf"},
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"[CARD-AUTH-ERROR] Error generating PDF for user {current_user.id}: {e}",
            extra={"user_id": current_user.id, "error": str(e)}
        )
        raise HTTPException(status_code=500, detail=str(e))
