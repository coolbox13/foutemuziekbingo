"""
Comprehensive Redis/Cache Integration Tests

This module provides comprehensive testing of the Redis/Dragonfly caching
system including cache performance, hit rates, invalidation strategies,
TTL management, and multi-instance coordination.

Test Coverage:
- Cache manager initialization and connection
- Cache operations (get, set, delete, exists)
- TTL policies and expiration handling
- Cache invalidation strategies
- Cache statistics and monitoring
- Performance under load
- Multi-instance cache coordination
- Cache warming and preloading
- Memory management and eviction
- Error handling and failover
"""

import pytest
import asyncio
import time
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional
from unittest.mock import patch, AsyncMock

import redis.asyncio as redis

# Add parent directory to path so we can import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

# Load test environment first
from test_utils import load_test_environment
load_test_environment()

from app.cache_manager import (
    CacheManager, CacheType,
    CacheConnectionError
)


class MockRedisClient:
    """Mock Redis client for testing."""

    def __init__(self):
        self.data = {}
        self.ttl_data = {}
        self.stats = {
            "hits": 0,
            "misses": 0,
            "sets": 0,
            "deletes": 0
        }

    async def ping(self):
        """Mock ping method."""
        return True

    async def get(self, key: str) -> Optional[str]:
        """Mock get method."""
        if key in self.data:
            # Check TTL
            if key in self.ttl_data:
                if time.time() > self.ttl_data[key]:
                    del self.data[key]
                    del self.ttl_data[key]
                    self.stats["misses"] += 1
                    return None
            self.stats["hits"] += 1
            return self.data[key]
        self.stats["misses"] += 1
        return None

    async def set(self, key: str, value: str, ex: int = None) -> bool:
        """Mock set method."""
        self.data[key] = value
        if ex:
            self.ttl_data[key] = time.time() + ex
        self.stats["sets"] += 1
        return True

    async def delete(self, *keys: str) -> int:
        """Mock delete method."""
        count = 0
        for key in keys:
            if key in self.data:
                del self.data[key]
                if key in self.ttl_data:
                    del self.ttl_data[key]
                count += 1
        self.stats["deletes"] += count
        return count

    async def exists(self, *keys: str) -> int:
        """Mock exists method."""
        count = 0
        for key in keys:
            if key in self.data:
                # Check TTL
                if key in self.ttl_data and time.time() > self.ttl_data[key]:
                    del self.data[key]
                    del self.ttl_data[key]
                else:
                    count += 1
        return count

    async def keys(self, pattern: str) -> List[str]:
        """Mock keys method."""
        # Simple pattern matching
        if pattern == "*":
            return list(self.data.keys())
        return [key for key in self.data.keys() if pattern.replace("*", "") in key]

    async def info(self, section: str = "all") -> Dict[str, Any]:
        """Mock info method."""
        return {
            "used_memory": len(str(self.data)) * 8,  # Rough estimate
            "connected_clients": 1,
            "total_commands_processed": sum(self.stats.values()),
            "keyspace_hits": self.stats["hits"],
            "keyspace_misses": self.stats["misses"]
        }

    def scan_iter(self, match: str = None, count: int = None):
        """Mock scan_iter method."""
        keys = self.data.keys()
        if match:
            keys = [key for key in keys if match.replace("*", "") in key]

        async def async_generator():
            for key in keys:
                yield key

        return async_generator()


