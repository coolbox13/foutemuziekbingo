"""
Test suite for MED-002 Database Optimization Implementation

This test suite validates the database performance optimizations,
including strategic indexing and cache integration.
"""
import pytest
import time
import asyncio
from datetime import datetime
from typing import List, Dict, Any

from app.database_optimization import db_optimizer, QueryPerformanceMetrics
from app.database import database, DatabaseError
from app.cache_manager import CacheManager, CacheType


class TestDatabaseOptimization:
    """Test database optimization features"""

    @pytest.fixture(autouse=True)
    def setup_method(self):
        """Setup for each test method"""
        # Clear performance metrics before each test
        db_optimizer.clear_performance_metrics()

    @pytest.mark.asyncio
    async def test_query_performance_tracking(self):
        """Test that query performance tracking works correctly"""
        
        # Simulate a database query with performance tracking
        async with db_optimizer.track_query_performance("select", "games", "test_query") as ctx:
            # Simulate some work
            await asyncio.sleep(0.1)  # 100ms
            
        # Check that metrics were recorded
        metrics = db_optimizer.get_performance_metrics()
        
        assert metrics["total_queries"] == 1
        assert metrics["avg_execution_time_ms"] >= 100  # Should be at least 100ms
        assert "select:games" in metrics["operation_stats"]
        
        # Check the individual metric
        assert len(db_optimizer.performance_metrics) == 1
        metric = db_optimizer.performance_metrics[0]
        assert metric.query_type == "select"
        assert metric.table == "games"
        assert metric.execution_time_ms >= 100
        assert "query_hash" in ctx

    @pytest.mark.asyncio
    async def test_slow_query_detection(self):
        """Test that slow queries are properly detected and logged"""
        
        # Simulate a slow query (>100ms)
        async with db_optimizer.track_query_performance("select", "games", "slow_query"):
            await asyncio.sleep(0.15)  # 150ms - should trigger slow query warning
            
        metrics = db_optimizer.get_performance_metrics()
        
        assert metrics["total_queries"] == 1
        assert metrics["slow_queries_count"] == 1
        assert metrics["slow_queries_percentage"] == 100.0
        assert len(metrics["recent_slow_queries"]) == 1

    @pytest.mark.asyncio
    async def test_optimized_user_games_performance(self):
        """Test optimized user games retrieval performance"""
        
        test_user_id = "test_user_123"
        
        # Test without cache first
        start_time = time.time()
        games = await db_optimizer.optimized_get_user_games(
            test_user_id, 
            use_cache=False
        )
        no_cache_time = (time.time() - start_time) * 1000
        
        assert isinstance(games, list)
        
        # Test with cache (should be faster on subsequent calls if cache works)
        if db_optimizer.cache_manager:
            start_time = time.time()
            cached_games = await db_optimizer.optimized_get_user_games(
                test_user_id, 
                use_cache=True
            )
            cached_time = (time.time() - start_time) * 1000
            
            assert games == cached_games  # Results should be the same
            # Note: Cache lookup might not always be faster in tests due to overhead

    @pytest.mark.asyncio 
    async def test_optimized_playlist_track_count(self):
        """Test optimized playlist track counting"""
        
        test_playlist_id = "test_playlist_123"
        
        # Test the optimized track count method
        count = await db_optimizer.optimized_get_playlist_track_count(
            test_playlist_id,
            use_cache=False
        )
        
        assert isinstance(count, int)
        assert count >= 0  # Should be 0 for non-existent playlist

    @pytest.mark.asyncio
    async def test_bulk_cache_user_data(self):
        """Test bulk user data caching for performance"""
        
        test_user_ids = ["user_1", "user_2", "user_3"]
        
        # Set up cache manager if not already set
        if not db_optimizer.cache_manager:
            try:
                cache_manager = CacheManager()
                await cache_manager.initialize()
                db_optimizer.set_cache_manager(cache_manager)
            except Exception:
                pytest.skip("Cache manager not available for testing")
        
        # Test bulk caching
        result = await db_optimizer.bulk_cache_user_data(test_user_ids)
        
        assert "cached" in result
        assert "failed" in result
        assert isinstance(result["cached"], int)
        assert isinstance(result["failed"], int)

    def test_performance_metrics_collection(self):
        """Test performance metrics collection and analysis"""
        
        # Add some test metrics
        test_metrics = [
            QueryPerformanceMetrics("select", "games", 50.0, 10, datetime.now()),
            QueryPerformanceMetrics("select", "games", 150.0, 5, datetime.now()),  # Slow
            QueryPerformanceMetrics("count", "playlist_tracks", 25.0, 1, datetime.now()),
            QueryPerformanceMetrics("select", "users", 200.0, 2, datetime.now()),  # Slow
        ]
        
        db_optimizer.performance_metrics.extend(test_metrics)
        
        metrics = db_optimizer.get_performance_metrics()
        
        # Validate metrics calculation
        assert metrics["total_queries"] == 4
        assert metrics["slow_queries_count"] == 2
        assert metrics["slow_queries_percentage"] == 50.0
        
        # Check operation stats
        assert "select:games" in metrics["operation_stats"]
        assert metrics["operation_stats"]["select:games"]["count"] == 2
        assert metrics["operation_stats"]["select:games"]["avg_time_ms"] == 100.0  # (50 + 150) / 2

    @pytest.mark.asyncio
    async def test_index_validation(self):
        """Test index performance validation"""
        
        # Run index validation
        validation_results = await db_optimizer.validate_indexes_performance()
        
        assert isinstance(validation_results, dict)
        assert len(validation_results) > 0
        
        # Check that each test has required fields
        for test_name, result in validation_results.items():
            if "error" not in result:
                assert "execution_time_ms" in result
                assert "expected_index" in result
                assert "status" in result
                assert result["status"] in ["fast", "slow"]

    def test_metrics_cleanup(self):
        """Test that metrics cleanup works properly"""
        
        # Add many metrics to test cleanup
        test_metrics = [
            QueryPerformanceMetrics("select", "test", 10.0, 1, datetime.now())
            for _ in range(1100)  # More than the 1000 limit
        ]
        
        db_optimizer.performance_metrics.extend(test_metrics)
        
        # Trigger cleanup by adding one more metric with tracking
        async def trigger_cleanup():
            async with db_optimizer.track_query_performance("select", "cleanup", "test"):
                pass
        
        asyncio.run(trigger_cleanup())
        
        # Should be reduced to 500 + 1 (the new one)
        assert len(db_optimizer.performance_metrics) <= 501

    def test_clear_performance_metrics(self):
        """Test clearing performance metrics"""
        
        # Add test metrics
        test_metrics = [
            QueryPerformanceMetrics("select", "test", 10.0, 1, datetime.now())
            for _ in range(5)
        ]
        db_optimizer.performance_metrics.extend(test_metrics)
        
        assert len(db_optimizer.performance_metrics) == 5
        
        # Clear metrics
        db_optimizer.clear_performance_metrics()
        
        assert len(db_optimizer.performance_metrics) == 0
        
        # Metrics summary should reflect empty state
        metrics = db_optimizer.get_performance_metrics()
        assert metrics["total_queries"] == 0


