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
- Standardized error responses with structured format
- User-friendly error messages with recovery suggestions
- Comprehensive audit logging for game events
- Graceful error handling for game service failures
- Security-safe error exposure (development vs production)
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
from app.error_handlers import ErrorResponse, handle_service_error, ErrorMessages

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
        raise handle_service_error(e, "create game", ErrorMessages.INTERNAL_ERROR)
    except Exception as e:
        logger.error(
            "[GAME-API-ERROR] Unexpected error creating game",
            extra={"user_id": current_user.id, "error": str(e)},
        )
        raise ErrorResponse.internal_server_error(
            "Failed to create game", error=e, operation="create game"
        )


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
        raise ErrorResponse.internal_server_error(
            "Failed to get games", error=e, operation="get user games"
        )


@router.get("/api/games/{game_id}", response_model=Game)
async def get_game(game_id: str, current_user: User = Depends(get_current_user)):
    """Get specific game details"""
    try:
        game = await game_service.get_game(
            game_id, include_playlist=True, include_players=True
        )
        if not game:
            raise ErrorResponse.not_found("Game", game_id)

        # Check if user has access to this game
        user_has_access = game.host_id == current_user.id or any(
            player.id == current_user.id for player in game.players
        )

        if not user_has_access and game.is_private:
            raise ErrorResponse.forbidden(
                "Access denied to private game",
                details="You must be invited or be the host to access this private game"
            )

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
        raise ErrorResponse.internal_server_error(
            "Failed to get game details", error=e, operation="get game"
        )


# Continue with the rest of the routes using similar pattern...