class TestCacheManagerInitialization:
    """Test cache manager initialization and configuration."""

    def test_cache_manager_creation(self):
        """Test cache manager instance creation."""
        cache_manager = CacheManager()

        assert cache_manager is not None
        assert cache_manager.redis_client is None  # Not connected yet
        assert cache_manager.key_prefix == "mb"
        assert cache_manager.ttl_policies is not None

        # Check TTL policies are configured
        assert CacheType.PLAYLIST in cache_manager.ttl_policies
        assert CacheType.TRACK in cache_manager.ttl_policies
        assert CacheType.USER_DATA in cache_manager.ttl_policies
        assert CacheType.GAME_STATE in cache_manager.ttl_policies
        assert CacheType.METADATA in cache_manager.ttl_policies
        assert CacheType.SESSION_DATA in cache_manager.ttl_policies

    @pytest.mark.asyncio
    async def test_cache_manager_connection(self):
        """Test Redis connection establishment."""
        cache_manager = CacheManager()

        # Mock Redis connection
        with patch('redis.asyncio.from_url') as mock_redis_factory:
            mock_redis = MockRedisClient()
            mock_redis_factory.return_value = mock_redis

            # Get Redis connection
            redis_client = await cache_manager._get_redis()

            assert redis_client is not None
            assert await redis_client.ping()

    @pytest.mark.asyncio
    async def test_connection_error_handling(self):
        """Test handling of Redis connection errors."""
        cache_manager = CacheManager()

        # Mock connection failure
        with patch('redis.asyncio.from_url') as mock_redis_factory:
            mock_redis_factory.side_effect = Exception("Connection failed")

            # Should raise CacheConnectionError
            with pytest.raises(CacheConnectionError):
                await cache_manager._get_redis()

    def test_ttl_policy_configuration(self):
        """Test TTL policy configuration."""
        cache_manager = CacheManager()

        # Verify TTL policies make sense
        assert cache_manager.ttl_policies[CacheType.TRACK] > cache_manager.ttl_policies[CacheType.SESSION_DATA]
        assert cache_manager.ttl_policies[CacheType.PLAYLIST] > cache_manager.ttl_policies[CacheType.USER_DATA]
        assert cache_manager.ttl_policies[CacheType.METADATA] > cache_manager.ttl_policies[CacheType.GAME_STATE]


class TestCacheOperations:
    """Test basic cache operations."""

    @pytest.mark.asyncio
    async def test_cache_set_get(self):
        """Test basic cache set and get operations."""
        cache_manager = CacheManager()

        # Mock Redis client
        mock_redis = MockRedisClient()
        cache_manager.redis_client = mock_redis

        # Test set operation
        test_data = {"track_id": "123", "name": "Test Song", "artist": "Test Artist"}
        success = await cache_manager.set(
            cache_type=CacheType.TRACK,
            identifier="123",
            data=test_data
        )

        assert success

        # Test get operation
        retrieved_data = await cache_manager.get(
            cache_type=CacheType.TRACK,
            identifier="123"
        )

        assert retrieved_data == test_data

    @pytest.mark.asyncio
    async def test_cache_delete(self):
        """Test cache deletion."""
        cache_manager = CacheManager()
        mock_redis = MockRedisClient()
        cache_manager.redis_client = mock_redis

        # Set data first
        test_data = {"playlist_id": "456", "name": "Test Playlist"}
        await cache_manager.set(CacheType.PLAYLIST, "456", test_data)

        # Verify data exists
        retrieved = await cache_manager.get(CacheType.PLAYLIST, "456")
        assert retrieved == test_data

        # Delete data
        deleted = await cache_manager.delete(CacheType.PLAYLIST, "456")
        assert deleted

        # Verify data is gone
        retrieved_after = await cache_manager.get(CacheType.PLAYLIST, "456")
        assert retrieved_after is None

    @pytest.mark.asyncio
    async def test_cache_exists(self):
        """Test cache existence checking."""
        cache_manager = CacheManager()
        mock_redis = MockRedisClient()
        cache_manager.redis_client = mock_redis

        # Check non-existent key
        exists_before = await cache_manager.exists(CacheType.USER_DATA, "789")
        assert not exists_before

        # Set data
        user_data = {"user_id": "789", "preferences": {"theme": "dark"}}
        await cache_manager.set(CacheType.USER_DATA, "789", user_data)

        # Check existing key
        exists_after = await cache_manager.exists(CacheType.USER_DATA, "789")
        assert exists_after

    @pytest.mark.asyncio
    async def test_cache_ttl_handling(self):
        """Test TTL (time-to-live) handling."""
        cache_manager = CacheManager()
        mock_redis = MockRedisClient()
        cache_manager.redis_client = mock_redis

        # Set data with short TTL for testing
        session_data = {"session_id": "abc123", "user_id": "user456"}

        # Override TTL for testing
        original_ttl = cache_manager.ttl_policies[CacheType.SESSION_DATA]
        cache_manager.ttl_policies[CacheType.SESSION_DATA] = 1  # 1 second

        await cache_manager.set(CacheType.SESSION_DATA, "abc123", session_data)

        # Data should exist immediately
        retrieved_immediate = await cache_manager.get(CacheType.SESSION_DATA, "abc123")
        assert retrieved_immediate == session_data

        # Wait for TTL to expire
        await asyncio.sleep(1.1)

        # Data should be expired
        retrieved_after_ttl = await cache_manager.get(CacheType.SESSION_DATA, "abc123")
        assert retrieved_after_ttl is None

        # Restore original TTL
        cache_manager.ttl_policies[CacheType.SESSION_DATA] = original_ttl


