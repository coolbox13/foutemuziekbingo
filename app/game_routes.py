"""
Game Routes Module

This module handles all game-related endpoints for the Musical Bingo application.
It provides comprehensive game management functionality including game creation,
player management, game state control, and real-time bingo card interaction.

Key Features:
- Complete game lifecycle management (create, join, start, end)
- Multi-player game support with real-time Socket.IO integration
- Bingo card generation and track marking system
- Room code-based game joining for easy access
- Host-only controls for game management
- Comprehensive game state tracking and persistence

Security Features:
- JWT authentication required for all endpoints
- Host-only access control for game management actions
- Private game access validation
- Input validation for all game parameters
- Rate limiting via global middleware
- CSRF protection via global middleware

Real-time Features:
- Socket.IO integration for live game updates
- Real-time player join/leave notifications
- Live game start broadcasts
- Instant bingo card updates and validation
- Multi-client synchronization

Game States:
- WAITING: Game created, accepting players
- ACTIVE: Game in progress, tracks being played
- PAUSED: Temporarily paused by host
- COMPLETED: Game finished, winners declared

Routes:
- POST /api/games: Create new game
- GET /api/games: List user's games (with optional status filter)
- GET /api/games/{game_id}: Get specific game details
- POST /api/games/{game_id}/join: Join game by ID
- POST /api/games/join-by-code/{room_code}: Join game by room code
- POST /api/games/{game_id}/start: Start game (host only)
- POST /api/games/{game_id}/mark-track: Mark track on bingo card
- GET /api/games/{game_id}/card: Get user's bingo card

Error Handling:
- Standard HTTP status codes (200, 201, 400, 403, 404, 500)
- Structured error responses with user-friendly messages
- Comprehensive audit logging for game events
- Graceful error handling for game service failures
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from typing import List, Optional
import logging
from datetime import datetime, timezone
from app.models import (
    Game,
    GameCreate,
    GamePublic,
    GameStatus,
    User,
    APIResponse,
    BingoCard,
    GameValidationResult,
    GameValidationStatus,
    BulkGameValidationRequest,
    BulkGameValidationResponse,
    GameExistenceCheck,
)
from app.game_service import game_service, GameError
from app.socket_handler import sio
from app.auth_service import get_current_user

router = APIRouter()
logger = logging.getLogger("music_bingo")


@router.post("/api/games", response_model=Game)
async def create_game(
    game_data: GameCreate, current_user: User = Depends(get_current_user)
):
    """Create a new game"""
    try:
        game = await game_service.create_game(game_data, current_user)
        logger.info(
            "[GAME-API-001] Game created successfully",
            extra={
                "game_id": game.id,
                "user_id": current_user.id,
                "game_name": game.name,
            },
        )
        return game

    except GameError as e:
        logger.error(
            "[GAME-API-ERROR] Game creation failed",
            extra={"user_id": current_user.id, "error": e.message},
        )
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        logger.error(
            "[GAME-API-ERROR] Unexpected error creating game",
            extra={"user_id": current_user.id, "error": str(e)},
        )
        raise HTTPException(status_code=500, detail="Failed to create game")


@router.get("/api/games", response_model=List[GamePublic])
async def get_user_games(
    status: Optional[GameStatus] = None, current_user: User = Depends(get_current_user)
):
    """Get games for current user"""
    try:
        games = await game_service.get_user_games(current_user.id, status)
        logger.debug(
            "[GAME-API-002] Retrieved user games",
            extra={
                "user_id": current_user.id,
                "game_count": len(games),
                "status_filter": status.value if status else None,
            },
        )
        return games

    except Exception as e:
        logger.error(
            "[GAME-API-ERROR] Error getting user games",
            extra={"user_id": current_user.id, "error": str(e)},
        )
        raise HTTPException(status_code=500, detail="Failed to get games")


@router.get("/api/games/{game_id}", response_model=Game)
async def get_game(game_id: str, current_user: User = Depends(get_current_user)):
    """Get specific game details"""
    try:
        game = await game_service.get_game(
            game_id, include_playlist=True, include_players=True
        )
        if not game:
            raise HTTPException(status_code=404, detail="Game not found")

        # Check if user has access to this game
        user_has_access = game.host_id == current_user.id or any(
            player.id == current_user.id for player in game.players
        )

        if not user_has_access and game.is_private:
            raise HTTPException(status_code=403, detail="Access denied")

        logger.debug(
            "[GAME-API-003] Retrieved game details",
            extra={
                "game_id": game_id,
                "user_id": current_user.id,
                "game_name": game.name,
            },
        )
        return game

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "[GAME-API-ERROR] Error getting game",
            extra={"game_id": game_id, "user_id": current_user.id, "error": str(e)},
        )
        raise HTTPException(status_code=500, detail="Failed to get game")


@router.post("/api/games/{game_id}/join", response_model=Game)
async def join_game(game_id: str, current_user: User = Depends(get_current_user)):
    """Join a game"""
    try:
        game = await game_service.join_game(game_id, current_user)
        logger.info(
            "[GAME-API-004] User joined game",
            extra={
                "game_id": game_id,
                "user_id": current_user.id,
                "game_name": game.name,
            },
        )

        # Broadcast player joined via Socket.IO (to all clients)
        await sio.emit(
            "player_joined",
            {
                "game_id": game_id,
                "user": {
                    "id": current_user.id,
                    "display_name": current_user.display_name,
                    "avatar_url": current_user.avatar_url,
                },
                "total_players": len(game.players),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

        return game

    except GameError as e:
        logger.error(
            "[GAME-API-ERROR] Failed to join game",
            extra={"game_id": game_id, "user_id": current_user.id, "error": e.message},
        )
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        logger.error(
            "[GAME-API-ERROR] Unexpected error joining game",
            extra={"game_id": game_id, "user_id": current_user.id, "error": str(e)},
        )
        raise HTTPException(status_code=500, detail="Failed to join game")


@router.post("/api/games/join-by-code/{room_code}", response_model=Game)
async def join_game_by_code(
    room_code: str, current_user: User = Depends(get_current_user)
):
    """Join a game by room code"""
    try:
        # Find game by room code
        game = await game_service.get_game_by_room_code(room_code)
        if not game:
            raise HTTPException(
                status_code=404, detail="Game not found with that room code"
            )

        # Join the game
        joined_game = await game_service.join_game(game.id, current_user)
        logger.info(
            "[GAME-API-005] User joined game by room code",
            extra={
                "room_code": room_code,
                "game_id": game.id,
                "user_id": current_user.id,
            },
        )
        return joined_game

    except HTTPException:
        raise
    except GameError as e:
        logger.error(
            "[GAME-API-ERROR] Failed to join game by code",
            extra={
                "room_code": room_code,
                "user_id": current_user.id,
                "error": e.message,
            },
        )
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        logger.error(
            "[GAME-API-ERROR] Unexpected error joining game by code",
            extra={"room_code": room_code, "user_id": current_user.id, "error": str(e)},
        )
        raise HTTPException(status_code=500, detail="Failed to join game")


@router.post("/api/games/{game_id}/start", response_model=Game)
async def start_game(game_id: str, current_user: User = Depends(get_current_user)):
    """Start a game (host only)"""
    try:
        game = await game_service.start_game(game_id, current_user)
        logger.info(
            "[GAME-API-006] Game started",
            extra={
                "game_id": game_id,
                "host_user_id": current_user.id,
                "game_name": game.name,
            },
        )

        # Broadcast game started via Socket.IO (to all clients)
        await sio.emit(
            "game_started",
            {
                "game": {"id": game.id, "name": game.name, "status": game.status.value},
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

        return game

    except GameError as e:
        logger.error(
            "[GAME-API-ERROR] Failed to start game",
            extra={"game_id": game_id, "user_id": current_user.id, "error": e.message},
        )
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        logger.error(
            "[GAME-API-ERROR] Unexpected error starting game",
            extra={"game_id": game_id, "user_id": current_user.id, "error": str(e)},
        )
        raise HTTPException(status_code=500, detail="Failed to start game")


@router.post("/api/games/{game_id}/mark-track", response_model=APIResponse)
async def mark_track(
    game_id: str, track_id: str, current_user: User = Depends(get_current_user)
):
    """Mark a track on user's bingo card"""
    try:
        result = await game_service.mark_track(game_id, current_user.id, track_id)

        logger.debug(
            "[GAME-API-007] Track marked",
            extra={
                "game_id": game_id,
                "user_id": current_user.id,
                "track_id": track_id,
                "marked": result["marked"],
                "bingo": result["bingo"],
            },
        )

        return APIResponse(
            success=True,
            message="Track marked successfully"
            + (" - BINGO!" if result["bingo"] else ""),
            data=result,
        )

    except GameError as e:
        logger.error(
            "[GAME-API-ERROR] Failed to mark track",
            extra={
                "game_id": game_id,
                "user_id": current_user.id,
                "track_id": track_id,
                "error": e.message,
            },
        )
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        logger.error(
            "[GAME-API-ERROR] Unexpected error marking track",
            extra={
                "game_id": game_id,
                "user_id": current_user.id,
                "track_id": track_id,
                "error": str(e),
            },
        )
        raise HTTPException(status_code=500, detail="Failed to mark track")


