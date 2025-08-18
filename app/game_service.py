"""
Game State Service for Foute Muziek Bingo
Replaces JSON file storage with Supabase database integration
"""
import logging
import random
import string
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple
from app.models import (
    Game,
    GameCreate,
    GameUpdate,
    GamePublic,
    GameStatus,
    GameSettings,
    BingoCard,
    Track,
    Playlist,
    User,
    UserPublic,
    BingoMode,
    APIResponse,
)
from app.database import database, DatabaseError, NotFoundError
from app.auth_service import get_current_user_optional
from fastapi import Request

logger = logging.getLogger("music_bingo")


class GameError(Exception):
    """Game-related errors"""

    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class GameStateService:
    """
    Game state management service with Supabase integration
    Replaces the legacy JSON file-based state management
    """

    def __init__(self):
        self.bingo_patterns = {
            BingoMode.ROW: self._check_row_pattern,
            BingoMode.COLUMN: self._check_column_pattern,
            BingoMode.DIAGONAL: self._check_diagonal_pattern,
            BingoMode.FULL_CARD: self._check_full_card_pattern,
            BingoMode.ROW_COL_DIAG: self._check_row_col_diag_pattern,
        }

    def _generate_room_code(self) -> str:
        """Generate a unique 6-digit room code"""
        return "".join(random.choices(string.digits, k=6))

    async def _ensure_unique_room_code(self) -> str:
        """Ensure room code is unique across all active games"""
        max_attempts = 10
        for _ in range(max_attempts):
            room_code = self._generate_room_code()

            # Check if room code already exists
            existing_games = await database.query_records(
                "games",
                filters={"room_code": room_code, "status": GameStatus.WAITING.value},
            )

            if not existing_games:
                return room_code

        raise GameError("Failed to generate unique room code. Please try again.")

    async def create_game(self, game_data: GameCreate, host_user: User) -> Game:
        """Create a new game"""
        game_id = f"game-{int(datetime.now().timestamp())}"

        logger.info(
            f"[GAME-CREATE-001] Creating new game",
            extra={
                "game_id": game_id,
                "host_user_id": host_user.id,
                "game_name": game_data.name,
                "playlist_id": game_data.playlist_id,
            },
        )

        try:
            # Verify playlist exists (accept either DB playlist id or Spotify playlist id)
            playlist = await database.get_record("playlists", game_data.playlist_id)
            if not playlist:
                # Try resolving by spotify_id for robustness
                try:
                    candidates = await database.query_records(
                        "playlists",
                        filters={
                            "spotify_id": game_data.playlist_id,
                            "owner_id": host_user.id,
                        },
                    )
                    if candidates:
                        playlist = candidates[0]
                        # Normalize to DB id for downstream usage
                        game_data.playlist_id = playlist["id"]
                except Exception:
                    playlist = None

            if not playlist:
                raise GameError(
                    f"Playlist not found. Ensure playlists are synced (open dashboard once) and pass a valid playlist id."
                )

            # Generate unique room code if private game
            room_code = None
            if game_data.is_private:
                room_code = await self._ensure_unique_room_code()

            # Prepare game data for database
            db_game_data = {
                "name": game_data.name,
                "description": game_data.description,
                "host_id": host_user.id,
                "playlist_id": game_data.playlist_id,
                "status": GameStatus.WAITING.value,
                "room_code": room_code,
                "max_players": game_data.max_players,
                "is_private": game_data.is_private,
                "current_track_index": 0,
                "settings": game_data.settings.dict(),
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }

            # Create game in database
            created_game = await database.create_record("games", db_game_data)

            logger.info(
                f"[GAME-CREATE-002] Game created successfully",
                extra={
                    "game_id": created_game["id"],
                    "room_code": room_code,
                    "host_user_id": host_user.id,
                },
            )

            # Return full game object with playlist
            game = Game(**created_game)
            game.playlist = Playlist(**playlist)

            return game

        except DatabaseError as e:
            logger.error(
                f"[GAME-CREATE-ERROR] Database error creating game",
                extra={
                    "game_id": game_id,
                    "error": str(e),
                    "host_user_id": host_user.id,
                },
            )
            raise GameError(f"Failed to create game: {str(e)}")
        except Exception as e:
            logger.error(
                f"[GAME-CREATE-ERROR] Unexpected error creating game",
                extra={
                    "game_id": game_id,
                    "error": str(e),
                    "host_user_id": host_user.id,
                },
            )
            raise GameError(f"Failed to create game: {str(e)}")

    async def get_game(
        self, game_id: str, include_playlist: bool = True, include_players: bool = True
    ) -> Optional[Game]:
        """Get game by ID with optional related data"""
        try:
            logger.debug(
                f"[GAME-GET-001] Retrieving game",
                extra={
                    "game_id": game_id,
                    "include_playlist": include_playlist,
                    "include_players": include_players,
                },
            )

            # Get base game data
            game_data = await database.get_record("games", game_id)
            if not game_data:
                return None

            game = Game(**game_data)

            # Include playlist if requested
            if include_playlist and game.playlist_id:
                playlist_data = await database.get_record("playlists", game.playlist_id)
                if playlist_data:
                    game.playlist = Playlist(**playlist_data)

            # Include players if requested
            if include_players:
                # Get game players from junction table
                players_data = await database.query_records(
                    "game_players", filters={"game_id": game_id}
                )

                # Get user details for each player
                player_users = []
                for player_data in players_data:
                    user_data = await database.get_record(
                        "users", player_data["user_id"]
                    )
                    if user_data:
                        user = User(**user_data)
                        player_users.append(
                            UserPublic(
                                id=user.id,
                                spotify_id=user.spotify_id,
                                display_name=user.display_name,
                                email=user.email,
                                avatar_url=user.avatar_url,
                                subscription_type=user.subscription_type,
                                created_at=user.created_at,
                                last_login_at=user.last_login_at,
                            )
                        )

                game.players = player_users

            logger.debug(
                f"[GAME-GET-002] Game retrieved successfully",
                extra={
                    "game_id": game_id,
                    "game_name": game.name,
                    "status": game.status,
                    "player_count": len(game.players) if include_players else 0,
                },
            )

            return game

        except Exception as e:
            logger.error(
                f"[GAME-GET-ERROR] Error retrieving game",
                extra={"game_id": game_id, "error": str(e)},
            )
            return None

    async def get_game_by_room_code(self, room_code: str) -> Optional[Game]:
        """Get game by room code"""
        try:
            games = await database.query_records(
                "games", filters={"room_code": room_code}
            )

            if games:
                return await self.get_game(games[0]["id"])
            return None

        except Exception as e:
            logger.error(
                f"[GAME-ROOM-ERROR] Error finding game by room code",
                extra={"room_code": room_code, "error": str(e)},
            )
            return None

    async def join_game(self, game_id: str, user: User) -> Game:
        """Add player to game"""
        logger.info(
            f"[GAME-JOIN-001] User joining game",
            extra={
                "game_id": game_id,
                "user_id": user.id,
                "user_name": user.display_name,
            },
        )

        try:
            # Get current game state
            game = await self.get_game(game_id, include_players=True)
            if not game:
                raise GameError("Game not found")

            # Check if game is joinable
            if game.status != GameStatus.WAITING:
                raise GameError("Game is not accepting new players")

            # Check if user is already in game
            if any(player.id == user.id for player in game.players):
                logger.info(
                    f"[GAME-JOIN-002] User already in game",
                    extra={"game_id": game_id, "user_id": user.id},
                )
                return game

            # Check if game is full
            if len(game.players) >= game.max_players:
                raise GameError("Game is full")

            # Add user to game_players table
            player_data = {
                "game_id": game_id,
                "user_id": user.id,
                "joined_at": datetime.now(timezone.utc).isoformat(),
            }

            await database.create_record("game_players", player_data)

            # Generate bingo card for the player
            await self._generate_bingo_card(
                game_id, user.id, game.playlist.tracks if game.playlist else []
            )

            logger.info(
                f"[GAME-JOIN-003] User joined game successfully",
                extra={
                    "game_id": game_id,
                    "user_id": user.id,
                    "total_players": len(game.players) + 1,
                },
            )

            # Return updated game
            return await self.get_game(game_id, include_players=True)

        except GameError:
            raise
        except Exception as e:
            logger.error(
                f"[GAME-JOIN-ERROR] Error joining game",
                extra={"game_id": game_id, "user_id": user.id, "error": str(e)},
            )
            raise GameError(f"Failed to join game: {str(e)}")

    async def start_game(self, game_id: str, host_user: User) -> Game:
        """Start a game (host only)"""
        logger.info(
            f"[GAME-START-001] Starting game",
            extra={"game_id": game_id, "host_user_id": host_user.id},
        )

        try:
            game = await self.get_game(game_id, include_players=True)
            if not game:
                raise GameError("Game not found")

            # Check if user is the host
            if game.host_id != host_user.id:
                raise GameError("Only the game host can start the game")

            # Check if game is in correct state
            if game.status != GameStatus.WAITING:
                raise GameError("Game cannot be started")

            # Check if there are any players
            if len(game.players) == 0:
                raise GameError("Cannot start game with no players")

            # Update game status
            update_data = {
                "status": GameStatus.IN_PROGRESS.value,
                "started_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }

            await database.update_record("games", game_id, update_data)

            logger.info(
                f"[GAME-START-002] Game started successfully",
                extra={"game_id": game_id, "player_count": len(game.players)},
            )

            return await self.get_game(game_id)

        except GameError:
            raise
        except Exception as e:
            logger.error(
                f"[GAME-START-ERROR] Error starting game",
                extra={
                    "game_id": game_id,
                    "host_user_id": host_user.id,
                    "error": str(e),
                },
            )
            raise GameError(f"Failed to start game: {str(e)}")

    async def _generate_bingo_card(
        self, game_id: str, user_id: str, tracks: List[Track]
    ) -> BingoCard:
        """Generate a bingo card for a player"""
        logger.debug(
            f"[CARD-GEN-001] Generating bingo card",
            extra={"game_id": game_id, "user_id": user_id, "track_count": len(tracks)},
        )

        try:
            if len(tracks) < 25:
                raise GameError(
                    "Not enough tracks in playlist for bingo card (need at least 25)"
                )

            # Select 25 random tracks
            selected_tracks = random.sample(tracks, 25)

            # Create 5x5 grid
            grid = []
            marked = []
            track_index = 0

            for row in range(5):
                grid_row = []
                marked_row = []
                for col in range(5):
                    if row == 2 and col == 2:
                        # Center square is "FREE"
                        grid_row.append(
                            {"id": "free", "name": "FREE", "artist": "FREE"}
                        )
                        marked_row.append(True)
                    else:
                        track = selected_tracks[track_index]
                        grid_row.append(
                            {"id": track.id, "name": track.name, "artist": track.artist}
                        )
                        marked_row.append(False)
                        track_index += 1

                grid.append(grid_row)
                marked.append(marked_row)

            # Save card to database
            card_data = {
                "user_id": user_id,
                "game_id": game_id,
                "grid": grid,
                "marked": marked,
                "patterns_completed": [],
                "is_winner": False,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }

            created_card = await database.create_record("bingo_cards", card_data)

            logger.debug(
                f"[CARD-GEN-002] Bingo card generated successfully",
                extra={
                    "game_id": game_id,
                    "user_id": user_id,
                    "card_id": created_card["id"],
                },
            )

            return BingoCard(**created_card)

        except Exception as e:
            logger.error(
                f"[CARD-GEN-ERROR] Error generating bingo card",
                extra={"game_id": game_id, "user_id": user_id, "error": str(e)},
            )
            raise GameError(f"Failed to generate bingo card: {str(e)}")

    async def mark_track(
        self, game_id: str, user_id: str, track_id: str
    ) -> Dict[str, Any]:
        """Mark a track on user's bingo card"""
        logger.debug(
            f"[TRACK-MARK-001] Marking track",
            extra={"game_id": game_id, "user_id": user_id, "track_id": track_id},
        )

        try:
            # Get user's bingo card
            cards = await database.query_records(
                "bingo_cards", filters={"game_id": game_id, "user_id": user_id}
            )

            if not cards:
                raise GameError("Bingo card not found")

            card = BingoCard(**cards[0])

            # Find and mark the track
            marked_position = None
            for row_idx, row in enumerate(card.grid):
                for col_idx, cell in enumerate(row):
                    if cell["id"] == track_id:
                        card.marked[row_idx][col_idx] = True
                        marked_position = (row_idx, col_idx)
                        break
                if marked_position:
                    break

            if not marked_position:
                logger.warning(
                    f"[TRACK-MARK-WARN] Track not found on card",
                    extra={
                        "game_id": game_id,
                        "user_id": user_id,
                        "track_id": track_id,
                    },
                )
                return {"marked": False, "bingo": False}

            # Check for bingo patterns
            game = await self.get_game(game_id)
            if not game:
                raise GameError("Game not found")

            bingo_achieved = await self._check_bingo_patterns(
                card, game.settings.bingo_mode
            )

            # Update card in database
            update_data = {
                "marked": card.marked,
                "patterns_completed": card.patterns_completed,
                "is_winner": card.is_winner,
            }

            await database.update_record("bingo_cards", card.id, update_data)

            logger.debug(
                f"[TRACK-MARK-002] Track marked successfully",
                extra={
                    "game_id": game_id,
                    "user_id": user_id,
                    "track_id": track_id,
                    "position": marked_position,
                    "bingo_achieved": bingo_achieved,
                },
            )

            return {
                "marked": True,
                "position": marked_position,
                "bingo": bingo_achieved,
                "patterns": card.patterns_completed,
            }

        except GameError:
            raise
        except Exception as e:
            logger.error(
                f"[TRACK-MARK-ERROR] Error marking track",
                extra={
                    "game_id": game_id,
                    "user_id": user_id,
                    "track_id": track_id,
                    "error": str(e),
                },
            )
            raise GameError(f"Failed to mark track: {str(e)}")

    async def _check_bingo_patterns(
        self, card: BingoCard, bingo_mode: BingoMode
    ) -> bool:
        """Check if card has winning patterns"""
        if bingo_mode in self.bingo_patterns:
            return self.bingo_patterns[bingo_mode](card)
        return False

    def _check_row_pattern(self, card: BingoCard) -> bool:
        """Check for row completion"""
        for row in card.marked:
            if all(row):
                if "row" not in card.patterns_completed:
                    card.patterns_completed.append("row")
                    card.is_winner = True
                return True
        return False

    def _check_column_pattern(self, card: BingoCard) -> bool:
        """Check for column completion"""
        for col_idx in range(5):
            if all(card.marked[row_idx][col_idx] for row_idx in range(5)):
                if "column" not in card.patterns_completed:
                    card.patterns_completed.append("column")
                    card.is_winner = True
                return True
        return False

    def _check_diagonal_pattern(self, card: BingoCard) -> bool:
        """Check for diagonal completion"""
        # Check main diagonal
        if all(card.marked[i][i] for i in range(5)):
            if "diagonal_main" not in card.patterns_completed:
                card.patterns_completed.append("diagonal_main")
                card.is_winner = True
            return True

        # Check anti-diagonal
        if all(card.marked[i][4 - i] for i in range(5)):
            if "diagonal_anti" not in card.patterns_completed:
                card.patterns_completed.append("diagonal_anti")
                card.is_winner = True
            return True

        return False

    def _check_full_card_pattern(self, card: BingoCard) -> bool:
        """Check for full card completion"""
        if all(all(row) for row in card.marked):
            if "full_card" not in card.patterns_completed:
                card.patterns_completed.append("full_card")
                card.is_winner = True
            return True
        return False

    def _check_row_col_diag_pattern(self, card: BingoCard) -> bool:
        """Check for row, column, or diagonal completion"""
        return (
            self._check_row_pattern(card)
            or self._check_column_pattern(card)
            or self._check_diagonal_pattern(card)
        )

    async def get_user_games(
        self, user_id: str, status_filter: Optional[GameStatus] = None
    ) -> List[GamePublic]:
        """Get games for a specific user with error recovery"""
        try:
            # Build query filters
            filters = {}
            if status_filter:
                filters["status"] = status_filter.value

            # Get games where user is host
            try:
                hosted_games = await database.query_records(
                    "games",
                    filters={**filters, "host_id": user_id},
                    order_by={"column": "created_at", "ascending": False},
                )
            except Exception as db_error:
                logger.warning(
                    f"[GAME-HOST-WARN] Failed to query hosted games",
                    extra={"user_id": user_id, "error": str(db_error)},
                )
                hosted_games = []

            # Get games where user is a player
            try:
                player_games_data = await database.query_records(
                    "game_players", filters={"user_id": user_id}
                )

                player_game_ids = [pg["game_id"] for pg in player_games_data]
                joined_games = []

                # EMERGENCY FIX: Use bulk query with EXISTS check to avoid orphaned records
                if player_game_ids:
                    try:
                        # Query all games in one go to avoid N+1 queries and handle missing games
                        bulk_query_filters = {"id": {"in": player_game_ids}}
                        if status_filter:
                            bulk_query_filters["status"] = status_filter.value
                        
                        joined_games = await database.query_records(
                            "games", 
                            filters=bulk_query_filters
                        )
                        
                        # EMERGENCY CLEANUP: Log and clean up orphaned game_players records
                        found_game_ids = {game["id"] for game in joined_games}
                        orphaned_ids = set(player_game_ids) - found_game_ids
                        
                        if orphaned_ids:
                            logger.warning(
                                f"[GAME-CLEANUP-EMERGENCY] Found {len(orphaned_ids)} orphaned game_players records",
                                extra={
                                    "user_id": user_id,
                                    "orphaned_count": len(orphaned_ids),
                                    "total_player_games": len(player_game_ids)
                                }
                            )
                            
                            # Clean up orphaned records to prevent future issues
                            for orphaned_id in orphaned_ids:
                                try:
                                    await database.delete_record("game_players", 
                                        filters={"game_id": orphaned_id, "user_id": user_id})
                                    logger.info(f"[GAME-CLEANUP] Removed orphaned game_players record: {orphaned_id}")
                                except Exception as cleanup_error:
                                    logger.warning(f"[GAME-CLEANUP-WARN] Failed to clean up orphaned record {orphaned_id}: {cleanup_error}")
                                    
                    except Exception as bulk_error:
                        logger.warning(
                            f"[GAME-BULK-WARN] Bulk query failed, falling back to individual queries",
                            extra={"user_id": user_id, "error": str(bulk_error)}
                        )
                        # Fallback to individual queries with better error handling
                        joined_games = []
                        for game_id in player_game_ids:
                            try:
                                game_data = await database.get_record("games", game_id)
                                if game_data and (
                                    not status_filter
                                    or game_data["status"] == status_filter.value
                                ):
                                    joined_games.append(game_data)
                            except Exception as game_error:
                                logger.warning(
                                    f"[GAME-SINGLE-WARN] Game {game_id} not found, cleaning up orphaned record",
                                    extra={
                                        "user_id": user_id,
                                        "game_id": game_id,
                                        "error": str(game_error),
                                    },
                                )
                                # Clean up the orphaned record
                                try:
                                    await database.delete_record("game_players", 
                                        filters={"game_id": game_id, "user_id": user_id})
                                except Exception:
                                    pass  # Ignore cleanup errors in fallback
                                continue
                else:
                    joined_games = []

            except Exception as player_error:
                logger.warning(
                    f"[GAME-PLAYER-WARN] Failed to query player games",
                    extra={"user_id": user_id, "error": str(player_error)},
                )
                joined_games = []

            # Combine and convert to GamePublic
            all_games = hosted_games + joined_games

            # Remove duplicates and convert to GamePublic
            seen_ids = set()
            public_games = []

            for game_data in all_games:
                if game_data["id"] not in seen_ids:
                    seen_ids.add(game_data["id"])

                    # Get player count with error recovery
                    try:
                        players = await database.query_records(
                            "game_players", filters={"game_id": game_data["id"]}
                        )
                    except Exception as player_count_error:
                        logger.warning(
                            f"[GAME-PLAYERS-WARN] Failed to get player count",
                            extra={
                                "user_id": user_id,
                                "game_id": game_data["id"],
                                "error": str(player_count_error),
                            },
                        )
                        players = []

                    try:
                        public_game = GamePublic(
                            id=game_data["id"],
                            name=game_data["name"],
                            description=game_data.get("description"),
                            host_id=game_data["host_id"],
                            status=GameStatus(game_data["status"]),
                            room_code=game_data.get("room_code"),
                            max_players=game_data["max_players"],
                            current_players=len(players),
                            # Default to False if missing
                            is_private=game_data.get("is_private", False),
                            created_at=datetime.fromisoformat(game_data["created_at"]),
                            started_at=datetime.fromisoformat(game_data["started_at"])
                            if game_data.get("started_at")
                            else None,
                        )
                        public_games.append(public_game)
                    except Exception as model_error:
                        logger.warning(
                            f"[GAME-MODEL-WARN] Failed to create GamePublic model: {str(model_error)}",
                            extra={
                                "user_id": user_id,
                                "game_id": game_data["id"],
                                "error": str(model_error),
                                "error_type": type(model_error).__name__,
                                "game_data_keys": list(game_data.keys())
                                if game_data
                                else [],
                            },
                        )
                        continue

            return sorted(public_games, key=lambda g: g.created_at, reverse=True)

        except Exception as e:
            logger.warning(
                f"[GAME-USER-WARN] Unexpected error getting user games, returning empty list",
                extra={
                    "user_id": user_id,
                    "status_filter": status_filter.value if status_filter else None,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )
            # Return empty list rather than failing completely
            return []



    async def validate_game(self, game_id: str, user_id: str, include_track_count: bool = True) -> "GameValidationResult":
        """
        Validate a single game for existence, accessibility, and readiness.
        
        Args:
            game_id: Game ID to validate
            user_id: User ID requesting validation (for access checks)
            include_track_count: Whether to include playlist track count
            
        Returns:
            GameValidationResult with comprehensive validation status
        """
        from app.models import GameValidationResult, GameValidationStatus
        
        logger.debug(f"[GAME-VALIDATE-001] Validating game {game_id} for user {user_id}")
        
        try:
            # Check if game exists in database
            game_data = await database.get_record("games", game_id)
            if not game_data:
                return GameValidationResult(
                    game_id=game_id,
                    status=GameValidationStatus.NOT_FOUND,
                    exists=False,
                    has_playlist=False,
                    track_count=0,
                    can_generate_cards=False,
                    error_message="Game not found in database"
                )
            
            # Check user access to game
            user_has_access = (
                game_data["host_id"] == user_id or 
                not game_data.get("is_private", False)
            )
            
            if game_data.get("is_private", False) and game_data["host_id"] != user_id:
                # Check if user is a player
                players = await database.query_records(
                    "game_players", 
                    filters={"game_id": game_id, "user_id": user_id}
                )
                user_has_access = len(players) > 0
            
            # Get playlist data if game exists
            playlist_id = game_data.get("playlist_id")
            has_playlist = False
            track_count = 0
            
            if playlist_id:
                playlist_data = await database.get_record("playlists", playlist_id)
                if playlist_data:
                    has_playlist = True
                    if include_track_count:
                        # Count tracks in playlist
                        tracks = await database.query_records(
                            "playlist_tracks",
                            filters={"playlist_id": playlist_id}
                        )
                        track_count = len(tracks)
                    else:
                        # Use stored total_tracks if available
                        track_count = playlist_data.get("total_tracks", 0)
            
            # Determine validation status
            if not user_has_access:
                status = GameValidationStatus.INVALID
                error_message = "Access denied to private game"
            elif not has_playlist:
                status = GameValidationStatus.NO_PLAYLIST
                error_message = "Game has no valid playlist"
            elif track_count < 25:  # Minimum for 5x5 bingo card
                status = GameValidationStatus.INSUFFICIENT_TRACKS
                error_message = f"Playlist has only {track_count} tracks (minimum 25 required)"
            else:
                status = GameValidationStatus.VALID
                error_message = None
            
            # Get last activity timestamp
            last_activity = None
            if game_data.get("updated_at"):
                last_activity = datetime.fromisoformat(game_data["updated_at"])
            elif game_data.get("created_at"):
                last_activity = datetime.fromisoformat(game_data["created_at"])
            
            return GameValidationResult(
                game_id=game_id,
                status=status,
                exists=True,
                has_playlist=has_playlist,
                track_count=track_count,
                can_generate_cards=track_count >= 25,
                error_message=error_message,
                last_activity=last_activity
            )
            
        except Exception as e:
            logger.error(
                f"[GAME-VALIDATE-ERROR] Error validating game {game_id}",
                extra={"game_id": game_id, "user_id": user_id, "error": str(e)}
            )
            return GameValidationResult(
                game_id=game_id,
                status=GameValidationStatus.INVALID,
                exists=False,
                has_playlist=False,
                track_count=0,
                can_generate_cards=False,
                error_message=f"Validation error: {str(e)}"
            )

    async def validate_games_bulk(
        self, 
        game_ids: List[str], 
        user_id: str, 
        include_track_count: bool = True,
        filter_status: Optional["GameStatus"] = None
    ) -> "BulkGameValidationResponse":
        """
        Validate multiple games in a single efficient operation.
        
        Args:
            game_ids: List of game IDs to validate (max 100)
            user_id: User ID requesting validation
            include_track_count: Whether to include playlist track counts
            filter_status: Optional status filter for games
            
        Returns:
            BulkGameValidationResponse with all validation results
        """
        from app.models import BulkGameValidationResponse, GameValidationStatus
        import time
        
        start_time = time.time()
        
        logger.info(
            f"[GAME-BULK-VALIDATE-001] Starting bulk validation",
            extra={
                "user_id": user_id,
                "game_count": len(game_ids),
                "include_track_count": include_track_count,
                "filter_status": filter_status.value if filter_status else None
            }
        )
        
        # Limit to prevent abuse
        if len(game_ids) > 100:
            game_ids = game_ids[:100]
            logger.warning(
                f"[GAME-BULK-VALIDATE-WARN] Truncated game list to 100 items",
                extra={"user_id": user_id, "original_count": len(game_ids)}
            )
        
        validation_results = []
        summary = {
            "valid": 0,
            "invalid": 0,
            "not_found": 0,
            "no_playlist": 0,
            "insufficient_tracks": 0
        }
        
        try:
            # Efficient bulk database queries
            # 1. Get all games in one query
            games_query = """
                SELECT id, host_id, playlist_id, is_private, status, created_at, updated_at
                FROM games 
                WHERE id = ANY($1)
            """
            if filter_status:
                games_query += " AND status = $2"
                games_data = await database.execute_query(
                    games_query, 
                    [game_ids, filter_status.value]
                )
            else:
                games_data = await database.execute_query(games_query, [game_ids])
            
            # Create lookup for existing games
            games_lookup = {game["id"]: game for game in games_data}
            
            # 2. Get user's game participation in one query
            player_games_query = """
                SELECT DISTINCT game_id 
                FROM game_players 
                WHERE user_id = $1 AND game_id = ANY($2)
            """
            player_games_data = await database.execute_query(
                player_games_query, 
                [user_id, game_ids]
            )
            user_game_ids = {row["game_id"] for row in player_games_data}
            
            # 3. Get playlist data for games that have playlists
            playlist_ids = [
                game["playlist_id"] for game in games_data 
                if game.get("playlist_id")
            ]
            
            playlists_lookup = {}
            track_counts_lookup = {}
            
            if playlist_ids:
                # Get playlist existence
                playlists_query = "SELECT id, total_tracks FROM playlists WHERE id = ANY($1)"
                playlists_data = await database.execute_query(playlists_query, [playlist_ids])
                playlists_lookup = {p["id"]: p for p in playlists_data}
                
                # Get actual track counts if requested
                if include_track_count:
                    track_counts_query = """
                        SELECT playlist_id, COUNT(*) as track_count
                        FROM playlist_tracks 
                        WHERE playlist_id = ANY($1)
                        GROUP BY playlist_id
                    """
                    track_counts_data = await database.execute_query(
                        track_counts_query, 
                        [playlist_ids]
                    )
                    track_counts_lookup = {
                        row["playlist_id"]: row["track_count"] 
                        for row in track_counts_data
                    }
            
            # 4. Process each game ID
            for game_id in game_ids:
                try:
                    result = await self._validate_single_game_from_bulk_data(
                        game_id=game_id,
                        user_id=user_id,
                        games_lookup=games_lookup,
                        user_game_ids=user_game_ids,
                        playlists_lookup=playlists_lookup,
                        track_counts_lookup=track_counts_lookup,
                        include_track_count=include_track_count
                    )
                    
                    validation_results.append(result)
                    summary[result.status.value] += 1
                    
                except Exception as e:
                    logger.error(
                        f"[GAME-BULK-VALIDATE-ERROR] Error validating game {game_id}",
                        extra={"game_id": game_id, "user_id": user_id, "error": str(e)}
                    )
                    # Add error result
                    from app.models import GameValidationResult, GameValidationStatus
                    error_result = GameValidationResult(
                        game_id=game_id,
                        status=GameValidationStatus.INVALID,
                        exists=False,
                        has_playlist=False,
                        track_count=0,
                        can_generate_cards=False,
                        error_message=f"Validation error: {str(e)}"
                    )
                    validation_results.append(error_result)
                    summary["invalid"] += 1
            
            processing_time_ms = (time.time() - start_time) * 1000
            
            logger.info(
                f"[GAME-BULK-VALIDATE-002] Bulk validation completed",
                extra={
                    "user_id": user_id,
                    "total_requested": len(game_ids),
                    "total_processed": len(validation_results),
                    "processing_time_ms": processing_time_ms,
                    "summary": summary
                }
            )
            
            return BulkGameValidationResponse(
                success=True,
                total_requested=len(game_ids),
                total_processed=len(validation_results),
                validation_results=validation_results,
                summary=summary,
                timestamp=datetime.now(timezone.utc),
                processing_time_ms=processing_time_ms
            )
            
        except Exception as e:
            logger.error(
                f"[GAME-BULK-VALIDATE-ERROR] Bulk validation failed",
                extra={
                    "user_id": user_id,
                    "game_count": len(game_ids),
                    "error": str(e)
                }
            )
            
            processing_time_ms = (time.time() - start_time) * 1000
            
            return BulkGameValidationResponse(
                success=False,
                total_requested=len(game_ids),
                total_processed=len(validation_results),
                validation_results=validation_results,
                summary=summary,
                timestamp=datetime.now(timezone.utc),
                processing_time_ms=processing_time_ms
            )

    async def _validate_single_game_from_bulk_data(
        self,
        game_id: str,
        user_id: str,
        games_lookup: Dict[str, Dict],
        user_game_ids: set,
        playlists_lookup: Dict[str, Dict],
        track_counts_lookup: Dict[str, int],
        include_track_count: bool
    ) -> "GameValidationResult":
        """
        Helper method to validate a single game using pre-fetched bulk data.
        
        This method is optimized for bulk operations and avoids individual database queries.
        """
        from app.models import GameValidationResult, GameValidationStatus
        
        # Check if game exists
        game_data = games_lookup.get(game_id)
        if not game_data:
            return GameValidationResult(
                game_id=game_id,
                status=GameValidationStatus.NOT_FOUND,
                exists=False,
                has_playlist=False,
                track_count=0,
                can_generate_cards=False,
                error_message="Game not found in database"
            )
        
        # Check user access
        user_has_access = (
            game_data["host_id"] == user_id or 
            not game_data.get("is_private", False) or
            game_id in user_game_ids
        )
        
        if not user_has_access:
            return GameValidationResult(
                game_id=game_id,
                status=GameValidationStatus.INVALID,
                exists=True,
                has_playlist=False,
                track_count=0,
                can_generate_cards=False,
                error_message="Access denied to private game"
            )
        
        # Check playlist
        playlist_id = game_data.get("playlist_id")
        has_playlist = False
        track_count = 0
        
        if playlist_id and playlist_id in playlists_lookup:
            has_playlist = True
            if include_track_count and playlist_id in track_counts_lookup:
                track_count = track_counts_lookup[playlist_id]
            else:
                # Use stored total_tracks as fallback
                track_count = playlists_lookup[playlist_id].get("total_tracks", 0)
        
        # Determine status
        if not has_playlist:
            status = GameValidationStatus.NO_PLAYLIST
            error_message = "Game has no valid playlist"
        elif track_count < 25:
            status = GameValidationStatus.INSUFFICIENT_TRACKS
            error_message = f"Playlist has only {track_count} tracks (minimum 25 required)"
        else:
            status = GameValidationStatus.VALID
            error_message = None
        
        # Get last activity
        last_activity = None
        if game_data.get("updated_at"):
            last_activity = datetime.fromisoformat(game_data["updated_at"])
        elif game_data.get("created_at"):
            last_activity = datetime.fromisoformat(game_data["created_at"])
        
        return GameValidationResult(
            game_id=game_id,
            status=status,
            exists=True,
            has_playlist=has_playlist,
            track_count=track_count,
            can_generate_cards=track_count >= 25,
            error_message=error_message,
            last_activity=last_activity
        )

    async def check_game_existence(self, game_id: str, user_id: str) -> "GameExistenceCheck":
        """
        Quick game existence check without full validation.
        
        Args:
            game_id: Game ID to check
            user_id: User ID for access validation
            
        Returns:
            GameExistenceCheck with basic existence and access info
        """
        from app.models import GameExistenceCheck
        
        try:
            game_data = await database.get_record("games", game_id)
            if not game_data:
                return GameExistenceCheck(
                    game_id=game_id,
                    exists=False,
                    accessible=False,
                    status=None
                )
            
            # Check accessibility
            accessible = (
                game_data["host_id"] == user_id or 
                not game_data.get("is_private", False)
            )
            
            if game_data.get("is_private", False) and game_data["host_id"] != user_id:
                # Quick check if user is a player
                players = await database.query_records(
                    "game_players",
                    filters={"game_id": game_id, "user_id": user_id}
                )
                accessible = len(players) > 0
            
            return GameExistenceCheck(
                game_id=game_id,
                exists=True,
                accessible=accessible,
                status=GameStatus(game_data["status"]) if game_data.get("status") else None
            )
            
        except Exception as e:
            logger.error(
                f"[GAME-EXISTENCE-ERROR] Error checking game existence",
                extra={"game_id": game_id, "user_id": user_id, "error": str(e)}
            )
            return GameExistenceCheck(
                game_id=game_id,
                exists=False,
                accessible=False,
                status=None
            )

# Global game service instance
game_service = GameStateService()