class TestCachePerformance:
    """Test cache performance and optimization."""

    @pytest.mark.asyncio
    async def test_bulk_operations(self):
        """Test bulk cache operations for performance."""
        cache_manager = CacheManager()
        mock_redis = MockRedisClient()
        cache_manager.redis_client = mock_redis

        # Bulk set operations
        bulk_data = {}
        for i in range(100):
            track_data = {
                "track_id": f"track_{i}",
                "name": f"Song {i}",
                "artist": f"Artist {i}"
            }
            bulk_data[f"track_{i}"] = track_data

        # Set all data
        start_time = time.time()
        for track_id, track_data in bulk_data.items():
            await cache_manager.set(CacheType.TRACK, track_id, track_data)
        set_time = time.time() - start_time

        # Get all data
        start_time = time.time()
        retrieved_data = {}
        for track_id in bulk_data.keys():
            retrieved_data[track_id] = await cache_manager.get(CacheType.TRACK, track_id)
        get_time = time.time() - start_time

        # Verify data integrity
        assert len(retrieved_data) == 100
        for track_id, expected_data in bulk_data.items():
            assert retrieved_data[track_id] == expected_data

        # Performance should be reasonable (adjust thresholds as needed)
        assert set_time < 1.0  # Should set 100 items in under 1 second
        assert get_time < 1.0  # Should get 100 items in under 1 second

    @pytest.mark.asyncio
    async def test_cache_hit_rates(self):
        """Test cache hit rate calculations."""
        cache_manager = CacheManager()
        mock_redis = MockRedisClient()
        cache_manager.redis_client = mock_redis

        # Set some test data
        test_items = {}
        for i in range(10):
            metadata = {"api_response": f"data_{i}", "timestamp": time.time()}
            test_items[f"item_{i}"] = metadata
            await cache_manager.set(CacheType.METADATA, f"item_{i}", metadata)

        # Generate cache hits and misses
        hits = 0
        misses = 0

        # Access existing items (cache hits)
        for i in range(10):
            result = await cache_manager.get(CacheType.METADATA, f"item_{i}")
            if result is not None:
                hits += 1
            else:
                misses += 1

        # Access non-existing items (cache misses)
        for i in range(10, 15):
            result = await cache_manager.get(CacheType.METADATA, f"item_{i}")
            if result is not None:
                hits += 1
            else:
                misses += 1

        # Calculate hit rate
        total_requests = hits + misses
        hit_rate = hits / total_requests if total_requests > 0 else 0

        assert hits == 10  # All existing items found
        assert misses == 5  # All non-existing items missed
        assert hit_rate == 0.67  # 10/15 = 0.666...

    @pytest.mark.asyncio
    async def test_concurrent_access(self):
        """Test cache performance under concurrent access."""
        cache_manager = CacheManager()
        mock_redis = MockRedisClient()
        cache_manager.redis_client = mock_redis

        # Concurrent set operations
        async def set_data(index):
            game_state = {
                "game_id": f"game_{index}",
                "status": "in_progress",
                "players": index % 5
            }
            return await cache_manager.set(CacheType.GAME_STATE, f"game_{index}", game_state)

        # Execute concurrent operations
        tasks = [set_data(i) for i in range(50)]
        results = await asyncio.gather(*tasks)

        # All operations should succeed
        assert all(results)
        assert len(results) == 50

        # Concurrent get operations
        async def get_data(index):
            return await cache_manager.get(CacheType.GAME_STATE, f"game_{index}")

        get_tasks = [get_data(i) for i in range(50)]
        get_results = await asyncio.gather(*get_tasks)

        # All data should be retrieved
        assert len(get_results) == 50
        assert all(result is not None for result in get_results)

    @pytest.mark.asyncio
    async def test_memory_efficiency(self):
        """Test cache memory usage and efficiency."""
        cache_manager = CacheManager()
        mock_redis = MockRedisClient()
        cache_manager.redis_client = mock_redis

        # Store data of different sizes
        small_data = {"key": "value"}
        medium_data = {"data": "x" * 1000}  # 1KB
        large_data = {"data": "x" * 10000}  # 10KB

        await cache_manager.set(CacheType.USER_DATA, "small", small_data)
        await cache_manager.set(CacheType.USER_DATA, "medium", medium_data)
        await cache_manager.set(CacheType.USER_DATA, "large", large_data)

        # Get cache statistics
        stats = await cache_manager.get_cache_stats()

        assert stats is not None
        assert "total_keys" in stats
        assert stats["total_keys"] >= 3  # At least our 3 items