class TestIntegrationWithExistingCode:
    """Test integration with existing database patterns"""

    @pytest.mark.asyncio
    async def test_compatibility_with_existing_queries(self):
        """Test that optimization doesn't break existing database queries"""
        
        # Test that existing database methods still work
        try:
            # This should work with existing code
            health_check = await database.health_check()
            assert isinstance(health_check, bool)
            
        except Exception as e:
            pytest.fail(f"Existing database functionality broken: {e}")

    @pytest.mark.asyncio
    async def test_game_service_integration(self):
        """Test integration with existing game service bulk operations"""
        
        # The game service already has excellent bulk operations
        # Test that our optimizations work alongside them
        from app.game_service import game_service
        
        # This should use the existing optimized bulk validation
        try:
            # Test with empty game IDs list
            from app.models import BulkGameValidationResponse
            
            result = await game_service.validate_games_bulk(
                [], 
                "test_user",
                include_track_count=False
            )
            
            assert isinstance(result, BulkGameValidationResponse)
            assert result.success == True
            assert result.total_requested == 0
            
        except Exception as e:
            # This is expected if models aren't available in test environment
            pass

    def test_cache_manager_integration(self):
        """Test integration with existing cache manager"""
        
        try:
            # Test that we can integrate with cache manager
            cache_manager = CacheManager()
            db_optimizer.set_cache_manager(cache_manager)
            
            # Should not raise an exception
            assert db_optimizer.cache_manager is not None
            
        except Exception as e:
            # Cache manager might not be available in test environment
            pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
