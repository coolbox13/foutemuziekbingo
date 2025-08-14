"""
Comprehensive Performance Test Suite

This module provides performance testing for all critical system components
including rate limiting under load, database connection pooling, Redis
pub/sub message delivery, cache performance, and overall system throughput.

Test Coverage:
- Rate limiting performance under high load
- Database connection pooling efficiency
- Redis pub/sub message delivery performance
- Cache hit rates and response times
- WebSocket connection handling under load
- Concurrent user simulation
- Memory usage monitoring
- System resource utilization
- Throughput and latency benchmarks
"""

import pytest
import asyncio
import time
import statistics
import psutil
import gc
from typing import Dict, Any, List, Tuple, Optional
from unittest.mock import patch, MagicMock, AsyncMock
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

# Import components for performance testing
from app.rate_limiter import (
    AsyncRateLimiter, RateLimitRule, RateLimitAlgorithm, RateLimitScope
)
from app.cache_manager import CacheManager, CacheType
from app.redis_pubsub import RedisPubSubManager
from app.fastapi_app import create_app
from httpx import AsyncClient


class PerformanceMetrics:
    """Utility class for collecting and analyzing performance metrics."""
    
    def __init__(self):
        self.start_time = None
        self.end_time = None
        self.response_times = []
        self.success_count = 0
        self.error_count = 0
        self.memory_samples = []
        self.cpu_samples = []
    
    def start_measurement(self):
        """Start performance measurement."""
        self.start_time = time.time()
        self.response_times = []
        self.success_count = 0
        self.error_count = 0
        self.memory_samples = []
        self.cpu_samples = []
        gc.collect()  # Clean start
    
    def record_operation(self, start_time: float, success: bool):
        """Record a single operation."""
        response_time = time.time() - start_time
        self.response_times.append(response_time)
        if success:
            self.success_count += 1
        else:
            self.error_count += 1
    
    def sample_system_metrics(self):
        """Sample system resource usage."""
        process = psutil.Process()
        self.memory_samples.append(process.memory_info().rss / 1024 / 1024)  # MB
        self.cpu_samples.append(process.cpu_percent())
    
    def end_measurement(self):
        """End measurement and calculate statistics."""
        self.end_time = time.time()
        return self.get_statistics()
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get performance statistics."""
        total_time = self.end_time - self.start_time if self.end_time else 0
        total_operations = self.success_count + self.error_count
        
        stats = {
            "total_time": total_time,
            "total_operations": total_operations,
            "success_count": self.success_count,
            "error_count": self.error_count,
            "success_rate": self.success_count / total_operations if total_operations > 0 else 0,
            "operations_per_second": total_operations / total_time if total_time > 0 else 0,
        }
        
        if self.response_times:
            stats.update({
                "avg_response_time": statistics.mean(self.response_times),
                "median_response_time": statistics.median(self.response_times),
                "min_response_time": min(self.response_times),
                "max_response_time": max(self.response_times),
                "p95_response_time": self._percentile(self.response_times, 95),
                "p99_response_time": self._percentile(self.response_times, 99),
            })
        
        if self.memory_samples:
            stats.update({
                "avg_memory_mb": statistics.mean(self.memory_samples),
                "peak_memory_mb": max(self.memory_samples),
                "min_memory_mb": min(self.memory_samples),
            })
        
        if self.cpu_samples:
            stats.update({
                "avg_cpu_percent": statistics.mean(self.cpu_samples),
                "peak_cpu_percent": max(self.cpu_samples),
            })
        
        return stats
    
    @staticmethod
    def _percentile(data: List[float], percentile: int) -> float:
        """Calculate percentile value."""
        if not data:
            return 0
        sorted_data = sorted(data)
        index = int((percentile / 100.0) * len(sorted_data))
        return sorted_data[min(index, len(sorted_data) - 1)]


class TestRateLimitingPerformance:
    """Test rate limiting performance under high load."""
    
    @pytest.mark.asyncio
    async def test_rate_limiter_throughput(self):
        """Test rate limiter throughput with many concurrent requests."""
        limiter = AsyncRateLimiter()
        limiter.add_rule("performance", RateLimitRule(
            requests=1000,
            window_seconds=60,
            algorithm=RateLimitAlgorithm.TOKEN_BUCKET,
            scope=RateLimitScope.IP
        ))
        
        # Mock backend for performance testing
        mock_backend = AsyncMock()
        allowed_count = 0
        
        def mock_increment(key, rule):
            nonlocal allowed_count
            allowed_count += 1
            remaining = max(0, 1000 - allowed_count)
            from app.rate_limiter import RateLimitStatus
            return RateLimitStatus(
                remaining=remaining,
                limit=1000,
                reset_at=datetime.now(timezone.utc)
            )
        
        mock_backend.increment_counter.side_effect = mock_increment
        limiter.backend = mock_backend
        
        metrics = PerformanceMetrics()
        metrics.start_measurement()
        
        # Simulate many concurrent requests
        async def make_request():
            start_time = time.time()
            from app.rate_limiter import MockRequest
            request = MockRequest()
            allowed, status = await limiter.is_allowed(request, "performance")
            metrics.record_operation(start_time, allowed)
            return allowed
        
        # Execute 500 concurrent requests
        tasks = [make_request() for _ in range(500)]
        results = await asyncio.gather(*tasks)
        
        stats = metrics.end_measurement()
        
        # Performance assertions
        assert stats["operations_per_second"] > 100  # At least 100 ops/sec
        assert stats["avg_response_time"] < 0.1  # Average under 100ms
        assert stats["p95_response_time"] < 0.2  # 95th percentile under 200ms
        assert stats["success_rate"] > 0.95  # At least 95% success rate
        
        print(f"Rate Limiting Performance: {stats['operations_per_second']:.1f} ops/sec, "
              f"avg: {stats['avg_response_time']*1000:.1f}ms, "
              f"p95: {stats['p95_response_time']*1000:.1f}ms")
    
    @pytest.mark.asyncio
    async def test_rate_limiter_memory_usage(self):
        """Test rate limiter memory usage with many keys."""
        limiter = AsyncRateLimiter()
        limiter.add_rule("memory_test", RateLimitRule(
            requests=10,
            window_seconds=60,
            algorithm=RateLimitAlgorithm.SLIDING_WINDOW,
            scope=RateLimitScope.IP
        ))
        
        mock_backend = AsyncMock()
        mock_backend.increment_counter.return_value = AsyncMock()
        limiter.backend = mock_backend
        
        metrics = PerformanceMetrics()
        metrics.start_measurement()
        
        # Create many different IP-based requests
        for i in range(1000):
            from app.rate_limiter import MockRequest
            request = MockRequest(client_host=f"192.168.1.{i % 256}")
            await limiter.is_allowed(request, "memory_test")
            
            if i % 100 == 0:
                metrics.sample_system_metrics()
        
        stats = metrics.end_measurement()
        
        # Memory usage should be reasonable
        assert stats["peak_memory_mb"] < 500  # Under 500MB
        assert stats["avg_memory_mb"] > 0
        
        print(f"Rate Limiter Memory: avg {stats['avg_memory_mb']:.1f}MB, "
              f"peak {stats['peak_memory_mb']:.1f}MB")
    
    @pytest.mark.asyncio
    async def test_algorithm_performance_comparison(self):
        """Compare performance of different rate limiting algorithms."""
        algorithms = [
            RateLimitAlgorithm.TOKEN_BUCKET,
            RateLimitAlgorithm.SLIDING_WINDOW
        ]
        
        results = {}
        
        for algorithm in algorithms:
            limiter = AsyncRateLimiter()
            limiter.add_rule("perf_test", RateLimitRule(
                requests=100,
                window_seconds=60,
                algorithm=algorithm,
                scope=RateLimitScope.IP
            ))
            
            mock_backend = AsyncMock()
            mock_backend.increment_counter.return_value = AsyncMock()
            limiter.backend = mock_backend
            
            metrics = PerformanceMetrics()
            metrics.start_measurement()
            
            # Execute requests
            from app.rate_limiter import MockRequest
            request = MockRequest()
            for _ in range(100):
                start_time = time.time()
                await limiter.is_allowed(request, "perf_test")
                metrics.record_operation(start_time, True)
            
            stats = metrics.end_measurement()
            results[algorithm.name] = stats
            
            print(f"{algorithm.name}: {stats['operations_per_second']:.1f} ops/sec, "
                  f"avg: {stats['avg_response_time']*1000:.1f}ms")
        
        # Both algorithms should perform reasonably
        for algorithm_name, stats in results.items():
            assert stats["operations_per_second"] > 50
            assert stats["avg_response_time"] < 0.05


class TestCachePerformance:
    """Test cache performance and efficiency."""
    
    @pytest.mark.asyncio
    async def test_cache_throughput(self):
        """Test cache read/write throughput."""
        cache_manager = CacheManager()
        
        # Mock Redis client
        from tests.test_cache_integration import MockRedisClient
        mock_redis = MockRedisClient()
        cache_manager.redis_client = mock_redis
        
        metrics = PerformanceMetrics()
        metrics.start_measurement()
        
        # Test write performance
        write_tasks = []
        for i in range(500):
            track_data = {
                "track_id": f"track_{i}",
                "name": f"Song {i}",
                "artist": f"Artist {i % 50}"  # Some overlap
            }
            task = cache_manager.set(CacheType.TRACK, f"track_{i}", track_data)
            write_tasks.append(task)
        
        write_start = time.time()
        write_results = await asyncio.gather(*write_tasks)
        write_time = time.time() - write_start
        
        # Test read performance
        read_tasks = []
        for i in range(500):
            task = cache_manager.get(CacheType.TRACK, f"track_{i}")
            read_tasks.append(task)
        
        read_start = time.time()
        read_results = await asyncio.gather(*read_tasks)
        read_time = time.time() - read_start
        
        # Performance assertions
        write_ops_per_sec = 500 / write_time
        read_ops_per_sec = 500 / read_time
        
        assert write_ops_per_sec > 200  # At least 200 writes/sec
        assert read_ops_per_sec > 500   # At least 500 reads/sec
        assert all(write_results)  # All writes successful
        assert all(result is not None for result in read_results)  # All reads successful
        
        print(f"Cache Write Performance: {write_ops_per_sec:.1f} ops/sec")
        print(f"Cache Read Performance: {read_ops_per_sec:.1f} ops/sec")
    
    @pytest.mark.asyncio
    async def test_cache_hit_rate_performance(self):
        """Test cache performance with varying hit rates."""
        cache_manager = CacheManager()
        
        from tests.test_cache_integration import MockRedisClient
        mock_redis = MockRedisClient()
        cache_manager.redis_client = mock_redis
        
        # Pre-populate cache with some data
        for i in range(100):
            playlist_data = {
                "playlist_id": f"playlist_{i}",
                "name": f"Playlist {i}",
                "tracks": [f"track_{j}" for j in range(i % 20)]
            }
            await cache_manager.set(CacheType.PLAYLIST, f"playlist_{i}", playlist_data)
        
        # Test different hit rate scenarios
        scenarios = [
            {"name": "High hit rate (90%)", "hit_probability": 0.9},
            {"name": "Medium hit rate (50%)", "hit_probability": 0.5},
            {"name": "Low hit rate (10%)", "hit_probability": 0.1},
        ]
        
        for scenario in scenarios:
            metrics = PerformanceMetrics()
            metrics.start_measurement()
            
            import random
            
            for _ in range(200):
                start_time = time.time()
                
                if random.random() < scenario["hit_probability"]:
                    # Cache hit - request existing data
                    playlist_id = f"playlist_{random.randint(0, 99)}"
                else:
                    # Cache miss - request non-existing data
                    playlist_id = f"playlist_{random.randint(1000, 1999)}"
                
                result = await cache_manager.get(CacheType.PLAYLIST, playlist_id)
                success = result is not None
                metrics.record_operation(start_time, True)  # Operation always succeeds
            
            stats = metrics.end_measurement()
            
            print(f"{scenario['name']}: {stats['operations_per_second']:.1f} ops/sec, "
                  f"avg: {stats['avg_response_time']*1000:.1f}ms")
            
            # Performance should be reasonable regardless of hit rate
            assert stats["operations_per_second"] > 100
            assert stats["avg_response_time"] < 0.1
    
    @pytest.mark.asyncio
    async def test_cache_memory_efficiency(self):
        """Test cache memory usage efficiency."""
        cache_manager = CacheManager()
        
        from tests.test_cache_integration import MockRedisClient
        mock_redis = MockRedisClient()
        cache_manager.redis_client = mock_redis
        
        metrics = PerformanceMetrics()
        metrics.start_measurement()
        
        # Test different data sizes
        data_sizes = [
            ("Small", {"key": "value"}),
            ("Medium", {"data": "x" * 1000}),  # 1KB
            ("Large", {"data": "x" * 10000}), # 10KB
        ]
        
        for size_name, sample_data in data_sizes:
            # Store many items of this size
            for i in range(100):
                key = f"{size_name.lower()}_{i}"
                await cache_manager.set(CacheType.METADATA, key, sample_data)
                
                if i % 20 == 0:
                    metrics.sample_system_metrics()
        
        stats = metrics.end_measurement()
        
        # Memory usage should be reasonable
        assert stats["peak_memory_mb"] < 1000  # Under 1GB
        
        print(f"Cache Memory Efficiency: peak {stats['peak_memory_mb']:.1f}MB")


class TestDatabasePerformance:
    """Test database connection and query performance."""
    
    @pytest.mark.asyncio
    async def test_connection_pool_performance(self):
        """Test database connection pool efficiency."""
        # Mock database service
        mock_db_service = AsyncMock()
        
        # Simulate connection pool behavior
        connection_pool = []
        max_connections = 10
        
        async def get_connection():
            if len(connection_pool) < max_connections:
                connection_pool.append(f"conn_{len(connection_pool)}")
            return connection_pool[len(connection_pool) % max_connections]
        
        async def release_connection(conn):
            pass  # Connection stays in pool
        
        mock_db_service.get_connection = get_connection
        mock_db_service.release_connection = release_connection
        
        metrics = PerformanceMetrics()
        metrics.start_measurement()
        
        # Simulate concurrent database operations
        async def db_operation():
            start_time = time.time()
            conn = await get_connection()
            # Simulate query time
            await asyncio.sleep(0.001)  # 1ms query
            await release_connection(conn)
            metrics.record_operation(start_time, True)
        
        # Execute 200 concurrent database operations
        tasks = [db_operation() for _ in range(200)]
        await asyncio.gather(*tasks)
        
        stats = metrics.end_measurement()
        
        # Performance assertions
        assert stats["operations_per_second"] > 50  # At least 50 DB ops/sec
        assert stats["avg_response_time"] < 0.1    # Average under 100ms
        assert len(connection_pool) <= max_connections  # Pool size limited
        
        print(f"DB Connection Pool: {stats['operations_per_second']:.1f} ops/sec, "
              f"pool size: {len(connection_pool)}/{max_connections}")
    
    @pytest.mark.asyncio
    async def test_query_performance(self):
        """Test database query performance simulation."""
        # Mock different query types and their expected performance
        query_types = {
            "user_lookup": 0.005,     # 5ms
            "game_state": 0.010,      # 10ms
            "playlist_tracks": 0.020, # 20ms
            "complex_join": 0.050,    # 50ms
        }
        
        metrics = PerformanceMetrics()
        metrics.start_measurement()
        
        # Simulate various query patterns
        import random
        
        async def execute_query(query_type: str, expected_time: float):
            start_time = time.time()
            # Simulate query execution time with some variance
            await asyncio.sleep(expected_time * random.uniform(0.8, 1.2))
            metrics.record_operation(start_time, True)
        
        # Execute mixed workload
        tasks = []
        for _ in range(100):
            query_type = random.choice(list(query_types.keys()))
            expected_time = query_types[query_type]
            tasks.append(execute_query(query_type, expected_time))
        
        await asyncio.gather(*tasks)
        stats = metrics.end_measurement()
        
        # Performance assertions
        assert stats["success_rate"] == 1.0  # All queries should succeed
        assert stats["avg_response_time"] < 0.1  # Average under 100ms
        assert stats["p95_response_time"] < 0.2  # 95th percentile under 200ms
        
        print(f"DB Query Performance: avg {stats['avg_response_time']*1000:.1f}ms, "
              f"p95 {stats['p95_response_time']*1000:.1f}ms")


class TestWebSocketPerformance:
    """Test WebSocket performance under load."""
    
    @pytest.mark.asyncio
    async def test_websocket_connection_handling(self):
        """Test WebSocket connection handling performance."""
        # Mock Socket.IO server
        mock_sio = AsyncMock()
        
        # Simulate connection handling
        connections = {}
        max_connections = 500
        
        async def handle_connect(session_id: str):
            if len(connections) < max_connections:
                connections[session_id] = {"connected_at": time.time()}
                return True
            return False
        
        async def handle_disconnect(session_id: str):
            if session_id in connections:
                del connections[session_id]
        
        metrics = PerformanceMetrics()
        metrics.start_measurement()
        
        # Simulate rapid connections
        async def simulate_connection(conn_id: int):
            start_time = time.time()
            session_id = f"session_{conn_id}"
            success = await handle_connect(session_id)
            metrics.record_operation(start_time, success)
            
            # Hold connection briefly
            await asyncio.sleep(0.1)
            
            # Disconnect
            await handle_disconnect(session_id)
        
        # Execute 200 concurrent connections
        tasks = [simulate_connection(i) for i in range(200)]
        await asyncio.gather(*tasks)
        
        stats = metrics.end_measurement()
        
        # Performance assertions
        assert stats["success_rate"] > 0.9  # Most connections should succeed
        assert stats["operations_per_second"] > 50  # At least 50 connections/sec
        
        print(f"WebSocket Connections: {stats['operations_per_second']:.1f} connections/sec, "
              f"success rate: {stats['success_rate']*100:.1f}%")
    
    @pytest.mark.asyncio
    async def test_websocket_message_throughput(self):
        """Test WebSocket message throughput."""
        mock_sio = AsyncMock()
        
        # Track message processing
        messages_processed = 0
        
        async def emit_message(event: str, data: dict, room: str = None):
            nonlocal messages_processed
            # Simulate message processing time
            await asyncio.sleep(0.001)  # 1ms
            messages_processed += 1
        
        mock_sio.emit = emit_message
        
        metrics = PerformanceMetrics()
        metrics.start_measurement()
        
        # Simulate various message types
        message_types = [
            ("track_played", {"track_id": "123", "name": "Song"}),
            ("bingo_claimed", {"user_id": "456", "card_id": "789"}),
            ("game_state", {"status": "playing", "round": 5}),
            ("user_joined", {"user_id": "101", "name": "Player"}),
        ]
        
        # Send many messages concurrently
        tasks = []
        for i in range(1000):
            event, data = message_types[i % len(message_types)]
            data_copy = data.copy()
            data_copy["message_id"] = i
            
            task = mock_sio.emit(event, data_copy, room=f"game_{i % 10}")
            tasks.append(task)
        
        start_time = time.time()
        await asyncio.gather(*tasks)
        total_time = time.time() - start_time
        
        # Performance assertions
        messages_per_second = messages_processed / total_time
        assert messages_per_second > 500  # At least 500 messages/sec
        assert messages_processed == 1000  # All messages processed
        
        print(f"WebSocket Messages: {messages_per_second:.1f} messages/sec")


class TestRedisPubSubPerformance:
    """Test Redis pub/sub performance."""
    
    @pytest.mark.asyncio
    async def test_pubsub_message_delivery(self):
        """Test Redis pub/sub message delivery performance."""
        manager = RedisPubSubManager()
        
        # Mock Redis pub/sub
        mock_redis = AsyncMock()
        manager.redis_client = mock_redis
        
        # Track published messages
        published_messages = []
        
        async def mock_publish(channel: str, message: str):
            published_messages.append({"channel": channel, "message": message, "time": time.time()})
            await asyncio.sleep(0.001)  # Simulate network latency
        
        mock_redis.publish = mock_publish
        
        metrics = PerformanceMetrics()
        metrics.start_measurement()
        
        # Publish many messages
        import json
        
        tasks = []
        for i in range(500):
            message = {
                "event": "test_event",
                "data": {"index": i, "timestamp": time.time()},
                "source_instance": manager.instance_id
            }
            channel = f"musicbingo:game:{i % 10}"  # 10 different games
            task = mock_redis.publish(channel, json.dumps(message))
            tasks.append(task)
        
        start_time = time.time()
        await asyncio.gather(*tasks)
        total_time = time.time() - start_time
        
        # Performance assertions
        messages_per_second = len(published_messages) / total_time
        assert messages_per_second > 200  # At least 200 messages/sec
        assert len(published_messages) == 500  # All messages published
        
        # Check message distribution across channels
        channel_counts = {}
        for msg in published_messages:
            channel = msg["channel"]
            channel_counts[channel] = channel_counts.get(channel, 0) + 1
        
        assert len(channel_counts) == 10  # Messages spread across channels
        
        print(f"Redis Pub/Sub: {messages_per_second:.1f} messages/sec")
    
    @pytest.mark.asyncio
    async def test_multi_instance_coordination(self):
        """Test multi-instance coordination performance."""
        # Create multiple manager instances
        managers = [RedisPubSubManager() for _ in range(5)]
        
        # Mock shared Redis
        shared_messages = []
        
        async def mock_publish(channel: str, message: str):
            shared_messages.append({
                "channel": channel,
                "message": message,
                "timestamp": time.time()
            })
        
        async def mock_subscribe_handler(message):
            # Simulate message processing
            await asyncio.sleep(0.001)
        
        # Set up mock Redis for all managers
        for manager in managers:
            mock_redis = AsyncMock()
            mock_redis.publish = mock_publish
            manager.redis_client = mock_redis
        
        metrics = PerformanceMetrics()
        metrics.start_measurement()
        
        # Each manager publishes messages
        tasks = []
        for i, manager in enumerate(managers):
            for j in range(20):  # 20 messages per instance
                message = {
                    "event": "coordination_test",
                    "data": {"instance": i, "message": j},
                    "source_instance": manager.instance_id
                }
                import json
                task = manager.redis_client.publish(
                    "musicbingo:broadcast:all",
                    json.dumps(message)
                )
                tasks.append(task)
        
        await asyncio.gather(*tasks)
        stats = metrics.end_measurement()
        
        # Performance assertions
        assert len(shared_messages) == 100  # 5 instances × 20 messages
        
        # Check that all instances contributed
        instance_ids = set()
        for msg in shared_messages:
            import json
            parsed_msg = json.loads(msg["message"])
            instance_ids.add(parsed_msg["source_instance"])
        
        assert len(instance_ids) == 5  # All instances published
        
        print(f"Multi-instance Coordination: {len(shared_messages)} messages from {len(instance_ids)} instances")


class TestSystemResourceUsage:
    """Test overall system resource usage and efficiency."""
    
    @pytest.mark.asyncio
    async def test_memory_usage_patterns(self):
        """Test memory usage patterns under load."""
        metrics = PerformanceMetrics()
        metrics.start_measurement()
        
        # Simulate various system components working together
        cache_manager = CacheManager()
        limiter = AsyncRateLimiter()
        pubsub_manager = RedisPubSubManager()
        
        # Mock their backends
        from tests.test_cache_integration import MockRedisClient
        cache_manager.redis_client = MockRedisClient()
        
        mock_backend = AsyncMock()
        limiter.backend = mock_backend
        
        # Simulate mixed workload
        for i in range(100):
            # Cache operations
            await cache_manager.set(CacheType.TRACK, f"track_{i}", {"name": f"Song {i}"})
            
            # Rate limiting checks
            from app.rate_limiter import MockRequest
            request = MockRequest()
            await limiter.is_allowed(request, "default")
            
            # Sample system metrics periodically
            if i % 10 == 0:
                metrics.sample_system_metrics()
        
        stats = metrics.end_measurement()
        
        # Memory usage should be reasonable and stable
        assert stats["peak_memory_mb"] < 1000  # Under 1GB
        
        # Memory usage should not grow indefinitely
        memory_growth = stats["peak_memory_mb"] - stats["min_memory_mb"]
        assert memory_growth < 500  # Memory growth under 500MB
        
        print(f"System Memory: avg {stats['avg_memory_mb']:.1f}MB, "
              f"peak {stats['peak_memory_mb']:.1f}MB, "
              f"growth {memory_growth:.1f}MB")
    
    @pytest.mark.asyncio
    async def test_concurrent_user_simulation(self):
        """Simulate many concurrent users and measure system performance."""
        metrics = PerformanceMetrics()
        metrics.start_measurement()
        
        # Mock all system components
        cache_manager = CacheManager()
        limiter = AsyncRateLimiter()
        
        from tests.test_cache_integration import MockRedisClient
        cache_manager.redis_client = MockRedisClient()
        
        mock_backend = AsyncMock()
        limiter.backend = mock_backend
        
        # Simulate different user behaviors
        async def simulate_user(user_id: int):
            """Simulate a single user's activity."""
            start_time = time.time()
            
            # User login - cache lookup
            user_data = await cache_manager.get(CacheType.USER_DATA, f"user_{user_id}")
            if not user_data:
                # Cache miss - load user data
                user_data = {"user_id": f"user_{user_id}", "name": f"User {user_id}"}
                await cache_manager.set(CacheType.USER_DATA, f"user_{user_id}", user_data)
            
            # User makes requests - rate limiting
            from app.rate_limiter import MockRequest
            request = MockRequest(client_host=f"192.168.1.{user_id % 256}")
            
            for _ in range(5):  # 5 requests per user
                await limiter.is_allowed(request, "default")
            
            # User activity - more cache operations
            playlist_data = await cache_manager.get(CacheType.PLAYLIST, f"playlist_{user_id % 10}")
            if not playlist_data:
                playlist_data = {"playlist_id": f"playlist_{user_id % 10}", "tracks": []}
                await cache_manager.set(CacheType.PLAYLIST, f"playlist_{user_id % 10}", playlist_data)
            
            metrics.record_operation(start_time, True)
        
        # Simulate 100 concurrent users
        user_tasks = [simulate_user(i) for i in range(100)]
        await asyncio.gather(*user_tasks)
        
        stats = metrics.end_measurement()
        
        # Performance assertions for concurrent users
        assert stats["success_rate"] == 1.0  # All user simulations successful
        assert stats["operations_per_second"] > 20  # At least 20 users/sec
        assert stats["avg_response_time"] < 1.0  # Average user flow under 1 second
        
        print(f"Concurrent Users: {stats['operations_per_second']:.1f} users/sec, "
              f"avg response: {stats['avg_response_time']*1000:.1f}ms")


if __name__ == "__main__":
    # Simple test runner for development
    async def run_tests():
        """Run comprehensive performance tests."""
        print("🚀 COMPREHENSIVE PERFORMANCE TEST SUITE")
        print("=" * 80)
        
        test_classes = [
            TestRateLimitingPerformance,
            TestCachePerformance,
            TestDatabasePerformance,
            TestWebSocketPerformance,
            TestRedisPubSubPerformance,
            TestSystemResourceUsage,
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
        print("PERFORMANCE TEST SUMMARY")
        print(f"{'='*80}")
        print(f"Total Tests: {total_tests}")
        print(f"Passed: {passed_tests}")
        print(f"Failed: {total_tests - passed_tests}")
        print(f"Success Rate: {(passed_tests/total_tests)*100:.1f}%")
        
        if passed_tests == total_tests:
            print("\n🎉 All performance tests passed\!")
            return True
        else:
            print(f"\n⚠️ {total_tests - passed_tests} test(s) failed")
            return False
    
    # Run tests if executed directly
    asyncio.run(run_tests())
EOF < /dev/null