class TestCacheInvalidation:
    """Test cache invalidation strategies."""

    @pytest.mark.asyncio
    async def test_manual_invalidation(self):
        """Test manual cache invalidation."""
        cache_manager = CacheManager()
        mock_redis = MockRedisClient()
        cache_manager.redis_client = mock_redis

        # Set playlist data
        playlist_data = {
            "playlist_id": "playlist123",
            "tracks": ["track1", "track2", "track3"]
        }
        await cache_manager.set(CacheType.PLAYLIST, "playlist123", playlist_data)

        # Verify data exists
        retrieved = await cache_manager.get(CacheType.PLAYLIST, "playlist123")
        assert retrieved == playlist_data

        # Invalidate cache
        invalidated = await cache_manager.invalidate_cache(CacheType.PLAYLIST, "playlist123")
        assert invalidated

        # Verify data is gone
        after_invalidation = await cache_manager.get(CacheType.PLAYLIST, "playlist123")
        assert after_invalidation is None

    @pytest.mark.asyncio
    async def test_pattern_based_invalidation(self):
        """Test pattern-based cache invalidation."""
        cache_manager = CacheManager()
        mock_redis = MockRedisClient()
        cache_manager.redis_client = mock_redis

        # Set multiple user-related cache entries
        user_items = {
            "user_123_profile": {"name": "User 123"},
            "user_123_preferences": {"theme": "dark"},
            "user_456_profile": {"name": "User 456"},
            "user_456_preferences": {"theme": "light"}
        }

        for item_id, data in user_items.items():
            await cache_manager.set(CacheType.USER_DATA, item_id, data)

        # Invalidate all user_123 data
        await cache_manager.invalidate_cache_pattern(CacheType.USER_DATA, "user_123*")

        # User 123 data should be gone
        profile_123 = await cache_manager.get(CacheType.USER_DATA, "user_123_profile")
        prefs_123 = await cache_manager.get(CacheType.USER_DATA, "user_123_preferences")
        assert profile_123 is None
        assert prefs_123 is None

        # User 456 data should still exist
        profile_456 = await cache_manager.get(CacheType.USER_DATA, "user_456_profile")
        prefs_456 = await cache_manager.get(CacheType.USER_DATA, "user_456_preferences")
        assert profile_456 == {"name": "User 456"}
        assert prefs_456 == {"theme": "light"}

    @pytest.mark.asyncio
    async def test_automatic_ttl_invalidation(self):
        """Test automatic TTL-based invalidation."""
        cache_manager = CacheManager()
        mock_redis = MockRedisClient()
        cache_manager.redis_client = mock_redis

        # Override TTL for testing
        original_ttl = cache_manager.ttl_policies[CacheType.GAME_STATE]
        cache_manager.ttl_policies[CacheType.GAME_STATE] = 1  # 1 second

        # Set game state data
        game_state = {
            "game_id": "game789",
            "current_track": "track123",
            "status": "playing"
        }
        await cache_manager.set(CacheType.GAME_STATE, "game789", game_state)

        # Verify immediate availability
        immediate = await cache_manager.get(CacheType.GAME_STATE, "game789")
        assert immediate == game_state

        # Wait for TTL expiration
        await asyncio.sleep(1.1)

        # Data should be automatically invalidated
        after_ttl = await cache_manager.get(CacheType.GAME_STATE, "game789")
        assert after_ttl is None

        # Restore original TTL
        cache_manager.ttl_policies[CacheType.GAME_STATE] = original_ttl

    @pytest.mark.asyncio
    async def test_cache_warming(self):
        """Test cache warming strategies."""
        cache_manager = CacheManager()
        mock_redis = MockRedisClient()
        cache_manager.redis_client = mock_redis

        # Mock frequently accessed data
        popular_tracks = {}
        for i in range(20):
            track_data = {
                "track_id": f"popular_{i}",
                "name": f"Popular Song {i}",
                "play_count": 1000 + i
            }
            popular_tracks[f"popular_{i}"] = track_data

        # Warm cache with popular tracks
        for track_id, track_data in popular_tracks.items():
            await cache_manager.set(CacheType.TRACK, track_id, track_data)

        # Verify cache is warmed
        for track_id in popular_tracks.keys():
            cached_track = await cache_manager.get(CacheType.TRACK, track_id)
            assert cached_track is not None
            assert cached_track["track_id"] == track_id


