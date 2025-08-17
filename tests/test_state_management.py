"""
Comprehensive tests for the hybrid Redis/Database state management system.

Tests cover:
- Redis game state manager functionality
- Database persistent state manager functionality
- Unified state manager integration
- Backward compatibility with legacy state management
- Migration scenarios and data integrity
"""

import pytest
import asyncio
import json
import os
import tempfile
from datetime import datetime
from unittest.mock import patch, MagicMock, AsyncMock

from app.models import (
    RedisGameState,
    PersistentGameState,
    StateSnapshot,
    Track,
    GameSettings,
    BingoMode
)
from app.game_state_manager import RedisGameStateManager
from app.persistent_state_manager import DatabaseStateManager
from app.unified_state_manager import UnifiedStateManager
from app.state import ThreadSafeGameState


class TestRedisGameStateManager:
    """Test Redis-based ephemeral state management"""

    @pytest.fixture
    def redis_manager(self):
        """Create Redis manager with mocked connection"""
        manager = RedisGameStateManager()
        # Mock Redis connection for testing
        manager.redis = AsyncMock()
        manager.is_connected = True
        manager.lua_scripts = {
            'update_game_state': 'mock_script_1',
            'player_join': 'mock_script_2',
            'track_advance': 'mock_script_3'
        }
        return manager

    @pytest.fixture
    def sample_tracks(self):
        """Sample tracks for testing"""
        return [
            Track(
                id="track_1",
                name="Test Song 1",
                artist="Test Artist 1",
                album="Test Album 1"
            ),
            Track(
                id="track_2",
                name="Test Song 2",
                artist="Test Artist 2",
                album="Test Album 2"
            )
        ]

    @pytest.fixture
    def sample_settings(self):
        """Sample game settings"""
        return GameSettings(
            track_duration=30,
            bingo_mode=BingoMode.ROW_COL_DIAG,
            shuffle_tracks=True
        )

    @pytest.mark.asyncio
    async def test_health_check(self, redis_manager):
        """Test Redis health check functionality"""
        # Mock successful ping
        redis_manager.redis.ping.return_value = "PONG"
        redis_manager.redis.set.return_value = True
        redis_manager.redis.get.return_value = "test"
        redis_manager.redis.delete.return_value = 1

        result = await redis_manager.health_check()
        assert result is True

        # Test failed health check
        redis_manager.redis.ping.side_effect = Exception("Connection failed")
        result = await redis_manager.health_check()
        assert result is False

    @pytest.mark.asyncio
    async def test_create_game_state(self, redis_manager, sample_tracks, sample_settings):
        """Test creating new game state in Redis"""
        game_id = "test_game_1"

        # Mock Redis operations
        redis_manager.redis.evalsha.return_value = [1, "Success"]
        redis_manager.redis.sadd.return_value = 1
        redis_manager.redis.hset.return_value = 1
        redis_manager.redis.expire.return_value = True
        redis_manager.redis.pipeline.return_value = AsyncMock()
        redis_manager.redis.pipeline.return_value.execute.return_value = [True, True]

        # Create game state
        result = await redis_manager.create_game_state(
            game_id, sample_tracks, sample_settings
        )

        assert isinstance(result, RedisGameState)
        assert result.game_id == game_id
        assert len(result.unplayed_tracks) == 2
        assert result.settings.bingo_mode == BingoMode.ROW_COL_DIAG
        assert result.state_version == 1

    @pytest.mark.asyncio
    async def test_get_game_state(self, redis_manager):
        """Test retrieving game state from Redis"""
        game_id = "test_game_1"

        # Mock Redis data
        mock_state = {
            "game_id": game_id,
            "played_tracks": [],
            "unplayed_tracks": [],
            "current_track": None,
            "current_track_index": 0,
            "active_players": [],
            "websocket_sessions": {},
            "bingo_validations": {},
            "game_started_at": None,
            "last_activity": datetime.now().isoformat(),
            "settings": {
                "track_duration": 30,
                "pause_between_tracks": 5,
                "bingo_mode": "rowcoldiag",
                "card_size": 5,
                "auto_mark": False,
                "shuffle_tracks": True
            },
            "ttl_seconds": 7200,
            "state_version": 1
        }

        redis_manager.redis.get.return_value = json.dumps(mock_state)

        result = await redis_manager.get_game_state(game_id)

        assert isinstance(result, RedisGameState)
        assert result.game_id == game_id
        assert result.state_version == 1

    @pytest.mark.asyncio
    async def test_update_game_state(self, redis_manager, sample_tracks, sample_settings):
        """Test updating game state in Redis"""
        game_id = "test_game_1"

        state = RedisGameState(
            game_id=game_id,
            unplayed_tracks=sample_tracks,
            settings=sample_settings,
            state_version=1
        )

        # Mock successful update
        redis_manager.redis.evalsha.return_value = [1, "Success"]

        result = await redis_manager.update_game_state(game_id, state)

        assert result is True
        assert state.state_version == 2  # Version should increment

        # Test version conflict
        redis_manager.redis.evalsha.return_value = [0, "Version conflict"]

        result = await redis_manager.update_game_state(game_id, state)
        assert result is False

    @pytest.mark.asyncio
    async def test_add_remove_player(self, redis_manager):
        """Test adding and removing players"""
        game_id = "test_game_1"
        player_id = "player_1"
        session_id = "session_1"

        # Test add player
        redis_manager.redis.evalsha.return_value = 2  # 2 players total
        redis_manager.redis.sadd.return_value = 1

        player_count = await redis_manager.add_player(game_id, player_id, session_id)
        assert player_count == 2

        # Test remove player
        redis_manager.redis.pipeline.return_value = AsyncMock()
        redis_manager.redis.pipeline.return_value.execute.return_value = [1, 1, 1]  # srem, delete, scard

        remaining_count = await redis_manager.remove_player(game_id, player_id)
        assert remaining_count == 1

    @pytest.mark.asyncio
    async def test_advance_track(self, redis_manager, sample_tracks):
        """Test advancing to next track"""
        game_id = "test_game_1"
        new_track = sample_tracks[0]

        # Mock successful track advance
        redis_manager.redis.evalsha.return_value = 5  # 5 tracks remaining

        remaining = await redis_manager.advance_track(game_id, new_track)
        assert remaining == 5

    @pytest.mark.asyncio
    async def test_get_active_games(self, redis_manager):
        """Test getting list of active games"""
        redis_manager.redis.smembers.return_value = {"game_1", "game_2", "game_3"}

        active_games = await redis_manager.get_active_games()
        assert len(active_games) == 3
        assert "game_1" in active_games