@router.get("/api/games/{game_id}/card", response_model=BingoCard)
async def get_user_bingo_card(
    game_id: str, current_user: User = Depends(get_current_user)
):
    """Get user's bingo card for a game"""
    try:
        from app.database import database

        cards = await database.query_records(
            "bingo_cards", filters={"game_id": game_id, "user_id": current_user.id}
        )

        if not cards:
            raise HTTPException(status_code=404, detail="Bingo card not found")

        card = BingoCard(**cards[0])

        logger.debug(
            "[GAME-API-008] Retrieved user bingo card",
            extra={"game_id": game_id, "user_id": current_user.id, "card_id": card.id},
        )

        return card

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "[GAME-API-ERROR] Error getting bingo card",
            extra={"game_id": game_id, "user_id": current_user.id, "error": str(e)},
        )
        raise HTTPException(status_code=500, detail="Failed to get bingo card")


# Legacy new_round endpoint removed

@router.get("/api/games/validate", response_model=List[GameValidationResult])
async def validate_games(
    game_ids: str = Query(..., description="Comma-separated list of game IDs to validate"),
    include_track_count: bool = Query(default=True, description="Include track count in validation"),
    filter_status: Optional[GameStatus] = Query(default=None, description="Optional status filter"),
    current_user: User = Depends(get_current_user)
):
    """
    Validate multiple games for existence, accessibility, and readiness.

    This endpoint replaces the frontend validation loops that were causing API storms.
    It efficiently validates multiple games in a single database operation.

    Args:
        game_ids: Comma-separated string of game IDs (max 100)
        include_track_count: Whether to include playlist track counts
        filter_status: Optional filter by game status
        current_user: Authenticated user

    Returns:
        List of GameValidationResult objects with detailed validation status

    Raises:
        HTTPException: 400 for invalid input, 500 for server errors
    """
    try:
        # Parse and validate game IDs
        game_id_list = [gid.strip() for gid in game_ids.split(",") if gid.strip()]

        if not game_id_list:
            raise HTTPException(status_code=400, detail="No game IDs provided")

        if len(game_id_list) > 100:
            raise HTTPException(
                status_code=400,
                detail="Too many game IDs (maximum 100 allowed)"
            )

        # Validate games using the game service
        results = []
        for game_id in game_id_list:
            result = await game_service.validate_game(
                game_id=game_id,
                user_id=current_user.id,
                include_track_count=include_track_count
            )

            # Apply status filter if specified
            if filter_status is None or (
                result.exists and
                result.status == GameValidationStatus.VALID
            ):
                results.append(result)

        logger.info(
            "[GAME-VALIDATE-API-001] Games validation completed",
            extra={
                "user_id": current_user.id,
                "requested_count": len(game_id_list),
                "returned_count": len(results),
                "filter_status": filter_status.value if filter_status else None
            }
        )

        return results

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "[GAME-VALIDATE-API-ERROR] Error in games validation endpoint",
            extra={
                "user_id": current_user.id,
                "error": str(e),
                "game_ids_count": len(game_id_list) if 'game_id_list' in locals() else 0
            }
        )
        raise HTTPException(status_code=500, detail="Failed to validate games")