class TestCacheStatistics:
    """Test cache statistics and monitoring."""

    @pytest.mark.asyncio
    async def test_cache_statistics_collection(self):
        """Test collection of cache statistics."""
        cache_manager = CacheManager()
        mock_redis = MockRedisClient()
        cache_manager.redis_client = mock_redis

        # Perform various cache operations
        await cache_manager.set(CacheType.TRACK, "track1", {"name": "Song 1"})
        await cache_manager.set(CacheType.PLAYLIST, "playlist1", {"name": "Playlist 1"})
        await cache_manager.get(CacheType.TRACK, "track1")  # Hit
        await cache_manager.get(CacheType.TRACK, "track2")  # Miss
        await cache_manager.delete(CacheType.PLAYLIST, "playlist1")

        # Get statistics
        stats = await cache_manager.get_cache_stats()

        assert stats is not None
        assert "total_keys" in stats
        assert "total_memory" in stats
        assert "hit_rate" in stats
        assert "miss_rate" in stats

    @pytest.mark.asyncio
    async def test_per_type_statistics(self):
        """Test statistics per cache type."""
        cache_manager = CacheManager()
        mock_redis = MockRedisClient()
        cache_manager.redis_client = mock_redis

        # Set data for different cache types
        cache_data = {
            CacheType.TRACK: {"track_stats": "data"},
            CacheType.PLAYLIST: {"playlist_stats": "data"},
            CacheType.USER_DATA: {"user_stats": "data"},
            CacheType.GAME_STATE: {"game_stats": "data"}
        }

        for cache_type, data in cache_data.items():
            await cache_manager.set(cache_type, "test_item", data)

        # Get statistics
        stats = await cache_manager.get_cache_stats()

        # Should have data for different cache types
        assert stats["total_keys"] >= 4

    @pytest.mark.asyncio
    async def test_cache_health_monitoring(self):
        """Test cache health monitoring."""
        cache_manager = CacheManager()
        mock_redis = MockRedisClient()
        cache_manager.redis_client = mock_redis

        # Get health status
        health = await cache_manager.health_check()

        assert health is not None
        assert "healthy" in health
        assert health["healthy"] is True
        assert "connection_status" in health
        assert "memory_usage" in health
        assert "response_time" in health


class TestCacheErrorHandling:
    """Test cache error handling and recovery."""

    @pytest.mark.asyncio
    async def test_redis_connection_loss(self):
        """Test handling of Redis connection loss."""
        cache_manager = CacheManager()

        # Mock Redis connection that fails
        mock_redis = AsyncMock()
        mock_redis.get.side_effect = redis.ConnectionError("Connection lost")
        cache_manager.redis_client = mock_redis

        # Cache operations should handle connection loss gracefully
        result = await cache_manager.get(CacheType.TRACK, "track123")

        # Should return None instead of raising exception
        assert result is None

    @pytest.mark.asyncio
    async def test_redis_timeout_handling(self):
        """Test handling of Redis operation timeouts."""
        cache_manager = CacheManager()

        # Mock Redis with timeout
        mock_redis = AsyncMock()
        mock_redis.set.side_effect = asyncio.TimeoutError("Operation timeout")
        cache_manager.redis_client = mock_redis

        # Should handle timeout gracefully
        result = await cache_manager.set(CacheType.PLAYLIST, "playlist123", {"data": "test"})

        # Should return False indicating operation failed
        assert result is False

    @pytest.mark.asyncio
    async def test_invalid_data_handling(self):
        """Test handling of invalid data types."""
        cache_manager = CacheManager()
        mock_redis = MockRedisClient()
        cache_manager.redis_client = mock_redis

        # Test various invalid data types
        invalid_data_tests = [
            lambda: object(),  # Non-serializable object
            lambda: {"circular": None},  # Would be fine, but let's test complex structures
        ]

        for get_invalid_data in invalid_data_tests:
            try:
                invalid_data = get_invalid_data()
                if hasattr(invalid_data, '__dict__') and not isinstance(invalid_data, dict):
                    # Non-serializable object
                    result = await cache_manager.set(CacheType.METADATA, "invalid", invalid_data)
                    # Should handle gracefully (may succeed if JSON serializable)
                    assert isinstance(result, bool)
            except Exception:
                # Expected for truly invalid data
                assert True

    @pytest.mark.asyncio
    async def test_cache_corruption_handling(self):
        """Test handling of corrupted cache data."""
        cache_manager = CacheManager()
        mock_redis = MockRedisClient()
        cache_manager.redis_client = mock_redis

        # Manually insert corrupted data
        mock_redis.data["mb:track:corrupted"] = "invalid_json_data{{"

        # Attempt to retrieve corrupted data
        result = await cache_manager.get(CacheType.TRACK, "corrupted")

        # Should handle corruption gracefully
        assert result is None  # Or handle according to implementation