class TestDatabaseStateManager:
    """Test Database-based persistent state management"""

    @pytest.fixture
    def db_manager(self):
        """Create database manager with mocked connection"""
        manager = DatabaseStateManager()
        manager.db = AsyncMock()
        manager.is_initialized = True
        return manager

    @pytest.mark.asyncio
    async def test_health_check(self, db_manager):
        """Test database health check"""
        db_manager.db.health_check.return_value = True

        result = await db_manager.health_check()
        assert result is True

    @pytest.mark.asyncio
    async def test_save_game_state(self, db_manager):
        """Test saving persistent game state"""
        game_id = "test_game_1"
        state_data = {"test": "data"}
        created_by = "user_1"

        # Mock database response
        mock_response = {
            "id": "state_1",
            "game_id": game_id,
            "state_data": state_data,
            "state_type": "checkpoint",
            "created_at": datetime.now().isoformat(),
            "created_by": created_by,
            "description": "Test state",
            "is_checkpoint": True,
            "is_final": False
        }

        db_manager.db.create_record.return_value = mock_response

        result = await db_manager.save_game_state(
            game_id, state_data, created_by, "Test state", is_checkpoint=True
        )

        assert isinstance(result, PersistentGameState)
        assert result.game_id == game_id
        assert result.is_checkpoint is True

    @pytest.mark.asyncio
    async def test_get_game_state(self, db_manager):
        """Test retrieving persistent game state"""
        game_id = "test_game_1"

        mock_response = {
            "id": "state_1",
            "game_id": game_id,
            "state_data": {"test": "data"},
            "state_type": "checkpoint",
            "created_at": datetime.now().isoformat(),
            "created_by": "user_1",
            "description": "Test state",
            "is_checkpoint": True,
            "is_final": False
        }

        db_manager.db.query_records.return_value = [mock_response]

        result = await db_manager.get_game_state(game_id)

        assert isinstance(result, PersistentGameState)
        assert result.game_id == game_id

    @pytest.mark.asyncio
    async def test_get_game_history(self, db_manager):
        """Test retrieving game state history"""
        game_id = "test_game_1"

        mock_responses = [
            {
                "id": f"state_{i}",
                "game_id": game_id,
                "state_data": {"test": f"data_{i}"},
                "state_type": "checkpoint",
                "created_at": datetime.now().isoformat(),
                "created_by": "user_1",
                "description": f"Test state {i}",
                "is_checkpoint": True,
                "is_final": False
            }
            for i in range(3)
        ]

        db_manager.db.query_records.return_value = mock_responses

        result = await db_manager.get_game_history(game_id)

        assert len(result) == 3
        assert all(isinstance(state, PersistentGameState) for state in result)

    @pytest.mark.asyncio
    async def test_user_preferences(self, db_manager):
        """Test user preference management"""
        user_id = "user_1"
        preferences = {"theme": "dark", "sound_enabled": True}

        # Test saving preferences (new user)
        db_manager.db.query_records.return_value = []  # No existing preferences
        db_manager.db.create_record.return_value = {"id": "pref_1"}

        result = await db_manager.save_user_preferences(user_id, preferences)
        assert result is True

        # Test getting preferences
        db_manager.db.query_records.return_value = [{"preferences": preferences}]

        result = await db_manager.get_user_preferences(user_id)
        assert result == preferences


