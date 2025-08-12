from fastapi import APIRouter, HTTPException, Request
import json
import os
from datetime import datetime
from app.state import game_state
import logging

router = APIRouter()
logger = logging.getLogger("music_bingo")

SAVED_GAMES_DIR = "saved_games"


def ensure_saved_games_dir():
    if not os.path.exists(SAVED_GAMES_DIR):
        os.makedirs(SAVED_GAMES_DIR)


@router.post("/api/save_game")
async def save_game(request: Request):
    """Save current game state with a name and description."""
    try:
        data = await request.json()
        game_name = data.get("name")
        description = data.get("description", "")

        if not game_name:
            raise HTTPException(status_code=400, detail="Game name is required")

        ensure_saved_games_dir()
        current_state = game_state.get_state()

        save_data = {
            "name": game_name,
            "description": description,
            "timestamp": datetime.now().isoformat(),
            "game_state": current_state,
        }

        filename = f"{game_name.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        filepath = os.path.join(SAVED_GAMES_DIR, filename)

        with open(filepath, "w") as f:
            json.dump(save_data, f, indent=4)

        return {"message": "Game saved successfully", "filename": filename}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error saving game: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/load_game/{filename}")
async def load_game(filename: str):
    """Load a saved game state."""
    try:
        filepath = os.path.join(SAVED_GAMES_DIR, filename)

        if not os.path.exists(filepath):
            raise HTTPException(status_code=404, detail="Saved game not found")

        with open(filepath, "r") as f:
            save_data = json.load(f)

        def update_state(state):
            loaded_state = save_data["game_state"]
            state.update(loaded_state)

        game_state.update_state(update_state)

        return {
            "message": "Game loaded successfully",
            "game_info": {
                "name": save_data["name"],
                "description": save_data["description"],
                "timestamp": save_data["timestamp"],
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error loading game {filename}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/list_saved_games")
async def list_saved_games():
    """Get list of all saved games."""
    try:
        ensure_saved_games_dir()
        saved_games = []

        for filename in os.listdir(SAVED_GAMES_DIR):
            if filename.endswith(".json"):
                filepath = os.path.join(SAVED_GAMES_DIR, filename)
                with open(filepath, "r") as f:
                    save_data = json.load(f)
                    saved_games.append(
                        {
                            "filename": filename,
                            "name": save_data["name"],
                            "description": save_data["description"],
                            "timestamp": save_data["timestamp"],
                        }
                    )

        return {
            "saved_games": sorted(
                saved_games, key=lambda x: x["timestamp"], reverse=True
            )
        }

    except Exception as e:
        logger.error(f"Error listing saved games: {e}")
        raise HTTPException(status_code=500, detail=str(e))