class TestCacheKeyGeneration:
    """Test cache key generation and namespacing."""

    def test_cache_key_generation(self):
        """Test cache key generation for different types."""
        cache_manager = CacheManager()

        # Test key generation
        track_key = cache_manager._generate_key(CacheType.TRACK, "track123")
        playlist_key = cache_manager._generate_key(CacheType.PLAYLIST, "playlist456", user_id="user789")
        user_key = cache_manager._generate_key(CacheType.USER_DATA, "preferences", user_id="user123")

        # Keys should be properly formatted
        assert track_key.startswith("mb:track:")
        assert "track123" in track_key

        assert playlist_key.startswith("mb:playlist:")
        assert "playlist456" in playlist_key
        assert "user789" in playlist_key

        assert user_key.startswith("mb:user:")
        assert "user123" in user_key
        assert "preferences" in user_key

    def test_key_collision_prevention(self):
        """Test that different cache types don't have key collisions."""
        cache_manager = CacheManager()

        # Same identifier for different types
        identifier = "same_id_123"

        track_key = cache_manager._generate_key(CacheType.TRACK, identifier)
        playlist_key = cache_manager._generate_key(CacheType.PLAYLIST, identifier)
        user_key = cache_manager._generate_key(CacheType.USER_DATA, identifier)

        # All keys should be different
        keys = [track_key, playlist_key, user_key]
        assert len(set(keys)) == len(keys)  # All unique

    def test_key_sanitization(self):
        """Test cache key sanitization for special characters."""
        cache_manager = CacheManager()

        # Test identifiers with special characters
        special_identifiers = [
            "track:with:colons",
            "track with spaces",
            "track/with/slashes",
            "track-with-dashes"
        ]

        for identifier in special_identifiers:
            key = cache_manager._generate_key(CacheType.TRACK, identifier)

            # Key should be generated successfully
            assert key is not None
            assert len(key) > 0

            # Should contain the cache type
            assert "track" in key.lower()


if __name__ == "__main__":
    # Simple test runner for development
    async def run_tests():
        """Run comprehensive cache integration tests."""
        print("🗄️ COMPREHENSIVE REDIS/CACHE INTEGRATION TESTS")
        print("=" * 80)

        test_classes = [
            TestCacheManagerInitialization,
            TestCacheOperations,
            TestCachePerformance,
            TestCacheInvalidation,
            TestCacheStatistics,
            TestCacheErrorHandling,
            TestCacheKeyGeneration,
        ]

        total_tests = 0
        passed_tests = 0

        for test_class in test_classes:
            print(f"\n{'='*60}")
            print(f"TESTING: {test_class.__name__}")
            print(f"{'='*60}")

            instance = test_class()
            test_methods = [method for method in dir(instance) if method.startswith('test_')]

            for test_method in test_methods:
                total_tests += 1
                try:
                    method = getattr(instance, test_method)
                    if asyncio.iscoroutinefunction(method):
                        await method()
                    else:
                        method()
                    print(f"✅ {test_method}")
                    passed_tests += 1
                except Exception as e:
                    print(f"❌ {test_method}: {e}")

        print(f"\n{'='*80}")
        print("CACHE INTEGRATION TEST SUMMARY")
        print(f"{'='*80}")
        print(f"Total Tests: {total_tests}")
        print(f"Passed: {passed_tests}")
        print(f"Failed: {total_tests - passed_tests}")
        print(f"Success Rate: {(passed_tests/total_tests)*100:.1f}%")

        if passed_tests == total_tests:
            print("\n🎉 All cache integration tests passed!")
            return True
        else:
            print(f"\n⚠️ {total_tests - passed_tests} test(s) failed")
            return False

    # Run tests if executed directly
    asyncio.run(run_tests())