@router.post("/api/games/validate-batch", response_model=BulkGameValidationResponse)
async def validate_games_batch(
    request: BulkGameValidationRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Efficient bulk validation of multiple games in a single operation.

    This endpoint is optimized for performance and replaces individual validation calls
    that were causing API storms. It uses bulk database queries to minimize latency.

    Args:
        request: BulkGameValidationRequest with game IDs and options
        current_user: Authenticated user

    Returns:
        BulkGameValidationResponse with comprehensive validation results and performance metrics

    Raises:
        HTTPException: 400 for invalid input, 500 for server errors
    """
    try:
        # Validate request
        if not request.game_ids:
            raise HTTPException(status_code=400, detail="No game IDs provided")

        if len(request.game_ids) > 100:
            raise HTTPException(
                status_code=400,
                detail="Too many game IDs (maximum 100 allowed)"
            )

        # Perform bulk validation
        response = await game_service.validate_games_bulk(
            game_ids=request.game_ids,
            user_id=current_user.id,
            include_track_count=request.include_track_count,
            filter_status=request.filter_status
        )

        logger.info(
            "[GAME-BULK-VALIDATE-API-001] Bulk validation completed",
            extra={
                "user_id": current_user.id,
                "requested_count": len(request.game_ids),
                "processed_count": response.total_processed,
                "processing_time_ms": response.processing_time_ms,
                "success_rate": (response.summary.get("valid", 0) / response.total_processed * 100)
                              if response.total_processed > 0 else 0
            }
        )

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "[GAME-BULK-VALIDATE-API-ERROR] Error in bulk validation endpoint",
            extra={
                "user_id": current_user.id,
                "error": str(e),
                "requested_game_count": len(request.game_ids) if request and request.game_ids else 0
            }
        )
        raise HTTPException(status_code=500, detail="Failed to perform bulk validation")


@router.get("/api/games/{game_id}/exists", response_model=GameExistenceCheck)
async def check_game_existence(
    game_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    Quick check for game existence and user access.

    This is a lightweight endpoint for checking if a game exists and if the user
    can access it, without performing full validation.

    Args:
        game_id: Game ID to check
        current_user: Authenticated user

    Returns:
        GameExistenceCheck with basic existence and accessibility info

    Raises:
        HTTPException: 500 for server errors
    """
    try:
        result = await game_service.check_game_existence(
            game_id=game_id,
            user_id=current_user.id
        )

        logger.debug(
            "[GAME-EXISTENCE-API-001] Game existence check completed",
            extra={
                "game_id": game_id,
                "user_id": current_user.id,
                "exists": result.exists,
                "accessible": result.accessible
            }
        )

        return result

    except Exception as e:
        logger.error(
            "[GAME-EXISTENCE-API-ERROR] Error checking game existence",
            extra={"game_id": game_id, "user_id": current_user.id, "error": str(e)}
        )
        raise HTTPException(status_code=500, detail="Failed to check game existence")
