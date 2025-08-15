"""
Redis-based Game State Manager for Production Scalability

This module implements ephemeral game state management using Redis/Dragonfly
for real-time, horizontally scalable game operations.
"""

import json
import logging
import asyncio
from typing import Optional, Dict, Any, List
from datetime import datetime
import redis.asyncio as redis
from pydantic import ValidationError

from app.config import get_config
from app.models import (
    RedisGameState,
    StateOperation,
    Track,
    GameSettings,
    RedisKeySchema
)

logger = logging.getLogger("music_bingo")


class RedisGameStateManager:
    """
    Production-grade Dragonfly game state manager (Redis-compatible) with:
    - Async operations with connection pooling
    - TTL management for ephemeral data
    - Atomic operations using Lua scripts
    - Connection failover and health monitoring
    - Performance optimization with pipelining
    """

    def __init__(self, redis_url: str = None, redis_password: str = None):
        """
        Initialize Dragonfly game state manager (Redis-compatible).

        Args:
            redis_url: Dragonfly connection URL (defaults to config)
            redis_password: Dragonfly password (defaults to config)
        """
        self.config = get_config()
        self.redis_url = redis_url or self.config.dragonfly_url
        self.redis_password = redis_password or self.config.dragonfly_password

        # Connection management
        self.redis: Optional[redis.Redis] = None
        self.is_connected = False
        self.connection_retries = 0
        self.max_retries = 5

        # Performance optimization
        self.pipeline_size = 100
        self.connection_pool = None

        # Health monitoring
        self.last_health_check: Optional[datetime] = None
        self.health_check_interval = 60  # seconds

        # Lua scripts for atomic operations
        self.lua_scripts = {}

    async def initialize(self) -> None:
        """Initialize Redis connection with connection pooling"""
        try:
            logger.info("[DRAGONFLY-STATE-INIT] Initializing Dragonfly game state manager")

            # Create connection pool for performance
            self.connection_pool = redis.ConnectionPool.from_url(
                self.redis_url,
                password=self.redis_password,
                max_connections=20,
                decode_responses=True,
                socket_keepalive=True,
                socket_keepalive_options={},
                health_check_interval=30
            )

            # Create Redis client with connection pool
            self.redis = redis.Redis(
                connection_pool=self.connection_pool,
                decode_responses=True
            )

            # Test connection
            await self.redis.ping()
            self.is_connected = True
            self.connection_retries = 0

            # Load Lua scripts for atomic operations
            await self._load_lua_scripts()

            logger.info("[DRAGONFLY-STATE-INIT] Dragonfly game state manager initialized successfully")

        except Exception as error:
            logger.error(f"[DRAGONFLY-STATE-INIT-ERROR] Failed to initialize Dragonfly connection: {error}")
            self.is_connected = False
            if self.connection_retries < self.max_retries:
                self.connection_retries += 1
                logger.info(f"[DRAGONFLY-STATE-RETRY] Retrying connection in 5 seconds (attempt {self.connection_retries}/{self.max_retries})")
                await asyncio.sleep(5)
                await self.initialize()
            else:
                raise Exception(f"Failed to connect to Dragonfly after {self.max_retries} attempts: {error}")

    async def _load_lua_scripts(self) -> None:
        """Load Lua scripts for atomic operations"""
        try:
            # Atomic game state update script
            update_game_state_script = """
                local game_key = KEYS[1]
                local state_data = ARGV[1]
                local ttl = tonumber(ARGV[2])
                local version = tonumber(ARGV[3])

                -- Get current version
                local current_data = redis.call('GET', game_key)
                if current_data then
                    local current_state = cjson.decode(current_data)
                    if current_state.state_version and current_state.state_version > version then
                        return {0, "Version conflict"}
                    end
                end

                -- Update state with TTL
                redis.call('SET', game_key, state_data)
                redis.call('EXPIRE', game_key, ttl)

                return {1, "Success"}
            """

            # Atomic player join script
            player_join_script = """
                local game_players_key = KEYS[1]
                local websocket_key = KEYS[2]
                local player_id = ARGV[1]
                local session_id = ARGV[2]
                local ttl = tonumber(ARGV[3])

                -- Add player to game
                redis.call('SADD', game_players_key, player_id)
                redis.call('EXPIRE', game_players_key, ttl)

                -- Map player to websocket session
                redis.call('SET', websocket_key, session_id)
                redis.call('EXPIRE', websocket_key, ttl)

                -- Get current player count
                local player_count = redis.call('SCARD', game_players_key)

                return player_count
            """

            # Atomic track advance script
            track_advance_script = """
                local played_key = KEYS[1]
                local unplayed_key = KEYS[2]
                local current_key = KEYS[3]
                local stats_key = KEYS[4]
                local track_data = ARGV[1]
                local ttl = tonumber(ARGV[2])

                -- Move current track to played
                local current_track = redis.call('GET', current_key)
                if current_track then
                    redis.call('LPUSH', played_key, current_track)
                    redis.call('EXPIRE', played_key, ttl)
                end

                -- Set new current track
                redis.call('SET', current_key, track_data)
                redis.call('EXPIRE', current_key, ttl)

                -- Remove from unplayed
                redis.call('LREM', unplayed_key, 1, track_data)
                redis.call('EXPIRE', unplayed_key, ttl)

                -- Update stats
                redis.call('HINCRBY', stats_key, 'tracks_played', 1)
                redis.call('HSET', stats_key, 'last_track_time', ARGV[3])
                redis.call('EXPIRE', stats_key, ttl)

                return redis.call('LLEN', unplayed_key)
            """

            # Register scripts
            self.lua_scripts['update_game_state'] = await self.redis.script_load(update_game_state_script)
            self.lua_scripts['player_join'] = await self.redis.script_load(player_join_script)
            self.lua_scripts['track_advance'] = await self.redis.script_load(track_advance_script)

            logger.info("[REDIS-STATE-SCRIPTS] Lua scripts loaded successfully")

        except Exception as error:
            logger.error(f"[REDIS-STATE-SCRIPTS-ERROR] Failed to load Lua scripts: {error}")
            raise

    async def health_check(self) -> bool:
        """Comprehensive health check for Redis connection and state"""
        try:
            if not self.redis or not self.is_connected:
                return False

            # Basic connectivity test
            await self.redis.ping()

            # Test key operations
            test_key = f"health:check:{int(datetime.now().timestamp())}"
            await self.redis.set(test_key, "test", ex=10)
            result = await self.redis.get(test_key)
            await self.redis.delete(test_key)

            if result != "test":
                return False

            # Update health check timestamp
            self.last_health_check = datetime.now()

            return True

        except Exception as error:
            logger.error(f"[REDIS-STATE-HEALTH-ERROR] Health check failed: {error}")
            self.is_connected = False
            return False

    async def get_game_state(self, game_id: str) -> Optional[RedisGameState]:
        """
        Get complete game state from Redis.

        Args:
            game_id: Game ID to retrieve state for

        Returns:
            RedisGameState object or None if not found
        """
        try:
            if not await self._ensure_connection():
                return None

            state_key = RedisKeySchema.get_key(RedisKeySchema.GAME_STATE, game_id=game_id)

            # Get serialized state
            state_data = await self.redis.get(state_key)
            if not state_data:
                return None

            # Parse and validate state
            state_dict = json.loads(state_data)
            game_state = RedisGameState(**state_dict)

            logger.debug(f"[REDIS-STATE-GET] Retrieved game state for {game_id}")
            return game_state

        except ValidationError as error:
            logger.error(f"[REDIS-STATE-GET-VALIDATION] Invalid state data for game {game_id}: {error}")
            return None
        except Exception as error:
            logger.error(f"[REDIS-STATE-GET-ERROR] Failed to get game state for {game_id}: {error}")
            return None

    async def update_game_state(self, game_id: str, state: RedisGameState) -> bool:
        """
        Update game state in Redis with atomic operation.

        Args:
            game_id: Game ID to update
            state: New game state

        Returns:
            True if successful, False otherwise
        """
        try:
            if not await self._ensure_connection():
                return False

            state_key = RedisKeySchema.get_key(RedisKeySchema.GAME_STATE, game_id=game_id)

            # Update activity timestamp
            state.last_activity = datetime.now()
            state.state_version += 1

            # Serialize state
            state_data = state.model_dump_json()

            # Use atomic Lua script for update
            result = await self.redis.evalsha(
                self.lua_scripts['update_game_state'],
                1,  # Number of keys
                state_key,  # Key
                state_data,  # State data
                str(state.ttl_seconds),  # TTL
                str(state.state_version)  # Version
            )

            success = result[0] == 1
            if success:
                logger.debug(f"[REDIS-STATE-UPDATE] Updated game state for {game_id}")

                # Log operation for audit trail
                await self._log_operation(
                    StateOperation(
                        operation_type="update_state",
                        game_id=game_id,
                        operation_data={"state_version": state.state_version},
                        success=True
                    )
                )
            else:
                logger.warning(f"[REDIS-STATE-UPDATE-CONFLICT] Version conflict for game {game_id}: {result[1]}")

            return success

        except Exception as error:
            logger.error(f"[REDIS-STATE-UPDATE-ERROR] Failed to update game state for {game_id}: {error}")
            return False

    async def create_game_state(self, game_id: str, initial_tracks: List[Track], settings: GameSettings) -> RedisGameState:
        """
        Create new game state in Redis.

        Args:
            game_id: Game ID
            initial_tracks: List of tracks for the game
            settings: Game settings

        Returns:
            Created RedisGameState object
        """
        try:
            if not await self._ensure_connection():
                raise Exception("Redis connection not available")

            # Create initial state
            initial_state = RedisGameState(
                game_id=game_id,
                unplayed_tracks=initial_tracks,
                settings=settings,
                last_activity=datetime.now(),
                state_version=1
            )

            # Save to Redis
            success = await self.update_game_state(game_id, initial_state)
            if not success:
                raise Exception("Failed to save initial game state")

            # Initialize related keys
            await self._initialize_game_keys(game_id, initial_state.ttl_seconds)

            logger.info(f"[REDIS-STATE-CREATE] Created new game state for {game_id}")
            return initial_state

        except Exception as error:
            logger.error(f"[REDIS-STATE-CREATE-ERROR] Failed to create game state for {game_id}: {error}")
            raise

    async def delete_game_state(self, game_id: str) -> bool:
        """
        Delete game state and all related keys from Redis.

        Args:
            game_id: Game ID to delete

        Returns:
            True if successful, False otherwise
        """
        try:
            if not await self._ensure_connection():
                return False

            # Get all keys for this game
            keys_to_delete = [
                RedisKeySchema.get_key(RedisKeySchema.GAME_STATE, game_id=game_id),
                RedisKeySchema.get_key(RedisKeySchema.GAME_TRACKS_PLAYED, game_id=game_id),
                RedisKeySchema.get_key(RedisKeySchema.GAME_TRACKS_UNPLAYED, game_id=game_id),
                RedisKeySchema.get_key(RedisKeySchema.GAME_CURRENT_TRACK, game_id=game_id),
                RedisKeySchema.get_key(RedisKeySchema.GAME_PLAYERS, game_id=game_id),
                RedisKeySchema.get_key(RedisKeySchema.GAME_WEBSOCKET_MAPPING, game_id=game_id),
                RedisKeySchema.get_key(RedisKeySchema.GAME_SETTINGS, game_id=game_id),
                RedisKeySchema.get_key(RedisKeySchema.GAME_ACTIVITY, game_id=game_id),
                RedisKeySchema.get_key(RedisKeySchema.GAME_STATS, game_id=game_id),
            ]

            # Delete all keys atomically
            deleted_count = await self.redis.delete(*keys_to_delete)

            # Remove from active games set
            await self.redis.srem(RedisKeySchema.ACTIVE_GAMES, game_id)

            logger.info(f"[REDIS-STATE-DELETE] Deleted game state for {game_id} ({deleted_count} keys)")
            return deleted_count > 0

        except Exception as error:
            logger.error(f"[REDIS-STATE-DELETE-ERROR] Failed to delete game state for {game_id}: {error}")
            return False

    async def add_player(self, game_id: str, player_id: str, session_id: str) -> int:
        """
        Add player to game using atomic operation.

        Args:
            game_id: Game ID
            player_id: Player ID to add
            session_id: WebSocket session ID

        Returns:
            Total number of players after addition
        """
        try:
            if not await self._ensure_connection():
                return 0

            players_key = RedisKeySchema.get_key(RedisKeySchema.GAME_PLAYERS, game_id=game_id)
            websocket_key = RedisKeySchema.get_key(RedisKeySchema.PLAYER_WEBSOCKET, player_id=player_id)
            ttl = RedisKeySchema.get_ttl("player_state")

            # Use atomic Lua script
            player_count = await self.redis.evalsha(
                self.lua_scripts['player_join'],
                2,  # Number of keys
                players_key, websocket_key,  # Keys
                player_id, session_id, str(ttl)  # Arguments
            )

            # Add to active games
            await self.redis.sadd(RedisKeySchema.ACTIVE_GAMES, game_id)

            logger.debug(f"[REDIS-STATE-PLAYER-ADD] Added player {player_id} to game {game_id} (total: {player_count})")
            return int(player_count)

        except Exception as error:
            logger.error(f"[REDIS-STATE-PLAYER-ADD-ERROR] Failed to add player {player_id} to game {game_id}: {error}")
            return 0

    async def remove_player(self, game_id: str, player_id: str) -> int:
        """
        Remove player from game.

        Args:
            game_id: Game ID
            player_id: Player ID to remove

        Returns:
            Remaining number of players
        """
        try:
            if not await self._ensure_connection():
                return 0

            players_key = RedisKeySchema.get_key(RedisKeySchema.GAME_PLAYERS, game_id=game_id)
            websocket_key = RedisKeySchema.get_key(RedisKeySchema.PLAYER_WEBSOCKET, player_id=player_id)

            # Remove player from game and clean up websocket mapping
            pipe = self.redis.pipeline()
            pipe.srem(players_key, player_id)
            pipe.delete(websocket_key)
            pipe.scard(players_key)
            results = await pipe.execute()

            player_count = results[2] if len(results) > 2 else 0

            logger.debug(f"[REDIS-STATE-PLAYER-REMOVE] Removed player {player_id} from game {game_id} (remaining: {player_count})")
            return int(player_count)

        except Exception as error:
            logger.error(f"[REDIS-STATE-PLAYER-REMOVE-ERROR] Failed to remove player {player_id} from game {game_id}: {error}")
            return 0

    async def advance_track(self, game_id: str, new_track: Track) -> int:
        """
        Advance to next track using atomic operation.

        Args:
            game_id: Game ID
            new_track: New track to set as current

        Returns:
            Number of remaining unplayed tracks
        """
        try:
            if not await self._ensure_connection():
                return 0

            played_key = RedisKeySchema.get_key(RedisKeySchema.GAME_TRACKS_PLAYED, game_id=game_id)
            unplayed_key = RedisKeySchema.get_key(RedisKeySchema.GAME_TRACKS_UNPLAYED, game_id=game_id)
            current_key = RedisKeySchema.get_key(RedisKeySchema.GAME_CURRENT_TRACK, game_id=game_id)
            stats_key = RedisKeySchema.get_key(RedisKeySchema.GAME_STATS, game_id=game_id)

            ttl = RedisKeySchema.get_ttl("game_state")
            track_data = new_track.model_dump_json()
            timestamp = str(int(datetime.now().timestamp()))

            # Use atomic Lua script
            remaining_tracks = await self.redis.evalsha(
                self.lua_scripts['track_advance'],
                4,  # Number of keys
                played_key, unplayed_key, current_key, stats_key,  # Keys
                track_data, str(ttl), timestamp  # Arguments
            )

            logger.debug(f"[REDIS-STATE-TRACK-ADVANCE] Advanced to track {new_track.name} in game {game_id} ({remaining_tracks} remaining)")
            return int(remaining_tracks)

        except Exception as error:
            logger.error(f"[REDIS-STATE-TRACK-ADVANCE-ERROR] Failed to advance track in game {game_id}: {error}")
            return 0

    async def get_active_games(self) -> List[str]:
        """Get list of active game IDs"""
        try:
            if not await self._ensure_connection():
                return []

            games = await self.redis.smembers(RedisKeySchema.ACTIVE_GAMES)
            return list(games) if games else []

        except Exception as error:
            logger.error(f"[REDIS-STATE-ACTIVE-GAMES-ERROR] Failed to get active games: {error}")
            return []

    async def get_game_stats(self, game_id: str) -> Dict[str, Any]:
        """Get game statistics from Redis"""
        try:
            if not await self._ensure_connection():
                return {}

            stats_key = RedisKeySchema.get_key(RedisKeySchema.GAME_STATS, game_id=game_id)
            stats = await self.redis.hgetall(stats_key)

            return stats if stats else {}

        except Exception as error:
            logger.error(f"[REDIS-STATE-STATS-ERROR] Failed to get stats for game {game_id}: {error}")
            return {}

    async def _ensure_connection(self) -> bool:
        """Ensure Redis connection is available"""
        if not self.is_connected:
            try:
                await self.initialize()
            except Exception:
                return False
        return self.is_connected

    async def _initialize_game_keys(self, game_id: str, ttl: int) -> None:
        """Initialize all Redis keys for a new game"""
        try:
            # Add to active games
            await self.redis.sadd(RedisKeySchema.ACTIVE_GAMES, game_id)

            # Initialize empty collections with TTL
            pipe = self.redis.pipeline()

            # Initialize stats
            stats_key = RedisKeySchema.get_key(RedisKeySchema.GAME_STATS, game_id=game_id)
            pipe.hset(stats_key, mapping={
                "tracks_played": 0,
                "players_joined": 0,
                "created_at": str(int(datetime.now().timestamp()))
            })
            pipe.expire(stats_key, ttl)

            await pipe.execute()

        except Exception as error:
            logger.error(f"[REDIS-STATE-INIT-KEYS-ERROR] Failed to initialize keys for game {game_id}: {error}")
            raise

    async def _log_operation(self, operation: StateOperation) -> None:
        """Log state operation for audit trail"""
        try:
            # Log to application logger
            logger.info(
                f"[REDIS-STATE-OP] {operation.operation_type}",
                extra={
                    "game_id": operation.game_id,
                    "user_id": operation.user_id,
                    "operation_data": operation.operation_data,
                    "timestamp": operation.timestamp.isoformat(),
                    "success": operation.success
                }
            )

            # Could also store in Redis for recent operation history
            # This is optional and depends on audit requirements

        except Exception as error:
            logger.error(f"[REDIS-STATE-LOG-ERROR] Failed to log operation: {error}")

    async def close(self) -> None:
        """Close Redis connection and cleanup resources"""
        try:
            if self.redis:
                await self.redis.close()
            if self.connection_pool:
                await self.connection_pool.disconnect()
            self.is_connected = False
            logger.info("[REDIS-STATE-CLOSE] Redis game state manager closed")
        except Exception as error:
            logger.error(f"[REDIS-STATE-CLOSE-ERROR] Error closing Redis connection: {error}")


# Global instance for application use
redis_game_state_manager = RedisGameStateManager()
