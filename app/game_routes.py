from fastapi import APIRouter, HTTPException, Depends, Request
from typing import List, Optional
import logging
from datetime import datetime, timezone
from app.models import (
    Game, GameCreate, GameUpdate, GamePublic, GameStatus,
    User, UserPublic, APIResponse, BingoCard, Track
)
from app.auth_service import get_current_user
from app.game_service import game_service, GameError
from app.playlist_service import playlist_service
from app.spotify import get_spotify_client
from app.websocket_service import ws_manager

router = APIRouter()
logger = logging.getLogger("music_bingo")


@router.post("/api/games", response_model=Game)
async def create_game(
    game_data: GameCreate,
    current_user: User = Depends(get_current_user)
):
    """Create a new game"""
    try:
        game = await game_service.create_game(game_data, current_user)
        logger.info(f"[GAME-API-001] Game created successfully", extra={
            "game_id": game.id,
            "user_id": current_user.id,
            "game_name": game.name
        })
        return game
        
    except GameError as e:
        logger.error(f"[GAME-API-ERROR] Game creation failed", extra={
            "user_id": current_user.id,
            "error": e.message
        })
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        logger.error(f"[GAME-API-ERROR] Unexpected error creating game", extra={
            "user_id": current_user.id,
            "error": str(e)
        })
        raise HTTPException(status_code=500, detail="Failed to create game")


@router.get("/api/games", response_model=List[GamePublic])
async def get_user_games(
    status: Optional[GameStatus] = None,
    current_user: User = Depends(get_current_user)
):
    """Get games for current user"""
    try:
        games = await game_service.get_user_games(current_user.id, status)
        logger.debug(f"[GAME-API-002] Retrieved user games", extra={
            "user_id": current_user.id,
            "game_count": len(games),
            "status_filter": status.value if status else None
        })
        return games
        
    except Exception as e:
        logger.error(f"[GAME-API-ERROR] Error getting user games", extra={
            "user_id": current_user.id,
            "error": str(e)
        })
        raise HTTPException(status_code=500, detail="Failed to get games")


@router.get("/api/games/{game_id}", response_model=Game)
async def get_game(
    game_id: str,
    current_user: User = Depends(get_current_user)
):
    """Get specific game details"""
    try:
        game = await game_service.get_game(game_id, include_playlist=True, include_players=True)
        if not game:
            raise HTTPException(status_code=404, detail="Game not found")
        
        # Check if user has access to this game
        user_has_access = (
            game.host_id == current_user.id or
            any(player.id == current_user.id for player in game.players)
        )
        
        if not user_has_access and game.is_private:
            raise HTTPException(status_code=403, detail="Access denied")
        
        logger.debug(f"[GAME-API-003] Retrieved game details", extra={
            "game_id": game_id,
            "user_id": current_user.id,
            "game_name": game.name
        })
        return game
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[GAME-API-ERROR] Error getting game", extra={
            "game_id": game_id,
            "user_id": current_user.id,
            "error": str(e)
        })
        raise HTTPException(status_code=500, detail="Failed to get game")