class TestUnifiedStateManager:
    """Test unified state manager integration"""

    @pytest.fixture
    def unified_manager(self):
        """Create unified manager with mocked backends"""
        manager = UnifiedStateManager()
        manager.redis_manager = AsyncMock()
        manager.db_manager = AsyncMock()
        manager.is_initialized = True
        return manager

    @pytest.mark.asyncio
    async def test_health_check(self, unified_manager):
        """Test unified health check"""
        unified_manager.redis_manager.health_check.return_value = True
        unified_manager.db_manager.health_check.return_value = True

        result = await unified_manager.health_check()

        assert result["overall_healthy"] is True
        assert result["redis_backend"] is True
        assert result["database_backend"] is True

    @pytest.mark.asyncio
    async def test_create_game_state(self, unified_manager, sample_tracks, sample_settings):
        """Test creating game state in unified manager"""
        game_id = "test_game_1"
        created_by = "user_1"

        # Mock Redis state creation
        mock_redis_state = RedisGameState(
            game_id=game_id,
            unplayed_tracks=sample_tracks,
            settings=sample_settings
        )
        unified_manager.redis_manager.create_game_state.return_value = mock_redis_state

        # Mock database state creation
        mock_db_state = PersistentGameState(
            id="state_1",
            game_id=game_id,
            state_data={},
            state_type="checkpoint",
            created_at=datetime.now(),
            created_by=created_by,
            is_checkpoint=True,
            is_final=False
        )
        unified_manager.db_manager.save_game_state.return_value = mock_db_state

        result = await unified_manager.create_game_state(
            game_id, sample_tracks, sample_settings, created_by
        )

        assert isinstance(result, StateSnapshot)
        assert result.game_id == game_id
        assert result.ephemeral_state == mock_redis_state
        assert result.persistent_state == mock_db_state

    @pytest.mark.asyncio
    async def test_get_game_snapshot(self, unified_manager):
        """Test getting complete game snapshot"""
        game_id = "test_game_1"

        # Mock both backends returning data
        mock_redis_state = RedisGameState(game_id=game_id)
        mock_db_state = PersistentGameState(
            id="state_1",
            game_id=game_id,
            state_data={},
            state_type="checkpoint",
            created_at=datetime.now(),
            created_by="user_1",
            is_checkpoint=True,
            is_final=False
        )

        unified_manager.redis_manager.get_game_state.return_value = mock_redis_state
        unified_manager.db_manager.get_game_state.return_value = mock_db_state

        result = await unified_manager.get_game_snapshot(game_id)

        assert isinstance(result, StateSnapshot)
        assert result.sync_status == "synced"

    @pytest.mark.asyncio
    async def test_backward_compatibility(self, unified_manager):
        """Test backward compatibility with legacy API"""
        # Mock active games
        unified_manager.redis_manager.get_active_games.return_value = ["game_1"]

        # Mock game snapshot
        mock_snapshot = StateSnapshot(
            game_id="game_1",
            ephemeral_state=RedisGameState(
                game_id="game_1",
                played_tracks=[],
                unplayed_tracks=[]
            )
        )

        with patch.object(unified_manager, 'get_game_snapshot', return_value=mock_snapshot):
            result = await unified_manager.get_state()

            assert isinstance(result, dict)
            assert "played_tracks" in result
            assert "unplayed_tracks" in result
            assert "cards" in result


