from fastapi import APIRouter, HTTPException, Request, Depends
import json
import os
from datetime import datetime
from app.state import game_state
from app.auth_service import get_current_user
from app.models import User
import logging

router = APIRouter()
logger = logging.getLogger("music_bingo")

SAVED_GAMES_DIR = "saved_games"


def ensure_saved_games_dir():
    if not os.path.exists(SAVED_GAMES_DIR):
        os.makedirs(SAVED_GAMES_DIR)


@router.post("/api/save_game")
async def save_game(request: Request, current_user: User = Depends(get_current_user)):
    """Save current game state with a name and description - requires authentication."""
    try:
        logger.info(
            f"[GAME-SAVE-AUTH-001] User {current_user.id} saving game",
            extra={"user_id": current_user.id, "spotify_id": current_user.spotify_id}
        )
        
        data = await request.json()
        game_name = data.get("name")
        description = data.get("description", "")

        if not game_name:
            logger.warning(
                f"[GAME-SAVE-AUTH-002] Missing game name for user {current_user.id}",
                extra={"user_id": current_user.id}
            )
            raise HTTPException(status_code=400, detail="Game name is required")

        ensure_saved_games_dir()
        current_state = game_state.get_state()

        save_data = {
            "name": game_name,
            "description": description,
            "timestamp": datetime.now().isoformat(),
            "saved_by": current_user.id,  # Track who saved the game
            "saved_by_spotify_id": current_user.spotify_id,
            "saved_by_display_name": current_user.display_name,
            "game_state": current_state,
        }

        filename = f"{game_name.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        filepath = os.path.join(SAVED_GAMES_DIR, filename)

        with open(filepath, "w") as f:
            json.dump(save_data, f, indent=4)

        logger.info(
            f"[GAME-SAVE-AUTH-003] Game saved successfully",
            extra={
                "user_id": current_user.id, 
                "game_name": game_name, 
                "game_filename": filename,
                "state_size": len(str(current_state))
            }
        )

        return {"message": "Game saved successfully", "filename": filename}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"[GAME-SAVE-AUTH-ERROR] Error saving game for user {current_user.id}: {e}",
            extra={"user_id": current_user.id, "error": str(e)}
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/load_game/{filename}")
async def load_game(filename: str, current_user: User = Depends(get_current_user)):
    """Load a saved game state - requires authentication."""
    try:
        logger.info(
            f"[GAME-LOAD-AUTH-001] User {current_user.id} loading game {filename}",
            extra={"user_id": current_user.id, "game_filename": filename}
        )
        
        filepath = os.path.join(SAVED_GAMES_DIR, filename)

        if not os.path.exists(filepath):
            logger.warning(
                f"[GAME-LOAD-AUTH-002] Game file not found for user {current_user.id}: {filename}",
                extra={"user_id": current_user.id, "game_filename": filename}
            )
            raise HTTPException(status_code=404, detail="Saved game not found")

        with open(filepath, "r") as f:
            save_data = json.load(f)

        # Optional: Check if user has permission to load this game
        # For now, any authenticated user can load any saved game
        # In the future, could add ownership checks:
        # if save_data.get("saved_by") != current_user.id:
        #     raise HTTPException(status_code=403, detail="Access denied to this saved game")

        def update_state(state):
            loaded_state = save_data["game_state"]
            state.update(loaded_state)

        game_state.update_state(update_state)

        logger.info(
            f"[GAME-LOAD-AUTH-003] Game loaded successfully",
            extra={
                "user_id": current_user.id, 
                "game_filename": filename,
                "original_saver": save_data.get("saved_by", "unknown"),
                "game_name": save_data.get("name", "unknown")
            }
        )

        return {
            "message": "Game loaded successfully",
            "game_info": {
                "name": save_data["name"],
                "description": save_data["description"],
                "timestamp": save_data["timestamp"],
                "saved_by": save_data.get("saved_by_display_name", "Unknown user"),
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"[GAME-LOAD-AUTH-ERROR] Error loading game {filename} for user {current_user.id}: {e}",
            extra={"user_id": current_user.id, "game_filename": filename, "error": str(e)}
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/list_saved_games")
async def list_saved_games(current_user: User = Depends(get_current_user)):
    """Get list of all saved games - requires authentication."""
    try:
        logger.info(
            f"[GAME-LIST-AUTH-001] User {current_user.id} listing saved games",
            extra={"user_id": current_user.id}
        )
        
        ensure_saved_games_dir()
        saved_games = []

        for filename in os.listdir(SAVED_GAMES_DIR):
            if filename.endswith(".json"):
                try:
                    filepath = os.path.join(SAVED_GAMES_DIR, filename)
                    with open(filepath, "r") as f:
                        save_data = json.load(f)
                        saved_games.append(
                            {
                                "game_filename": filename,
                                "name": save_data["name"],
                                "description": save_data["description"],
                                "timestamp": save_data["timestamp"],
                                "saved_by": save_data.get("saved_by_display_name", "Unknown user"),
                            }
                        )
                except Exception as file_error:
                    logger.warning(
                        f"[GAME-LIST-AUTH-WARN] Skipping corrupted save file {filename}: {file_error}",
                        extra={"user_id": current_user.id, "game_filename": filename, "error": str(file_error)}
                    )
                    continue

        sorted_games = sorted(saved_games, key=lambda x: x["timestamp"], reverse=True)
        
        logger.info(
            f"[GAME-LIST-AUTH-002] Saved games listed successfully",
            extra={"user_id": current_user.id, "game_count": len(sorted_games)}
        )

        return {"saved_games": sorted_games}

    except Exception as e:
        logger.error(
            f"[GAME-LIST-AUTH-ERROR] Error listing saved games for user {current_user.id}: {e}",
            extra={"user_id": current_user.id, "error": str(e)}
        )
        raise HTTPException(status_code=500, detail=str(e))
