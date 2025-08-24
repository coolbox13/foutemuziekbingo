"""
Bingo Card Routes Module

This module handles bingo card generation, validation, and download functionality.
All endpoints require authentication and implement standardized error handling.
"""

from fastapi import APIRouter, HTTPException, Request, Depends
from fastapi.responses import StreamingResponse
from app.state import game_state
from app.pdf_generator import generate_pdf
from app.auth_service import get_current_user
from app.models import User
from app.error_handlers import ErrorResponse, ErrorMessages
import random
from io import BytesIO
import logging
from datetime import datetime, timezone

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

        # Get request data
        data = await request.json()
        num_cards = int(data.get("num_cards", 1))

        if num_cards < 1 or num_cards > 10:
            raise ErrorResponse.bad_request(
                "Invalid number of cards",
                details="Number of cards must be between 1 and 10"
            )

        # Check if there are enough unplayed tracks
        unplayed_tracks = game_state.get_unplayed_tracks()
        if len(unplayed_tracks) < 25:
            raise ErrorResponse.bad_request(
                ErrorMessages.INSUFFICIENT_TRACKS,
                details=f"Only {len(unplayed_tracks)} tracks available, need at least 25"
            )

        # Generate the cards
        cards = []
        for i in range(num_cards):
            # Create unique card with random selection
            selected_tracks = random.sample(unplayed_tracks, 25)
            card = {
                "id": f"card_{current_user.id}_{len(game_state.cards) + i}",
                "user_id": current_user.id,
                "tracks": selected_tracks,
                "matches": [],
                "created_at": datetime.utcnow().isoformat()
            }
            cards.append(card)

        # Store cards in game state
        game_state.cards.extend(cards)
        game_state.save_to_file()

        logger.info(
            f"[CARD-GEN-001] Generated {len(cards)} cards for user {current_user.id}",
            extra={
                "user_id": current_user.id,
                "card_count": len(cards),
                "total_cards": len(game_state.cards)
            }
        )

        return {"success": True, "cards": cards, "total_cards": len(cards)}

    except HTTPException:
        raise
    except ValueError as e:
        logger.error(
            f"[CARD-ERROR] Invalid card generation request from user {current_user.id}",
            extra={"user_id": current_user.id, "error": str(e)}
        )
        raise ErrorResponse.bad_request(
            "Invalid number of cards",
            details=str(e)
        )
    except Exception as e:
        logger.error(
            f"[CARD-ERROR] Unexpected error generating cards for user {current_user.id}",
            extra={"user_id": current_user.id, "error": str(e)},
            exc_info=True
        )
        raise ErrorResponse.internal_server_error(
            "Failed to generate bingo cards",
            error=e,
            operation="generate cards"
        )


@router.get("/api/get_cards")
async def api_get_cards(current_user: User = Depends(get_current_user)):
    """Get all bingo cards for the current user - requires authentication."""
    try:
        user_cards = [card for card in game_state.cards if card.get("user_id") == current_user.id]

        logger.debug(
            f"[CARD-GET-001] Retrieved {len(user_cards)} cards for user {current_user.id}",
            extra={"user_id": current_user.id, "card_count": len(user_cards)}
        )

        return {"cards": user_cards}

    except Exception as e:
        logger.error(
            f"[CARD-ERROR] Error getting cards for user {current_user.id}",
            extra={"user_id": current_user.id, "error": str(e)},
            exc_info=True
        )
        raise ErrorResponse.internal_server_error(
            "Failed to retrieve bingo cards",
            error=e,
            operation="get cards"
        )


@router.get("/api/check_card/{card_id}")
async def api_check_card(card_id: str, current_user: User = Depends(get_current_user)):
    """Check specific card status - requires authentication."""
    try:
        # Find the card
        card = None
        for c in game_state.cards:
            if c.get("id") == card_id and c.get("user_id") == current_user.id:
                card = c
                break

        if not card:
            raise ErrorResponse.not_found(
                "Bingo card",
                card_id
            )

        # Check for bingo
        played_tracks = game_state.get_played_tracks()
        has_bingo = check_bingo_status(card, played_tracks)

        logger.debug(
            f"[CARD-CHECK-001] Checked card {card_id} for user {current_user.id}",
            extra={
                "user_id": current_user.id,
                "card_id": card_id,
                "has_bingo": has_bingo,
                "matches": len(card.get("matches", []))
            }
        )

        return {
            "card": card,
            "bingo": has_bingo,
            "played_tracks": played_tracks,
            "matches": len(card.get("matches", []))
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"[CARD-ERROR] Error checking card {card_id} for user {current_user.id}",
            extra={"user_id": current_user.id, "card_id": card_id, "error": str(e)},
            exc_info=True
        )
        raise ErrorResponse.internal_server_error(
            "Failed to check bingo card status",
            error=e,
            operation="check card"
        )


@router.get("/api/download_cards_pd")
async def api_download_cards_pdf(current_user: User = Depends(get_current_user)):
    """Download bingo cards as PDF - requires authentication."""
    try:
        # Get user's cards
        user_cards = [card for card in game_state.cards if card.get("user_id") == current_user.id]

        if not user_cards:
            raise ErrorResponse.not_found(
                "Bingo cards",
                details="No cards found for current user. Please generate cards first."
            )

        # Generate PDF
        pdf_buffer = generate_pdf(user_cards)

        logger.info(
            f"[CARD-PDF-001] Generated PDF for {len(user_cards)} cards for user {current_user.id}",
            extra={
                "user_id": current_user.id,
                "card_count": len(user_cards)
            }
        )

        return StreamingResponse(
            BytesIO(pdf_buffer),
            media_type="application/pd",
            headers={"Content-Disposition": "attachment; filename=bingo_cards.pdf"}
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"[CARD-ERROR] Error generating PDF for user {current_user.id}",
            extra={"user_id": current_user.id, "error": str(e)},
            exc_info=True
        )
        raise ErrorResponse.internal_server_error(
            "Failed to generate PDF",
            error=e,
            operation="download cards PDF"
        )