@router.post("/api/games/{game_id}/join", response_model=Game)
async def join_game(
    game_id: str,
    current_user: User = Depends(get_current_user)
):
    """Join a game"""
    try:
        game = await game_service.join_game(game_id, current_user)
        logger.info(f"[GAME-API-004] User joined game", extra={
            "game_id": game_id,
            "user_id": current_user.id,
            "game_name": game.name
        })
        
        # Broadcast player joined to WebSocket connections
        await ws_manager.broadcast_to_game(game_id, {
            "type": "player_joined",
            "user": {
                "id": current_user.id,
                "display_name": current_user.display_name,
                "avatar_url": current_user.avatar_url
            },
            "total_players": len(game.players),
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        
        return game
        
    except GameError as e:
        logger.error(f"[GAME-API-ERROR] Failed to join game", extra={
            "game_id": game_id,
            "user_id": current_user.id,
            "error": e.message
        })
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        logger.error(f"[GAME-API-ERROR] Unexpected error joining game", extra={
            "game_id": game_id,
            "user_id": current_user.id,
            "error": str(e)
        })
        raise HTTPException(status_code=500, detail="Failed to join game")


@router.post("/api/games/join-by-code/{room_code}", response_model=Game)
async def join_game_by_code(
    room_code: str,
    current_user: User = Depends(get_current_user)
):
    """Join a game by room code"""
    try:
        # Find game by room code
        game = await game_service.get_game_by_room_code(room_code)
        if not game:
            raise HTTPException(status_code=404, detail="Game not found with that room code")
        
        # Join the game
        joined_game = await game_service.join_game(game.id, current_user)
        logger.info(f"[GAME-API-005] User joined game by room code", extra={
            "room_code": room_code,
            "game_id": game.id,
            "user_id": current_user.id
        })
        return joined_game
        
    except HTTPException:
        raise
    except GameError as e:
        logger.error(f"[GAME-API-ERROR] Failed to join game by code", extra={
            "room_code": room_code,
            "user_id": current_user.id,
            "error": e.message
        })
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        logger.error(f"[GAME-API-ERROR] Unexpected error joining game by code", extra={
            "room_code": room_code,
            "user_id": current_user.id,
            "error": str(e)
        })
        raise HTTPException(status_code=500, detail="Failed to join game")


@router.post("/api/games/{game_id}/start", response_model=Game)
async def start_game(
    game_id: str,
    current_user: User = Depends(get_current_user)
):
    """Start a game (host only)"""
    try:
        game = await game_service.start_game(game_id, current_user)
        logger.info(f"[GAME-API-006] Game started", extra={
            "game_id": game_id,
            "host_user_id": current_user.id,
            "game_name": game.name
        })
        
        # Broadcast game started to WebSocket connections
        await ws_manager.broadcast_to_game(game_id, {
            "type": "game_started",
            "game": {
                "id": game.id,
                "name": game.name,
                "status": game.status.value
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        
        return game
        
    except GameError as e:
        logger.error(f"[GAME-API-ERROR] Failed to start game", extra={
            "game_id": game_id,
            "user_id": current_user.id,
            "error": e.message
        })
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        logger.error(f"[GAME-API-ERROR] Unexpected error starting game", extra={
            "game_id": game_id,
            "user_id": current_user.id,
            "error": str(e)
        })
        raise HTTPException(status_code=500, detail="Failed to start game")


@router.post("/api/games/{game_id}/mark-track", response_model=APIResponse)
async def mark_track(
    game_id: str,
    track_id: str,
    current_user: User = Depends(get_current_user)
):
    """Mark a track on user's bingo card"""
    try:
        result = await game_service.mark_track(game_id, current_user.id, track_id)
        
        logger.debug(f"[GAME-API-007] Track marked", extra={
            "game_id": game_id,
            "user_id": current_user.id,
            "track_id": track_id,
            "marked": result["marked"],
            "bingo": result["bingo"]
        })
        
        return APIResponse(
            success=True,
            message="Track marked successfully" + (" - BINGO!" if result["bingo"] else ""),
            data=result
        )
        
    except GameError as e:
        logger.error(f"[GAME-API-ERROR] Failed to mark track", extra={
            "game_id": game_id,
            "user_id": current_user.id,
            "track_id": track_id,
            "error": e.message
        })
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        logger.error(f"[GAME-API-ERROR] Unexpected error marking track", extra={
            "game_id": game_id,
            "user_id": current_user.id,
            "track_id": track_id,
            "error": str(e)
        })
        raise HTTPException(status_code=500, detail="Failed to mark track")


@router.get("/api/games/{game_id}/card", response_model=BingoCard)
async def get_user_bingo_card(
    game_id: str,
    current_user: User = Depends(get_current_user)
):
    """Get user's bingo card for a game"""
    try:
        from app.database import database
        
        cards = await database.query_records(
            "bingo_cards",
            filters={"game_id": game_id, "user_id": current_user.id}
        )
        
        if not cards:
            raise HTTPException(status_code=404, detail="Bingo card not found")
        
        card = BingoCard(**cards[0])
        
        logger.debug(f"[GAME-API-008] Retrieved user bingo card", extra={
            "game_id": game_id,
            "user_id": current_user.id,
            "card_id": card.id
        })
        
        return card
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[GAME-API-ERROR] Error getting bingo card", extra={
            "game_id": game_id,
            "user_id": current_user.id,
            "error": str(e)
        })
        raise HTTPException(status_code=500, detail="Failed to get bingo card")


# Legacy compatibility endpoint
@router.post("/api/new_round")
async def api_new_round(current_user: User = Depends(get_current_user)):
    """Legacy endpoint - Start a new round by resetting the game state."""
    logger.warning(f"[GAME-API-LEGACY] Legacy new_round endpoint called", extra={
        "user_id": current_user.id
    })
    
    return APIResponse(
        success=True,
        message="This endpoint is deprecated. Use /api/games to create new games."
    )
