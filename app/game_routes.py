from fastapi import APIRouter, HTTPException
from app.state import game_state
import logging

router = APIRouter()
logger = logging.getLogger("music_bingo")


@router.post("/api/new_round")
async def api_new_round():
    """Start a new round by resetting the game state."""
    try:
        game_state.reset_to_default()
        return {"message": "New round started"}

    except Exception as e:
        logger.error(f"Error starting new round: {e}")
        raise HTTPException(status_code=500, detail=str(e))