class TestBackwardCompatibility:
    """Test backward compatibility with legacy state management"""

    @pytest.fixture
    def temp_state_file(self):
        """Create temporary state file for testing"""
        temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
        state_data = {
            "played_tracks": [{"id": "track_1", "name": "Test Song"}],
            "unplayed_tracks": [{"id": "track_2", "name": "Test Song 2"}],
            "cards": {"player_1": {"grid": []}},
            "bingo_mode": "rowcoldiag",
            "current_playlist": {"id": "playlist_1"},
            "num_tracks": 2
        }
        json.dump(state_data, temp_file)
        temp_file.close()
        yield temp_file.name
        os.unlink(temp_file.name)

    def test_legacy_state_load(self, temp_state_file):
        """Test loading legacy state file"""
        with patch('app.state.GAME_STATE_FILE', temp_state_file):
            state_manager = ThreadSafeGameState()
            state = state_manager.get_state()

            assert state["num_tracks"] == 2
            assert len(state["played_tracks"]) == 1
            assert len(state["unplayed_tracks"]) == 1

    def test_legacy_state_update(self, temp_state_file):
        """Test updating legacy state"""
        with patch('app.state.GAME_STATE_FILE', temp_state_file):
            state_manager = ThreadSafeGameState()

            def update_func(state):
                state["num_tracks"] = 5
                state["played_tracks"].append({"id": "track_3", "name": "New Song"})

            updated_state = state_manager.update_state(update_func)

            assert updated_state["num_tracks"] == 5
            assert len(updated_state["played_tracks"]) == 2

    @pytest.mark.asyncio
    async def test_migration_to_unified(self, temp_state_file):
        """Test migration from legacy to unified state management"""
        with patch('app.state.GAME_STATE_FILE', temp_state_file):
            state_manager = ThreadSafeGameState()

            # Mock unified manager
            mock_unified = AsyncMock()
            mock_unified.is_initialized = True
            state_manager._unified_manager = mock_unified

            result = await state_manager.migrate_to_unified("test_game", "test_user")

            assert result is True
            mock_unified.update_game_state.assert_called_once()


class TestStateIntegration:
    """Integration tests for complete state management system"""

    @pytest.mark.asyncio
    async def test_full_game_lifecycle(self):
        """Test complete game lifecycle with state management"""
        # This would be a comprehensive integration test
        # that tests the entire flow from game creation to completion
        # with real Redis and Database connections in a test environment

        # For now, this is a placeholder for future implementation
        # when test infrastructure is set up
        pass

    @pytest.mark.asyncio
    async def test_state_synchronization(self):
        """Test state synchronization between Redis and Database"""
        # Test that changes in Redis are properly synchronized to Database
        # and vice versa when needed
        pass

    @pytest.mark.asyncio
    async def test_error_recovery(self):
        """Test error recovery scenarios"""
        # Test what happens when Redis is down but Database is available
        # Test what happens when Database is down but Redis is available
        # Test recovery when both are restored
        pass

    @pytest.mark.asyncio
    async def test_performance_characteristics(self):
        """Test performance characteristics of state management"""
        # Test response times for various operations
        # Test memory usage patterns
        # Test concurrent access scenarios
        pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
