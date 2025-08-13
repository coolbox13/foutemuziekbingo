"""
Unified State Manager - Hybrid Redis/Database Architecture

This module provides a unified interface for game state management that:
- Routes ephemeral data to Redis for performance
- Routes persistent data to Database for durability
- Maintains backward compatibility with existing code
- Provides automatic state synchronization
"""

import json
import logging
import asyncio
from typing import Optional, Dict, Any, List, Union
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor

from app.game_state_manager import redis_game_state_manager, RedisGameStateManager
from app.persistent_state_manager import database_state_manager, DatabaseStateManager
from app.models import (
    RedisGameState,
    PersistentGameState,
    StateSnapshot,
    StateOperation,
    Track,
    BingoCard,
    GameSettings,
    UserPublic
)

logger = logging.getLogger("music_bingo")


class UnifiedStateManager:
    """
    Unified state manager that provides a single interface for all state operations.
    
    Architecture:
    - Redis: Real-time ephemeral data (active games, current tracks, player sessions)
    - Database: Persistent data (saved games, history, user preferences)
    - Automatic routing based on data type and operation
    - State synchronization between storage backends
    - Backward compatibility with existing ThreadSafeGameState API
    """
    
    def __init__(self):
        """Initialize unified state manager"""
        self.redis_manager: RedisGameStateManager = redis_game_state_manager
        self.db_manager: DatabaseStateManager = database_state_manager
        
        # Configuration
        self.auto_sync_enabled = True
        self.sync_interval_seconds = 300  # 5 minutes
        self.checkpoint_interval_seconds = 1800  # 30 minutes
        
        # State management
        self.is_initialized = False
        self.sync_task: Optional[asyncio.Task] = None
        self.checkpoint_task: Optional[asyncio.Task] = None
        
        # Performance monitoring
        self.operation_stats = {
            "redis_operations": 0,
            "db_operations": 0,
            "sync_operations": 0,
            "failed_operations": 0
        }
        
    async def initialize(self) -> None:
        """Initialize both Redis and Database managers"""
        try:
            logger.info("[UNIFIED-STATE-INIT] Initializing unified state manager")
            
            # Initialize both backends
            await asyncio.gather(
                self.redis_manager.initialize(),
                self.db_manager.initialize()
            )
            
            # Start background tasks
            if self.auto_sync_enabled:
                self.sync_task = asyncio.create_task(self._sync_loop())
                self.checkpoint_task = asyncio.create_task(self._checkpoint_loop())
            
            self.is_initialized = True
            logger.info("[UNIFIED-STATE-INIT] Unified state manager initialized successfully")
            
        except Exception as error:
            logger.error(f"[UNIFIED-STATE-INIT-ERROR] Failed to initialize unified state manager: {error}")
            raise
    
    async def health_check(self) -> Dict[str, Any]:
        """Comprehensive health check for both backends"""
        try:
            redis_health, db_health = await asyncio.gather(
                self.redis_manager.health_check(),
                self.db_manager.health_check(),
                return_exceptions=True
            )
            
            health_status = {
                "unified_manager": self.is_initialized,
                "redis_backend": redis_health if not isinstance(redis_health, Exception) else False,
                "database_backend": db_health if not isinstance(db_health, Exception) else False,
                "sync_enabled": self.auto_sync_enabled,
                "operation_stats": self.operation_stats.copy(),
                "last_check": datetime.now().isoformat()
            }
            
            health_status["overall_healthy"] = (
                health_status["unified_manager"] and
                health_status["redis_backend"] and
                health_status["database_backend"]
            )
            
            return health_status
            
        except Exception as error:
            logger.error(f"[UNIFIED-STATE-HEALTH-ERROR] Health check failed: {error}")
            return {
                "overall_healthy": False,
                "error": str(error),
                "last_check": datetime.now().isoformat()
            }
    
    # ====================================
    # BACKWARD COMPATIBILITY API
    # ====================================
    
    async def get_state(self) -> Dict[str, Any]:
        """
        Get complete game state (backward compatibility method).
        
        Returns:
            Combined state from Redis and Database
        """
        try:
            # For backward compatibility, we need to determine which game to get
            # This is a simplified implementation - in production you'd need a way
            # to specify which game or get the "current" active game
            
            active_games = await self.redis_manager.get_active_games()
            if not active_games:
                # Return default empty state for backward compatibility
                return {
                    "played_tracks": [],
                    "unplayed_tracks": [],
                    "cards": {},
                    "bingo_mode": "rowcoldiag",
                    "current_playlist": None,
                    "num_tracks": 0,
                }
            
            # Get state for the first active game (simplified)
            game_id = active_games[0]
            snapshot = await self.get_game_snapshot(game_id)
            
            if not snapshot:
                return {
                    "played_tracks": [],
                    "unplayed_tracks": [],
                    "cards": {},
                    "bingo_mode": "rowcoldiag",
                    "current_playlist": None,
                    "num_tracks": 0,
                }
            
            # Convert to old format for backward compatibility
            return self._convert_to_legacy_format(snapshot)
            
        except Exception as error:
            logger.error(f"[UNIFIED-STATE-GET-LEGACY-ERROR] Failed to get legacy state: {error}")
            return {
                "played_tracks": [],
                "unplayed_tracks": [],
                "cards": {},
                "bingo_mode": "rowcoldiag",
                "current_playlist": None,
                "num_tracks": 0,
            }
    
    async def update_state(self, update_func) -> Dict[str, Any]:
        """
        Update game state (backward compatibility method).
        
        Args:
            update_func: Function that updates the state dict
            
        Returns:
            Updated state dict
        """
        try:
            # This is a complex backward compatibility method
            # In a real migration, you'd gradually update callers to use the new API
            
            # Get current state
            current_state = await self.get_state()
            
            # Apply update function
            update_func(current_state)
            
            # Extract game information from updated state
            game_id = current_state.get("current_playlist", {}).get("id")
            if not game_id:
                # Create a new game if none exists
                game_id = f"legacy_game_{int(datetime.now().timestamp())}"
            
            # Convert back to new format and save
            await self._save_legacy_state(game_id, current_state)
            
            return current_state
            
        except Exception as error:
            logger.error(f"[UNIFIED-STATE-UPDATE-LEGACY-ERROR] Failed to update legacy state: {error}")
            raise
    
    # ====================================
    # NEW UNIFIED API
    # ====================================
    
    async def create_game_state(self, game_id: str, initial_tracks: List[Track], 
                              settings: GameSettings, created_by: str) -> StateSnapshot:
        """
        Create new game state in both Redis and Database.
        
        Args:
            game_id: Game ID
            initial_tracks: Initial track list
            settings: Game settings
            created_by: User who created the game
            
        Returns:
            Complete state snapshot
        """
        try:
            logger.info(f"[UNIFIED-STATE-CREATE] Creating game state for {game_id}")
            
            # Create ephemeral state in Redis
            redis_state = await self.redis_manager.create_game_state(
                game_id, initial_tracks, settings
            )
            
            # Create persistent state in Database
            state_data = {
                "initial_tracks": [track.model_dump() for track in initial_tracks],
                "settings": settings.model_dump(),
                "created_at": datetime.now().isoformat(),
                "game_id": game_id
            }
            
            persistent_state = await self.db_manager.save_game_state(
                game_id=game_id,
                state_data=state_data,
                created_by=created_by,
                description="Initial game state",
                is_checkpoint=True
            )
            
            # Create unified snapshot
            snapshot = StateSnapshot(
                game_id=game_id,
                ephemeral_state=redis_state,
                persistent_state=persistent_state,
                sync_status="synced",
                last_sync=datetime.now()
            )
            
            self.operation_stats["redis_operations"] += 1
            self.operation_stats["db_operations"] += 1
            
            logger.info(f"[UNIFIED-STATE-CREATE] Successfully created game state for {game_id}")
            return snapshot
            
        except Exception as error:
            self.operation_stats["failed_operations"] += 1
            logger.error(f"[UNIFIED-STATE-CREATE-ERROR] Failed to create game state for {game_id}: {error}")
            raise
    
    async def get_game_snapshot(self, game_id: str) -> Optional[StateSnapshot]:
        """
        Get complete game state snapshot from both backends.
        
        Args:
            game_id: Game ID
            
        Returns:
            Complete state snapshot or None if not found
        """
        try:
            # Get from both backends concurrently
            redis_state, persistent_state = await asyncio.gather(
                self.redis_manager.get_game_state(game_id),
                self.db_manager.get_game_state(game_id),
                return_exceptions=True
            )
            
            # Handle exceptions
            if isinstance(redis_state, Exception):
                logger.warning(f"[UNIFIED-STATE-GET-REDIS-ERROR] Redis error for game {game_id}: {redis_state}")
                redis_state = None
            
            if isinstance(persistent_state, Exception):
                logger.warning(f"[UNIFIED-STATE-GET-DB-ERROR] Database error for game {game_id}: {persistent_state}")
                persistent_state = None
            
            # Return None if neither backend has data
            if not redis_state and not persistent_state:
                return None
            
            # Create snapshot
            snapshot = StateSnapshot(
                game_id=game_id,
                ephemeral_state=redis_state,
                persistent_state=persistent_state,
                sync_status="synced" if (redis_state and persistent_state) else "partial",
                last_sync=datetime.now()
            )
            
            logger.debug(f"[UNIFIED-STATE-GET] Retrieved state snapshot for {game_id}")
            return snapshot
            
        except Exception as error:
            logger.error(f"[UNIFIED-STATE-GET-ERROR] Failed to get state snapshot for {game_id}: {error}")
            return None
    
    async def update_game_state(self, game_id: str, updates: Dict[str, Any], user_id: str = None) -> bool:
        """
        Update game state in appropriate backend(s).
        
        Args:
            game_id: Game ID
            updates: State updates to apply
            user_id: User performing the update
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Determine which backends to update based on update type
            needs_redis = self._needs_redis_update(updates)
            needs_db = self._needs_db_update(updates)
            
            success = True
            
            # Update Redis if needed
            if needs_redis:
                redis_state = await self.redis_manager.get_game_state(game_id)
                if redis_state:
                    # Apply updates to Redis state
                    updated_redis_state = self._apply_updates_to_redis_state(redis_state, updates)
                    redis_success = await self.redis_manager.update_game_state(game_id, updated_redis_state)
                    if not redis_success:
                        success = False
                    self.operation_stats["redis_operations"] += 1
            
            # Update Database if needed (for persistent changes)
            if needs_db:
                await self.db_manager.save_game_state(
                    game_id=game_id,
                    state_data=updates,
                    created_by=user_id or "system",
                    description="State update",
                    is_checkpoint=False
                )
                self.operation_stats["db_operations"] += 1
            
            if not success:
                self.operation_stats["failed_operations"] += 1
            
            logger.debug(f"[UNIFIED-STATE-UPDATE] Updated game state for {game_id} (Redis: {needs_redis}, DB: {needs_db})")
            return success
            
        except Exception as error:
            self.operation_stats["failed_operations"] += 1
            logger.error(f"[UNIFIED-STATE-UPDATE-ERROR] Failed to update game state for {game_id}: {error}")
            return False
    
    async def delete_game_state(self, game_id: str) -> bool:
        """
        Delete game state from both backends.
        
        Args:
            game_id: Game ID to delete
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Delete from both backends concurrently
            redis_success, db_count = await asyncio.gather(
                self.redis_manager.delete_game_state(game_id),
                self.db_manager.delete_game_states(game_id),
                return_exceptions=True
            )
            
            # Handle exceptions
            if isinstance(redis_success, Exception):
                logger.error(f"[UNIFIED-STATE-DELETE-REDIS-ERROR] Redis deletion failed for {game_id}: {redis_success}")
                redis_success = False
            
            if isinstance(db_count, Exception):
                logger.error(f"[UNIFIED-STATE-DELETE-DB-ERROR] Database deletion failed for {game_id}: {db_count}")
                db_count = 0
            
            overall_success = redis_success or db_count > 0
            
            if overall_success:
                logger.info(f"[UNIFIED-STATE-DELETE] Deleted game state for {game_id}")
            else:
                self.operation_stats["failed_operations"] += 1
            
            return overall_success
            
        except Exception as error:
            self.operation_stats["failed_operations"] += 1
            logger.error(f"[UNIFIED-STATE-DELETE-ERROR] Failed to delete game state for {game_id}: {error}")
            return False
    
    # ====================================
    # PLAYER MANAGEMENT
    # ====================================
    
    async def add_player(self, game_id: str, player_id: str, session_id: str) -> int:
        """Add player to game (Redis operation)"""
        try:
            player_count = await self.redis_manager.add_player(game_id, player_id, session_id)
            self.operation_stats["redis_operations"] += 1
            return player_count
        except Exception as error:
            self.operation_stats["failed_operations"] += 1
            logger.error(f"[UNIFIED-STATE-ADD-PLAYER-ERROR] Failed to add player {player_id} to game {game_id}: {error}")
            return 0
    
    async def remove_player(self, game_id: str, player_id: str) -> int:
        """Remove player from game (Redis operation)"""
        try:
            player_count = await self.redis_manager.remove_player(game_id, player_id)
            self.operation_stats["redis_operations"] += 1
            return player_count
        except Exception as error:
            self.operation_stats["failed_operations"] += 1
            logger.error(f"[UNIFIED-STATE-REMOVE-PLAYER-ERROR] Failed to remove player {player_id} from game {game_id}: {error}")
            return 0
    
    async def advance_track(self, game_id: str, new_track: Track) -> int:
        """Advance to next track (Redis operation)"""
        try:
            remaining_tracks = await self.redis_manager.advance_track(game_id, new_track)
            self.operation_stats["redis_operations"] += 1
            return remaining_tracks
        except Exception as error:
            self.operation_stats["failed_operations"] += 1
            logger.error(f"[UNIFIED-STATE-ADVANCE-TRACK-ERROR] Failed to advance track in game {game_id}: {error}")
            return 0
    
    # ====================================
    # PERSISTENCE OPERATIONS
    # ====================================
    
    async def save_game_checkpoint(self, game_id: str, user_id: str, description: str = None) -> bool:
        """Save current game state as a checkpoint"""
        try:
            # Get current Redis state
            redis_state = await self.redis_manager.get_game_state(game_id)
            if not redis_state:
                return False
            
            # Save as checkpoint in database
            await self.db_manager.save_game_state(
                game_id=game_id,
                state_data=redis_state.model_dump(),
                created_by=user_id,
                description=description or "Manual checkpoint",
                is_checkpoint=True
            )
            
            self.operation_stats["db_operations"] += 1
            logger.info(f"[UNIFIED-STATE-CHECKPOINT] Saved checkpoint for game {game_id}")
            return True
            
        except Exception as error:
            self.operation_stats["failed_operations"] += 1
            logger.error(f"[UNIFIED-STATE-CHECKPOINT-ERROR] Failed to save checkpoint for game {game_id}: {error}")
            return False
    
    async def get_game_history(self, game_id: str, limit: int = 50) -> List[PersistentGameState]:
        """Get game state history from database"""
        try:
            history = await self.db_manager.get_game_history(game_id, limit)
            self.operation_stats["db_operations"] += 1
            return history
        except Exception as error:
            self.operation_stats["failed_operations"] += 1
            logger.error(f"[UNIFIED-STATE-HISTORY-ERROR] Failed to get history for game {game_id}: {error}")
            return []
    
    # ====================================
    # SYNCHRONIZATION
    # ====================================
    
    async def sync_game_state(self, game_id: str) -> bool:
        """Manually synchronize game state between Redis and Database"""
        try:
            # Get current Redis state
            redis_state = await self.redis_manager.get_game_state(game_id)
            if not redis_state:
                logger.warning(f"[UNIFIED-STATE-SYNC] No Redis state found for game {game_id}")
                return False
            
            # Save current state as checkpoint in database
            await self.db_manager.save_game_state(
                game_id=game_id,
                state_data=redis_state.model_dump(),
                created_by="system",
                description="Automatic sync checkpoint",
                is_checkpoint=True
            )
            
            self.operation_stats["sync_operations"] += 1
            logger.debug(f"[UNIFIED-STATE-SYNC] Synchronized state for game {game_id}")
            return True
            
        except Exception as error:
            self.operation_stats["failed_operations"] += 1
            logger.error(f"[UNIFIED-STATE-SYNC-ERROR] Failed to sync state for game {game_id}: {error}")
            return False
    
    async def _sync_loop(self) -> None:
        """Background task for automatic state synchronization"""
        while self.auto_sync_enabled:
            try:
                await asyncio.sleep(self.sync_interval_seconds)
                
                # Get all active games
                active_games = await self.redis_manager.get_active_games()
                
                # Sync each game
                for game_id in active_games:
                    await self.sync_game_state(game_id)
                
                logger.debug(f"[UNIFIED-STATE-SYNC-LOOP] Synchronized {len(active_games)} active games")
                
            except Exception as error:
                logger.error(f"[UNIFIED-STATE-SYNC-LOOP-ERROR] Sync loop error: {error}")
                await asyncio.sleep(60)  # Wait before retrying
    
    async def _checkpoint_loop(self) -> None:
        """Background task for automatic checkpoint creation"""
        while self.auto_sync_enabled:
            try:
                await asyncio.sleep(self.checkpoint_interval_seconds)
                
                # Get all active games
                active_games = await self.redis_manager.get_active_games()
                
                # Create checkpoint for each game
                for game_id in active_games:
                    await self.save_game_checkpoint(
                        game_id, 
                        "system", 
                        "Automatic checkpoint"
                    )
                
                logger.debug(f"[UNIFIED-STATE-CHECKPOINT-LOOP] Created checkpoints for {len(active_games)} active games")
                
            except Exception as error:
                logger.error(f"[UNIFIED-STATE-CHECKPOINT-LOOP-ERROR] Checkpoint loop error: {error}")
                await asyncio.sleep(300)  # Wait before retrying
    
    # ====================================
    # HELPER METHODS
    # ====================================
    
    def _needs_redis_update(self, updates: Dict[str, Any]) -> bool:
        """Determine if updates need to be applied to Redis"""
        redis_keys = {
            "played_tracks", "unplayed_tracks", "current_track", 
            "active_players", "websocket_sessions", "bingo_validations"
        }
        return any(key in updates for key in redis_keys)
    
    def _needs_db_update(self, updates: Dict[str, Any]) -> bool:
        """Determine if updates need to be applied to Database"""
        db_keys = {
            "cards", "final_state", "game_completed", "settings"
        }
        return any(key in updates for key in db_keys)
    
    def _apply_updates_to_redis_state(self, redis_state: RedisGameState, updates: Dict[str, Any]) -> RedisGameState:
        """Apply updates to Redis state object"""
        # Create a copy and apply updates
        state_dict = redis_state.model_dump()
        
        for key, value in updates.items():
            if key in state_dict:
                state_dict[key] = value
        
        return RedisGameState(**state_dict)
    
    def _convert_to_legacy_format(self, snapshot: StateSnapshot) -> Dict[str, Any]:
        """Convert state snapshot to legacy format for backward compatibility"""
        legacy_state = {
            "played_tracks": [],
            "unplayed_tracks": [],
            "cards": {},
            "bingo_mode": "rowcoldiag",
            "current_playlist": None,
            "num_tracks": 0,
        }
        
        if snapshot.ephemeral_state:
            legacy_state.update({
                "played_tracks": [track.model_dump() for track in snapshot.ephemeral_state.played_tracks],
                "unplayed_tracks": [track.model_dump() for track in snapshot.ephemeral_state.unplayed_tracks],
                "num_tracks": len(snapshot.ephemeral_state.played_tracks) + len(snapshot.ephemeral_state.unplayed_tracks),
                "bingo_mode": snapshot.ephemeral_state.settings.bingo_mode.value
            })
        
        if snapshot.cards_state:
            cards_dict = {}
            for card in snapshot.cards_state:
                cards_dict[card.id] = card.model_dump()
            legacy_state["cards"] = cards_dict
        
        return legacy_state
    
    async def _save_legacy_state(self, game_id: str, legacy_state: Dict[str, Any]) -> None:
        """Save legacy format state to new backends"""
        # This is a simplified conversion - in practice you'd need more sophisticated mapping
        try:
            # Extract tracks
            played_tracks = [Track(**track) for track in legacy_state.get("played_tracks", [])]
            unplayed_tracks = [Track(**track) for track in legacy_state.get("unplayed_tracks", [])]
            
            # Get or create Redis state
            redis_state = await self.redis_manager.get_game_state(game_id)
            if not redis_state:
                # Create new state
                settings = GameSettings()  # Default settings
                redis_state = await self.redis_manager.create_game_state(game_id, unplayed_tracks, settings)
            else:
                # Update existing state
                redis_state.played_tracks = played_tracks
                redis_state.unplayed_tracks = unplayed_tracks
                await self.redis_manager.update_game_state(game_id, redis_state)
            
        except Exception as error:
            logger.error(f"[UNIFIED-STATE-SAVE-LEGACY-ERROR] Failed to save legacy state for {game_id}: {error}")
            raise
    
    async def close(self) -> None:
        """Close unified state manager and all backends"""
        try:
            # Stop background tasks
            if self.sync_task and not self.sync_task.done():
                self.sync_task.cancel()
            if self.checkpoint_task and not self.checkpoint_task.done():
                self.checkpoint_task.cancel()
            
            # Close backends
            await asyncio.gather(
                self.redis_manager.close(),
                # Database manager doesn't have a close method currently
                return_exceptions=True
            )
            
            self.is_initialized = False
            logger.info("[UNIFIED-STATE-CLOSE] Unified state manager closed")
            
        except Exception as error:
            logger.error(f"[UNIFIED-STATE-CLOSE-ERROR] Error closing unified state manager: {error}")


# Global instance for application use
unified_state_manager = UnifiedStateManager()
