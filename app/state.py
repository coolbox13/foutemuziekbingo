"""
State Management Module - Hybrid Redis/Database Architecture

This module provides backward compatibility with the original file-based state management
while internally using the new Redis/Database hybrid architecture for production scalability.

MIGRATION STATUS: In progress - maintaining backward compatibility during transition
"""

import json
import os
import copy
import asyncio
import logging
from threading import Lock
from typing import Dict, Any, Optional, Callable

from app.unified_state_manager import unified_state_manager

logger = logging.getLogger("music_bingo")

# Legacy file paths (kept for migration purposes)
PLAYLISTS_FILE = "playlists.json"
GAME_STATE_FILE = "game_state.json"

# Default game state structure (kept for backward compatibility)
DEFAULT_GAME_STATE = {
    "played_tracks": [],
    "unplayed_tracks": [],
    "cards": {},
    "bingo_mode": "rowcoldiag",
    "current_playlist": None,
    "num_tracks": 0,
}


class ThreadSafeGameState:
    """
    Backward-compatible thread-safe game state manager.

    This class maintains the same API as the original file-based implementation
    but internally uses the new Redis/Database hybrid architecture.

    IMPORTANT: This is a transition class. New code should use unified_state_manager directly.
    """

    _instance = None
    _lock = Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance.__initialized = False
        return cls._instance

    def __init__(self):
        if not getattr(self, "__initialized", False):
            self.state_lock = Lock()
            self._unified_manager = unified_state_manager
            self._is_migrated = False
            self._migration_in_progress = False

            # Initialize the unified manager asynchronously
            self._initialization_task = None

            # Try to load legacy state for migration
            self.state = self.load_state()
            self.__initialized = True

            # Start async initialization
            self._ensure_async_initialized()

    def _ensure_async_initialized(self):
        """Ensure async components are initialized"""
        try:
            # Try to get the current event loop
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If we're in an async context, schedule initialization
                if not self._initialization_task or self._initialization_task.done():
                    self._initialization_task = asyncio.create_task(self._async_initialize())
            else:
                # If not in async context, create a new loop
                asyncio.run(self._async_initialize())
        except RuntimeError:
            # No event loop, will initialize when first async method is called
            logger.info("[STATE-LEGACY] No event loop available, deferring async initialization")

    async def _async_initialize(self):
        """Initialize the unified state manager asynchronously"""
        try:
            if not self._unified_manager.is_initialized:
                await self._unified_manager.initialize()
                logger.info("[STATE-LEGACY] Unified state manager initialized")

                # Migrate legacy state if it exists and hasn't been migrated
                if not self._is_migrated and not self._migration_in_progress:
                    await self._migrate_legacy_state()

        except Exception as error:
            logger.error(f"[STATE-LEGACY-INIT-ERROR] Failed to initialize unified state manager: {error}")

    async def _migrate_legacy_state(self):
        """Migrate legacy file-based state to new architecture"""
        try:
            self._migration_in_progress = True
            logger.info("[STATE-MIGRATION] Starting legacy state migration")

            # Check if legacy state file exists and has data
            if os.path.exists(GAME_STATE_FILE):
                with open(GAME_STATE_FILE, 'r') as f:
                    legacy_data = json.load(f)

                # Only migrate if there's actual game data
                if (legacy_data.get("unplayed_tracks") or
                    legacy_data.get("played_tracks") or
                    legacy_data.get("cards")):

                    # Create a migration game ID
                    migration_game_id = f"migrated_legacy_{int(asyncio.get_event_loop().time())}"

                    # Use the database manager to store the migration
                    await self._unified_manager.db_manager.save_game_state(
                        game_id=migration_game_id,
                        state_data=legacy_data,
                        created_by="system",
                        description="Migrated from legacy file-based state",
                        is_checkpoint=True
                    )

                    # Backup the original file
                    backup_file = f"{GAME_STATE_FILE}.migrated.backup"
                    os.rename(GAME_STATE_FILE, backup_file)

                    logger.info(f"[STATE-MIGRATION] Successfully migrated legacy state to game {migration_game_id}")
                    logger.info(f"[STATE-MIGRATION] Legacy file backed up to {backup_file}")

            self._is_migrated = True
            self._migration_in_progress = False

        except Exception as error:
            logger.error(f"[STATE-MIGRATION-ERROR] Failed to migrate legacy state: {error}")
            self._migration_in_progress = False

    def load_state(self):
        """Load game state from file (legacy compatibility method)"""
        try:
            with open(GAME_STATE_FILE, "r") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.warning(
                f"[STATE-LEGACY-LOAD] Unable to load game state from {GAME_STATE_FILE}: "
                f"{e}. Using default state."
            )
            return self.reset_to_default()

    def save_state(self, state):
        """Save game state to file (legacy compatibility method)"""
        try:
            # For backward compatibility, still save to file during transition
            with open(GAME_STATE_FILE, "w") as f:
                json.dump(state, f, indent=4)

            # Also trigger async save to new system if available
            self._trigger_async_save(state)

        except Exception as error:
            logger.error(f"[STATE-LEGACY-SAVE-ERROR] Failed to save legacy state: {error}")

    def _trigger_async_save(self, state):
        """Trigger async save to new state management system"""
        try:
            # Get the current event loop if it exists
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # Schedule the async save
                    asyncio.create_task(self._async_save_state(state))
            except RuntimeError:
                # No event loop running, skip async save for now
                pass
        except Exception as error:
            logger.error(f"[STATE-LEGACY-ASYNC-SAVE-ERROR] Failed to trigger async save: {error}")

    async def _async_save_state(self, state):
        """Save state to new unified system asynchronously"""
        try:
            if not self._unified_manager.is_initialized:
                await self._unified_manager.initialize()

            # Extract or create game ID
            game_id = state.get("current_playlist", {}).get("id")
            if not game_id:
                game_id = f"legacy_session_{int(asyncio.get_event_loop().time())}"

            # Update the unified state
            await self._unified_manager.update_game_state(
                game_id=game_id,
                updates=state,
                user_id="legacy_system"
            )

            logger.debug(f"[STATE-LEGACY-ASYNC-SAVE] Saved state to unified system for game {game_id}")

        except Exception as error:
            logger.error(f"[STATE-LEGACY-ASYNC-SAVE-ERROR] Failed to save to unified system: {error}")

    def update_state(self, update_func: Callable[[Dict[str, Any]], None]) -> Dict[str, Any]:
        """
        Thread-safe state update (legacy compatibility method).

        Args:
            update_func: Function that modifies the state dictionary in place

        Returns:
            Deep copy of the updated state
        """
        with self.state_lock:
            # Apply the update function to current state
            update_func(self.state)

            # Save the updated state
            self.save_state(self.state)

            # Return deep copy for thread safety
            return copy.deepcopy(self.state)

    def get_state(self) -> Dict[str, Any]:
        """Thread-safe state retrieval (legacy compatibility method)"""
        with self.state_lock:
            return copy.deepcopy(self.state)

    def reset_to_default(self) -> Dict[str, Any]:
        """Reset state to default values (legacy compatibility method)"""
        self.state = DEFAULT_GAME_STATE.copy()
        self.save_state(self.state)
        return self.state

    # New methods for accessing unified state manager
    async def get_unified_manager(self):
        """Get the unified state manager instance"""
        if not self._unified_manager.is_initialized:
            await self._unified_manager.initialize()
        return self._unified_manager

    async def migrate_to_unified(self, game_id: str, user_id: str = "migration_user") -> bool:
        """
        Manually trigger migration of current state to unified system.

        Args:
            game_id: Game ID to use for the migration
            user_id: User ID performing the migration

        Returns:
            True if migration successful, False otherwise
        """
        try:
            if not self._unified_manager.is_initialized:
                await self._unified_manager.initialize()

            current_state = self.get_state()

            # Save current state to unified system
            await self._unified_manager.update_game_state(
                game_id=game_id,
                updates=current_state,
                user_id=user_id
            )

            logger.info(f"[STATE-MIGRATION-MANUAL] Successfully migrated state to game {game_id}")
            return True

        except Exception as error:
            logger.error(f"[STATE-MIGRATION-MANUAL-ERROR] Failed to migrate state: {error}")
            return False


def load_playlists():
    """Load playlists from the JSON file (legacy compatibility function)"""
    if not os.path.exists(PLAYLISTS_FILE):
        save_playlists([])
        return []
    try:
        with open(PLAYLISTS_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.warning(f"[STATE-PLAYLISTS-LOAD] Unable to load playlists from {PLAYLISTS_FILE}: {e}")
        save_playlists([])
        return []


def save_playlists(playlists):
    """Save playlists to the JSON file (legacy compatibility function)"""
    try:
        with open(PLAYLISTS_FILE, "w") as f:
            json.dump(playlists, f, indent=4)
    except Exception as error:
        logger.error(f"[STATE-PLAYLISTS-SAVE-ERROR] Failed to save playlists: {error}")


# Create the singleton instance (legacy compatibility)
game_state = ThreadSafeGameState()

# Export the unified manager for new code
__all__ = ['game_state', 'unified_state_manager', 'load_playlists', 'save_playlists']
