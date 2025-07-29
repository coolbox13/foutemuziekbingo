from fastapi import APIRouter, Request, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from app.card_status import summarize_card_statuses
from app.state import game_state
import logging

router = APIRouter()
logger = logging.getLogger("music_bingo")
templates = Jinja2Templates(directory="templates")


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


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Render the main dashboard."""
    try:
        logger.info("Dashboard route accessed")
        dashboard_data = get_dashboard_data()
        return templates.TemplateResponse("dashboard.html", {
            "request": request,
            **dashboard_data
        })
    except Exception as e:
        logger.error(f"Error rendering dashboard: {e}")
        return templates.TemplateResponse("error.html", {
            "request": request,
            "error_message": "Failed to load dashboard. Please try again."
        })


@router.get("/api/dashboard_data")
async def api_dashboard_data():
    """Get current dashboard data via API."""
    try:
        dashboard_data = get_dashboard_data()
        return dashboard_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/dashboard_stats")
async def api_dashboard_stats():
    """Get current game statistics."""
    try:
        state = game_state.get_state()
        cards = state.get("cards", {})
        stats = {
            "total_tracks": (len(state.get("unplayed_tracks", [])) +
                             len(state.get("played_tracks", []))),
            "played_tracks": len(state.get("played_tracks", [])),
            "remaining_tracks": len(state.get("unplayed_tracks", [])),
            "total_cards": len(cards),
            "cards_with_matches": sum(1 for card in cards.values() if card.get("matches")),
            "bingos": sum(1 for card in cards.values() if card.get("bingo_status") == "BINGO!")
        }
        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
