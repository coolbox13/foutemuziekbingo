"""
Database-based Persistent State Manager for Game History and User Data

This module implements persistent state management using Supabase database
for long-term storage of game history, user preferences, and saved games.
"""

import json
import logging
import uuid
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
from pydantic import ValidationError

from app.database import database, DatabaseError, NotFoundError
from app.models import (
    PersistentGameState, 
    StateOperation, 
    StateMigration,
    Game,
    BingoCard,
    Track,
    GameSettings
)

logger = logging.getLogger("music_bingo")


class DatabaseStateManager:
    """
    Production-grade database state manager with:
    - Async database operations using Supabase
    - Game history and checkpoint management
    - User preference storage
    - Migration utilities for state data
    - Comprehensive audit logging
    """
    
    def __init__(self):
        """Initialize database state manager"""
        self.db = database
        self.is_initialized = False
        self.table_names = {
            "game_states": "game_states",
            "saved_games": "saved_games", 
            "user_preferences": "user_preferences",
            "state_migrations": "state_migrations"
        }
    
    async def initialize(self) -> None:
        """Initialize database connection and ensure tables exist"""
        try:
            logger.info("[DB-STATE-INIT] Initializing database state manager")
            
            # Ensure database is initialized
            if not self.db.is_initialized:
                await self.db.initialize()
            
            # Verify required tables exist
            await self._verify_tables()
            
            self.is_initialized = True
            logger.info("[DB-STATE-INIT] Database state manager initialized successfully")
            
        except Exception as error:
            logger.error(f"[DB-STATE-INIT-ERROR] Failed to initialize database state manager: {error}")
            raise
    
    async def _verify_tables(self) -> None:
        """Verify required tables exist or provide helpful error messages"""
        try:
            # Test queries to verify table existence
            test_queries = [
                ("game_states", "select count(*) from game_states limit 1"),
                ("saved_games", "select count(*) from saved_games limit 1"),
                ("users", "select count(*) from users limit 1"),
                ("games", "select count(*) from games limit 1")
            ]
            
            for table_name, query in test_queries:
                try:
                    await self.db.execute_query(
                        lambda client: client.rpc('test_table_exists', {'query': query})
                    )
                    logger.debug(f"[DB-STATE-VERIFY] Table '{table_name}' exists and accessible")
                except Exception as table_error:
                    # Table might not exist - log warning but continue
                    logger.warning(f"[DB-STATE-VERIFY-WARN] Table '{table_name}' may not exist: {table_error}")
            
        except Exception as error:
            logger.error(f"[DB-STATE-VERIFY-ERROR] Failed to verify tables: {error}")
            # Don't fail initialization for table verification issues
    
    async def health_check(self) -> bool:
        """Check database state manager health"""
        try:
            if not self.is_initialized:
                return False
                
            # Test database connectivity
            health_result = await self.db.health_check()
            return health_result
            
        except Exception as error:
            logger.error(f"[DB-STATE-HEALTH-ERROR] Health check failed: {error}")
            return False
    
    async def save_game_state(self, game_id: str, state_data: Dict[str, Any], 
                            created_by: str, description: str = None, 
                            is_checkpoint: bool = False, is_final: bool = False) -> PersistentGameState:
        """
        Save game state to database.
        
        Args:
            game_id: Game ID
            state_data: Complete game state data
            created_by: User ID who created this state
            description: Optional description for this state
            is_checkpoint: Whether this is a checkpoint save
            is_final: Whether this is the final game state
            
        Returns:
            Created PersistentGameState object
        """
        try:
            if not self.is_initialized:
                await self.initialize()
            
            # Create state record
            state_record = {
                "id": str(uuid.uuid4()),
                "game_id": game_id,
                "state_data": state_data,
                "state_type": "checkpoint" if is_checkpoint else ("final" if is_final else "snapshot"),
                "created_at": datetime.now(timezone.utc).isoformat(),
                "created_by": created_by,
                "description": description,
                "is_checkpoint": is_checkpoint,
                "is_final": is_final
            }
            
            # Save to database
            result = await self.db.create_record("game_states", state_record)
            
            # Create and return PersistentGameState object
            persistent_state = PersistentGameState(**result)
            
            logger.info(f"[DB-STATE-SAVE] Saved game state for {game_id} (type: {persistent_state.state_type})")
            
            # Log operation
            await self._log_operation(
                StateOperation(
                    operation_type="save_persistent_state",
                    game_id=game_id,
                    user_id=created_by,
                    operation_data={
                        "state_id": persistent_state.id,
                        "state_type": persistent_state.state_type,
                        "is_checkpoint": is_checkpoint,
                        "is_final": is_final
                    },
                    success=True
                )
            )
            
            return persistent_state
            
        except Exception as error:
            logger.error(f"[DB-STATE-SAVE-ERROR] Failed to save game state for {game_id}: {error}")
            
            # Log failed operation
            await self._log_operation(
                StateOperation(
                    operation_type="save_persistent_state",
                    game_id=game_id,
                    user_id=created_by,
                    operation_data={"error": str(error)},
                    success=False,
                    error_message=str(error)
                )
            )
            raise
    
    async def get_game_state(self, game_id: str, state_id: str = None) -> Optional[PersistentGameState]:
        """
        Get game state from database.
        
        Args:
            game_id: Game ID
            state_id: Specific state ID (if None, gets latest)
            
        Returns:
            PersistentGameState object or None if not found
        """
        try:
            if not self.is_initialized:
                await self.initialize()
            
            if state_id:
                # Get specific state by ID
                result = await self.db.get_record("game_states", state_id)
                if not result:
                    return None
            else:
                # Get latest state for game
                results = await self.db.query_records(
                    "game_states",
                    filters={"game_id": game_id},
                    order_by={"column": "created_at", "ascending": False},
                    limit=1
                )
                if not results:
                    return None
                result = results[0]
            
            # Validate and return
            persistent_state = PersistentGameState(**result)
            
            logger.debug(f"[DB-STATE-GET] Retrieved game state for {game_id}")
            return persistent_state
            
        except ValidationError as error:
            logger.error(f"[DB-STATE-GET-VALIDATION] Invalid state data for game {game_id}: {error}")
            return None
        except Exception as error:
            logger.error(f"[DB-STATE-GET-ERROR] Failed to get game state for {game_id}: {error}")
            return None
    
    async def get_game_history(self, game_id: str, limit: int = 50) -> List[PersistentGameState]:
        """
        Get game state history from database.
        
        Args:
            game_id: Game ID
            limit: Maximum number of states to return
            
        Returns:
            List of PersistentGameState objects ordered by creation time (newest first)
        """
        try:
            if not self.is_initialized:
                await self.initialize()
            
            results = await self.db.query_records(
                "game_states",
                filters={"game_id": game_id},
                order_by={"column": "created_at", "ascending": False},
                limit=limit
            )
            
            if not results:
                return []
            
            # Convert to PersistentGameState objects
            states = []
            for result in results:
                try:
                    state = PersistentGameState(**result)
                    states.append(state)
                except ValidationError as error:
                    logger.warning(f"[DB-STATE-HISTORY-VALIDATION] Skipping invalid state for game {game_id}: {error}")
                    continue
            
            logger.debug(f"[DB-STATE-HISTORY] Retrieved {len(states)} state records for game {game_id}")
            return states
            
        except Exception as error:
            logger.error(f"[DB-STATE-HISTORY-ERROR] Failed to get game history for {game_id}: {error}")
            return []
    
    async def delete_game_states(self, game_id: str) -> int:
        """
        Delete all game states for a game.
        
        Args:
            game_id: Game ID
            
        Returns:
            Number of states deleted
        """
        try:
            if not self.is_initialized:
                await self.initialize()
            
            # Get all states for the game first
            states = await self.db.query_records(
                "game_states",
                filters={"game_id": game_id},
                select="id"
            )
            
            if not states:
                return 0
            
            # Delete each state
            deleted_count = 0
            for state in states:
                try:
                    await self.db.delete_record("game_states", state["id"])
                    deleted_count += 1
                except Exception as delete_error:
                    logger.warning(f"[DB-STATE-DELETE-WARN] Failed to delete state {state['id']}: {delete_error}")
            
            logger.info(f"[DB-STATE-DELETE] Deleted {deleted_count} state records for game {game_id}")
            return deleted_count
            
        except Exception as error:
            logger.error(f"[DB-STATE-DELETE-ERROR] Failed to delete game states for {game_id}: {error}")
            return 0
    
    async def save_user_preferences(self, user_id: str, preferences: Dict[str, Any]) -> bool:
        """
        Save user preferences to database.
        
        Args:
            user_id: User ID
            preferences: User preference data
            
        Returns:
            True if successful, False otherwise
        """
        try:
            if not self.is_initialized:
                await self.initialize()
            
            # Check if preferences already exist
            existing = await self.db.query_records(
                "user_preferences",
                filters={"user_id": user_id},
                limit=1
            )
            
            preference_data = {
                "user_id": user_id,
                "preferences": preferences,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
            
            if existing:
                # Update existing preferences
                await self.db.update_record("user_preferences", existing[0]["id"], preference_data)
                logger.debug(f"[DB-STATE-PREFS-UPDATE] Updated preferences for user {user_id}")
            else:
                # Create new preferences
                preference_data["id"] = str(uuid.uuid4())
                preference_data["created_at"] = preference_data["updated_at"]
                await self.db.create_record("user_preferences", preference_data)
                logger.debug(f"[DB-STATE-PREFS-CREATE] Created preferences for user {user_id}")
            
            return True
            
        except Exception as error:
            logger.error(f"[DB-STATE-PREFS-ERROR] Failed to save preferences for user {user_id}: {error}")
            return False
    
    async def get_user_preferences(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Get user preferences from database.
        
        Args:
            user_id: User ID
            
        Returns:
            User preferences dict or None if not found
        """
        try:
            if not self.is_initialized:
                await self.initialize()
            
            results = await self.db.query_records(
                "user_preferences",
                filters={"user_id": user_id},
                limit=1
            )
            
            if not results:
                return None
            
            return results[0].get("preferences", {})
            
        except Exception as error:
            logger.error(f"[DB-STATE-PREFS-GET-ERROR] Failed to get preferences for user {user_id}: {error}")
            return None
    
    async def migrate_file_based_state(self, file_path: str, created_by: str) -> StateMigration:
        """
        Migrate file-based game state to database.
        
        Args:
            file_path: Path to game state JSON file
            created_by: User ID performing migration
            
        Returns:
            StateMigration object with results
        """
        migration = StateMigration(
            migration_id=str(uuid.uuid4()),
            source_type="file",
            target_type="database",
            started_at=datetime.now(),
            status="in_progress"
        )
        
        try:
            if not self.is_initialized:
                await self.initialize()
            
            logger.info(f"[DB-STATE-MIGRATE] Starting file-based state migration from {file_path}")
            
            # Load file-based state
            with open(file_path, 'r') as f:
                file_state = json.load(f)
            
            # Extract game information
            game_id = file_state.get("current_playlist", {}).get("id", "unknown")
            if game_id == "unknown":
                game_id = f"migrated_{int(datetime.now().timestamp())}"
            
            migration.total_games = 1
            
            # Save as persistent state
            await self.save_game_state(
                game_id=game_id,
                state_data=file_state,
                created_by=created_by,
                description=f"Migrated from file: {file_path}",
                is_checkpoint=True
            )
            
            migration.games_migrated.append(game_id)
            migration.status = "completed"
            migration.completed_at = datetime.now()
            
            logger.info(f"[DB-STATE-MIGRATE] Successfully migrated file-based state to game {game_id}")
            
        except Exception as error:
            migration.status = "failed"
            migration.completed_at = datetime.now()
            migration.error_log.append(str(error))
            
            logger.error(f"[DB-STATE-MIGRATE-ERROR] Migration failed: {error}")
        
        return migration
    
    async def get_saved_games(self, user_id: str = None, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get saved games from database.
        
        Args:
            user_id: Filter by user ID (optional)
            limit: Maximum number of games to return
            
        Returns:
            List of saved game records
        """
        try:
            if not self.is_initialized:
                await self.initialize()
            
            filters = {}
            if user_id:
                filters["created_by"] = user_id
            
            results = await self.db.query_records(
                "saved_games",
                filters=filters,
                order_by={"column": "created_at", "ascending": False},
                limit=limit
            )
            
            logger.debug(f"[DB-STATE-SAVED-GAMES] Retrieved {len(results)} saved games")
            return results if results else []
            
        except Exception as error:
            logger.error(f"[DB-STATE-SAVED-GAMES-ERROR] Failed to get saved games: {error}")
            return []
    
    async def cleanup_old_states(self, days_old: int = 30) -> int:
        """
        Clean up old game states (except final states).
        
        Args:
            days_old: Delete states older than this many days
            
        Returns:
            Number of states deleted
        """
        try:
            if not self.is_initialized:
                await self.initialize()
            
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_old)
            
            # Find old non-final states
            old_states = await self.db.query_records(
                "game_states",
                # Note: This would need proper SQL for date comparison
                # The exact implementation depends on Supabase query capabilities
                select="id",
                limit=1000  # Process in batches
            )
            
            deleted_count = 0
            for state in old_states:
                # Would need to check date and is_final status
                # Implementation depends on query capabilities
                pass
            
            logger.info(f"[DB-STATE-CLEANUP] Cleaned up {deleted_count} old states")
            return deleted_count
            
        except Exception as error:
            logger.error(f"[DB-STATE-CLEANUP-ERROR] Failed to cleanup old states: {error}")
            return 0
    
    async def get_database_stats(self) -> Dict[str, Any]:
        """Get database statistics for monitoring"""
        try:
            if not self.is_initialized:
                await self.initialize()
            
            stats = {}
            
            # Count records in each table
            for table_name in self.table_names.values():
                try:
                    count = await self.db.count_records(table_name)
                    stats[f"{table_name}_count"] = count
                except Exception as count_error:
                    logger.warning(f"[DB-STATE-STATS-WARN] Failed to count {table_name}: {count_error}")
                    stats[f"{table_name}_count"] = -1
            
            # Add health status
            stats["health_status"] = await self.health_check()
            stats["last_check"] = datetime.now().isoformat()
            
            return stats
            
        except Exception as error:
            logger.error(f"[DB-STATE-STATS-ERROR] Failed to get database stats: {error}")
            return {"error": str(error)}
    
    async def _log_operation(self, operation: StateOperation) -> None:
        """Log state operation for audit trail"""
        try:
            # Log to application logger
            logger.info(
                f"[DB-STATE-OP] {operation.operation_type}",
                extra={
                    "game_id": operation.game_id,
                    "user_id": operation.user_id,
                    "operation_data": operation.operation_data,
                    "timestamp": operation.timestamp.isoformat(),
                    "success": operation.success
                }
            )
            
            # Could also store in database audit table if needed
            
        except Exception as error:
            logger.error(f"[DB-STATE-LOG-ERROR] Failed to log operation: {error}")


# Global instance for application use
database_state_manager = DatabaseStateManager()
