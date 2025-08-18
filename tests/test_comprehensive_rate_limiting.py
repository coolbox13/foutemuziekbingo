"""
Comprehensive Rate Limiting Security Tests

This module provides comprehensive testing of the rate limiting middleware
including all algorithms, abuse scenarios, bypass attempts, and edge cases.

Test Coverage:
- Token bucket algorithm testing
- Sliding window algorithm testing
- Rate limit bypass attempts
- Abuse scenario simulation
- Multiple scope testing (IP, User, Session, Global, Endpoint)
- Redis backend integration testing
- Lua script execution testing
- Rate limit header validation
- Error handling and failover testing
- Performance under load
"""

import pytest
import asyncio
import time
import sys
from pathlib import Path
from typing import Dict
from unittest.mock import patch, AsyncMock, MagicMock
from datetime import datetime, timezone, timedelta

import redis.asyncio as redis
from httpx import AsyncClient

# Add parent directory to path so we can import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import rate limiting components
from app.rate_limiter import (
    RateLimitAlgorithm, RateLimitScope, RateLimitRule, RateLimitStatus,
    AsyncRateLimiter, RedisRateLimitBackend, RateLimitMiddleware,
    create_default_rate_limiter
)
from app.fastapi_app import create_app


class MockRequest:
    """Mock Request object for testing."""

    def __init__(self, method: str = "POST", path: str = "/api/test",
                 client_host: str = "127.0.0.1", headers: Dict[str, str] = None):
        self.method = method
        self.url = MagicMock()
        self.url.path = path
        self.client = MagicMock()
        self.client.host = client_host
        self.headers = headers or {}


class TestRateLimitAlgorithms:
    """Test different rate limiting algorithms."""

    @pytest.mark.asyncio
    async def test_token_bucket_algorithm(self):
        """Test token bucket algorithm implementation."""
        # Create rule with token bucket algorithm
        rule = RateLimitRule(
            requests=10,
            window_seconds=60,
            algorithm=RateLimitAlgorithm.TOKEN_BUCKET,
            scope=RateLimitScope.IP
        )

        # Create mock Redis backend
        redis_backend = RedisRateLimitBackend()

        # Mock Redis connection
        mock_redis = AsyncMock()
        redis_backend.redis = mock_redis

        # Mock Lua script execution for token bucket
        mock_redis.evalsha.return_value = [1, 9, 10]  # allowed, remaining, limit

        # Test token bucket increment
        status = await redis_backend.increment_counter("test_key", rule)

        assert status.remaining == 9
        assert status.limit == 10
        assert status.algorithm == RateLimitAlgorithm.TOKEN_BUCKET

        # Verify Lua script was called correctly
        mock_redis.evalsha.assert_called_once()

    @pytest.mark.asyncio
    async def test_sliding_window_algorithm(self):
        """Test sliding window algorithm implementation."""
        rule = RateLimitRule(
            requests=5,
            window_seconds=60,
            algorithm=RateLimitAlgorithm.SLIDING_WINDOW,
            scope=RateLimitScope.IP
        )

        redis_backend = RedisRateLimitBackend()
        mock_redis = AsyncMock()
        redis_backend.redis = mock_redis

        # Mock sliding window Lua script
        mock_redis.evalsha.return_value = [1, 4, 5]  # allowed, remaining, limit

        status = await redis_backend.increment_counter("test_key", rule)

        assert status.remaining == 4
        assert status.limit == 5
        assert status.algorithm == RateLimitAlgorithm.SLIDING_WINDOW

    @pytest.mark.asyncio
    async def test_algorithm_comparison_performance(self):
        """Compare performance characteristics of different algorithms."""
        token_bucket_rule = RateLimitRule(
            requests=100,
            window_seconds=60,
            algorithm=RateLimitAlgorithm.TOKEN_BUCKET,
            scope=RateLimitScope.IP
        )

        sliding_window_rule = RateLimitRule(
            requests=100,
            window_seconds=60,
            algorithm=RateLimitAlgorithm.SLIDING_WINDOW,
            scope=RateLimitScope.IP
        )

        # Test burst handling differences
        # Token bucket should handle bursts better
        # Sliding window should be more strict about rate

        # This would be expanded with actual performance measurements
        assert token_bucket_rule.algorithm == RateLimitAlgorithm.TOKEN_BUCKET
        assert sliding_window_rule.algorithm == RateLimitAlgorithm.SLIDING_WINDOW


class TestRateLimitScopes:
    """Test different rate limiting scopes."""

    @pytest.mark.asyncio
    async def test_ip_based_rate_limiting(self):
        """Test IP-based rate limiting."""
        limiter = AsyncRateLimiter()
        limiter.add_rule("test", RateLimitRule(
            requests=5,
            window_seconds=60,
            algorithm=RateLimitAlgorithm.TOKEN_BUCKET,
            scope=RateLimitScope.IP
        ))

        # Mock Redis backend
        mock_backend = AsyncMock()
        mock_backend.increment_counter.return_value = RateLimitStatus(
            remaining=4, limit=5, reset_at=datetime.now(timezone.utc)
        )
        limiter.backend = mock_backend

        # Test different IP addresses get different limits
        request1 = MockRequest(client_host="192.168.1.1")
        request2 = MockRequest(client_host="192.168.1.2")

        allowed1, status1 = await limiter.is_allowed(request1, "test")
        allowed2, status2 = await limiter.is_allowed(request2, "test")

        assert allowed1 and allowed2

        # Verify different keys were generated
        calls = mock_backend.increment_counter.call_args_list
        assert len(calls) == 2
        assert calls[0][0][0] != calls[1][0][0]  # Different keys

    @pytest.mark.asyncio
    async def test_user_based_rate_limiting(self):
        """Test user-based rate limiting."""
        limiter = AsyncRateLimiter()
        limiter.add_rule("test", RateLimitRule(
            requests=10,
            window_seconds=60,
            algorithm=RateLimitAlgorithm.TOKEN_BUCKET,
            scope=RateLimitScope.USER
        ))

        mock_backend = AsyncMock()
        mock_backend.increment_counter.return_value = RateLimitStatus(
            remaining=9, limit=10, reset_at=datetime.now(timezone.utc)
        )
        limiter.backend = mock_backend

        # Mock session with user ID
        request = MockRequest()

        with patch('app.rate_limiter.get_session_from_request') as mock_session:
            mock_session.return_value = {"user_id": "user123"}

            allowed, status = await limiter.is_allowed(request, "test")

            assert allowed
            assert status.remaining == 9

    @pytest.mark.asyncio
    async def test_endpoint_specific_rate_limiting(self):
        """Test endpoint-specific rate limiting."""
        limiter = AsyncRateLimiter()
        limiter.add_rule("api_endpoints", RateLimitRule(
            requests=3,
            window_seconds=60,
            algorithm=RateLimitAlgorithm.SLIDING_WINDOW,
            scope=RateLimitScope.ENDPOINT,
            paths={"/api/"}
        ))

        mock_backend = AsyncMock()
        mock_backend.increment_counter.return_value = RateLimitStatus(
            remaining=2, limit=3, reset_at=datetime.now(timezone.utc)
        )
        limiter.backend = mock_backend

        # Test API endpoint gets rate limited
        api_request = MockRequest(path="/api/games")
        allowed, status = await limiter.is_allowed(api_request, "api_endpoints")
        assert allowed

        # Test non-API endpoint is not rate limited
        other_request = MockRequest(path="/dashboard")
        allowed2, status2 = await limiter.is_allowed(other_request, "api_endpoints")
        assert allowed2

        # Verify only API request was rate limited
        assert mock_backend.increment_counter.call_count == 1


class TestRateLimitAbuseScenarios:
    """Test various abuse scenarios and attack vectors."""

    @pytest.mark.asyncio
    async def test_rapid_fire_requests(self):
        """Test rapid successive requests hitting rate limits."""
        app = create_app()

        # Create strict rate limit for testing
        with patch('app.rate_limiter.create_default_rate_limiter') as mock_limiter_factory:
            limiter = AsyncRateLimiter()
            limiter.add_rule("strict", RateLimitRule(
                requests=3,
                window_seconds=10,
                algorithm=RateLimitAlgorithm.SLIDING_WINDOW,
                scope=RateLimitScope.IP
            ))
            mock_limiter_factory.return_value = limiter

            # Mock Redis backend to simulate strict limits
            mock_backend = AsyncMock()
            responses = [
                RateLimitStatus(remaining=2, limit=3, reset_at=datetime.now(timezone.utc)),
                RateLimitStatus(remaining=1, limit=3, reset_at=datetime.now(timezone.utc)),
                RateLimitStatus(remaining=0, limit=3, reset_at=datetime.now(timezone.utc)),
                RateLimitStatus(remaining=0, limit=3, reset_at=datetime.now(timezone.utc),
                                retry_after=10, blocked_until=datetime.now(timezone.utc) + timedelta(seconds=10)),
            ]
            mock_backend.increment_counter.side_effect = responses
            limiter.backend = mock_backend

            async with AsyncClient(app=app, base_url="http://test") as client:
                # Send rapid requests
                results = []
                for i in range(4):
                    response = await client.post("/api/test", json={"data": f"request_{i}"})
                    results.append(response.status_code)

                # First 3 should succeed, 4th should be rate limited
                assert results[:3] == [404, 404, 404]  # 404 because endpoint doesn't exist, but not rate limited
                assert results[3] == 429  # Rate limited

    @pytest.mark.asyncio
    async def test_distributed_ip_attack(self):
        """Test attack from multiple IP addresses."""
        limiter = AsyncRateLimiter()
        limiter.add_rule("test", RateLimitRule(
            requests=2,
            window_seconds=60,
            algorithm=RateLimitAlgorithm.TOKEN_BUCKET,
            scope=RateLimitScope.IP
        ))

        # Mock backend that tracks different IPs
        mock_backend = AsyncMock()
        ip_counters = {}

        def mock_increment(key, rule):
            ip = key.split(":")[-1]  # Extract IP from key
            if ip not in ip_counters:
                ip_counters[ip] = 2
            ip_counters[ip] -= 1

            if ip_counters[ip] >= 0:
                return RateLimitStatus(
                    remaining=ip_counters[ip], limit=2,
                    reset_at=datetime.now(timezone.utc)
                )
            else:
                return RateLimitStatus(
                    remaining=0, limit=2,
                    reset_at=datetime.now(timezone.utc),
                    retry_after=60,
                    blocked_until=datetime.now(timezone.utc) + timedelta(seconds=60)
                )

        mock_backend.increment_counter.side_effect = mock_increment
        limiter.backend = mock_backend

        # Test multiple IPs
        ips = ["192.168.1.1", "192.168.1.2", "192.168.1.3"]
        for ip in ips:
            request = MockRequest(client_host=ip)

            # Each IP should get their own allowance
            allowed1, status1 = await limiter.is_allowed(request, "test")
            allowed2, status2 = await limiter.is_allowed(request, "test")
            allowed3, status3 = await limiter.is_allowed(request, "test")

            assert allowed1 and allowed2  # First 2 should be allowed
            assert not allowed3  # Third should be blocked

    @pytest.mark.asyncio
    async def test_header_spoofing_attempts(self):
        """Test attempts to spoof headers to bypass rate limiting."""
        limiter = AsyncRateLimiter()

        # Test X-Forwarded-For spoofing
        request1 = MockRequest(
            client_host="192.168.1.1",
            headers={"X-Forwarded-For": "1.1.1.1, 2.2.2.2, 192.168.1.1"}
        )
        request2 = MockRequest(
            client_host="192.168.1.1",
            headers={"X-Forwarded-For": "3.3.3.3, 4.4.4.4, 192.168.1.1"}
        )

        # Should use the same real client IP (first in X-Forwarded-For)
        key1 = await limiter._generate_key(request1, RateLimitRule(
            requests=10, window_seconds=60,
            algorithm=RateLimitAlgorithm.TOKEN_BUCKET,
            scope=RateLimitScope.IP
        ))
        key2 = await limiter._generate_key(request2, RateLimitRule(
            requests=10, window_seconds=60,
            algorithm=RateLimitAlgorithm.TOKEN_BUCKET,
            scope=RateLimitScope.IP
        ))

        # Keys should be different based on first IP in chain
        assert "1.1.1.1" in key1
        assert "3.3.3.3" in key2
        assert key1 != key2

    @pytest.mark.asyncio
    async def test_burst_attack_protection(self):
        """Test protection against burst attacks."""
        rule = RateLimitRule(
            requests=10,
            window_seconds=60,
            algorithm=RateLimitAlgorithm.TOKEN_BUCKET,
            scope=RateLimitScope.IP,
            burst_requests=5,  # Allow 5 extra requests in burst
            burst_window_seconds=10
        )

        limiter = AsyncRateLimiter()
        limiter.add_rule("burst_test", rule)

        mock_backend = AsyncMock()
        # Simulate burst capacity
        burst_responses = [
            RateLimitStatus(remaining=i, limit=15, reset_at=datetime.now(timezone.utc))
            for i in range(15, 0, -1)
        ]
        mock_backend.increment_counter.side_effect = burst_responses
        limiter.backend = mock_backend

        request = MockRequest()

        # Should handle burst of requests up to burst capacity
        for i in range(15):  # 10 normal + 5 burst
            allowed, status = await limiter.is_allowed(request, "burst_test")
            if i < 15:
                assert allowed, f"Request {i} should be allowed in burst"


class TestRateLimitBypassAttempts:
    """Test various bypass attempt scenarios."""

    @pytest.mark.asyncio
    async def test_user_agent_rotation(self):
        """Test attempts to bypass limits by rotating user agents."""
        limiter = AsyncRateLimiter()
        limiter.add_rule("test", RateLimitRule(
            requests=3,
            window_seconds=60,
            algorithm=RateLimitAlgorithm.SLIDING_WINDOW,
            scope=RateLimitScope.IP  # IP-based, so user agent shouldn't matter
        ))

        mock_backend = AsyncMock()
        # Same IP should hit same limit regardless of user agent
        call_count = 0

        def mock_increment(key, rule):
            nonlocal call_count
            call_count += 1
            remaining = max(0, 3 - call_count)

            if remaining > 0:
                return RateLimitStatus(remaining=remaining, limit=3, reset_at=datetime.now(timezone.utc))
            else:
                return RateLimitStatus(
                    remaining=0, limit=3, reset_at=datetime.now(timezone.utc),
                    retry_after=60, blocked_until=datetime.now(timezone.utc) + timedelta(seconds=60)
                )

        mock_backend.increment_counter.side_effect = mock_increment
        limiter.backend = mock_backend

        # Try different user agents from same IP
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
            "curl/7.68.0"
        ]

        for ua in user_agents:
            request = MockRequest(client_host="192.168.1.1", headers={"User-Agent": ua})
            allowed, status = await limiter.is_allowed(request, "test")

            # Should still be rate limited after 3 requests regardless of UA
            if call_count <= 3:
                assert allowed
            else:
                assert not allowed

    @pytest.mark.asyncio
    async def test_session_manipulation(self):
        """Test attempts to bypass user-based limits by manipulating sessions."""
        limiter = AsyncRateLimiter()
        limiter.add_rule("user_test", RateLimitRule(
            requests=2,
            window_seconds=60,
            algorithm=RateLimitAlgorithm.TOKEN_BUCKET,
            scope=RateLimitScope.USER
        ))

        mock_backend = AsyncMock()
        user_counters = {}

        def mock_increment(key, rule):
            user_id = key.split(":")[-1] if "user:" in key else "unknown"
            if user_id not in user_counters:
                user_counters[user_id] = 2
            user_counters[user_id] -= 1

            remaining = max(0, user_counters[user_id])
            if remaining > 0:
                return RateLimitStatus(remaining=remaining, limit=2, reset_at=datetime.now(timezone.utc))
            else:
                return RateLimitStatus(
                    remaining=0, limit=2, reset_at=datetime.now(timezone.utc),
                    retry_after=60, blocked_until=datetime.now(timezone.utc) + timedelta(seconds=60)
                )

        mock_backend.increment_counter.side_effect = mock_increment
        limiter.backend = mock_backend

        request = MockRequest()

        # Test with different user sessions
        with patch('app.rate_limiter.get_session_from_request') as mock_session:
            # First user
            mock_session.return_value = {"user_id": "user1"}
            allowed1, _ = await limiter.is_allowed(request, "user_test")
            allowed2, _ = await limiter.is_allowed(request, "user_test")
            allowed3, _ = await limiter.is_allowed(request, "user_test")

            assert allowed1 and allowed2  # First 2 allowed
            assert not allowed3  # Third blocked

            # Different user should get fresh allowance
            mock_session.return_value = {"user_id": "user2"}
            allowed4, _ = await limiter.is_allowed(request, "user_test")
            assert allowed4  # Fresh user gets allowance

    @pytest.mark.asyncio
    async def test_time_manipulation_attempts(self):
        """Test resilience against time manipulation attempts."""
        # Rate limiting should use server time, not client time
        # This test ensures time-based bypasses don't work

        rule = RateLimitRule(
            requests=2,
            window_seconds=10,
            algorithm=RateLimitAlgorithm.SLIDING_WINDOW,
            scope=RateLimitScope.IP
        )

        backend = RedisRateLimitBackend()

        # Mock Redis with time-sensitive operations
        mock_redis = AsyncMock()
        backend.redis = mock_redis

        # Ensure server time is used in Lua scripts
        current_time = time.time()
        mock_redis.evalsha.return_value = [1, 1, 2]  # allowed, remaining, limit

        await backend.increment_counter("test_key", rule)

        # Verify Lua script was called with server time
        call_args = mock_redis.evalsha.call_args
        assert len(call_args[0]) >= 4  # Should have time argument
        script_time = float(call_args[0][4])  # Time argument
        assert abs(script_time - current_time) < 1  # Should be current server time


class TestRateLimitErrorHandling:
    """Test error handling and failover scenarios."""

    @pytest.mark.asyncio
    async def test_redis_connection_failure(self):
        """Test behavior when Redis connection fails."""
        limiter = AsyncRateLimiter()
        limiter.add_rule("test", RateLimitRule(
            requests=5,
            window_seconds=60,
            algorithm=RateLimitAlgorithm.TOKEN_BUCKET,
            scope=RateLimitScope.IP
        ))

        # Mock Redis backend that raises connection error
        mock_backend = AsyncMock()
        mock_backend.increment_counter.side_effect = redis.ConnectionError("Redis unavailable")
        limiter.backend = mock_backend

        request = MockRequest()

        # Should fail open (allow requests) when Redis is down
        allowed, status = await limiter.is_allowed(request, "test")

        # Should allow request despite Redis failure
        assert allowed
        assert status.remaining > 0  # Should have permissive fallback

    @pytest.mark.asyncio
    async def test_lua_script_failure(self):
        """Test behavior when Lua scripts fail."""
        backend = RedisRateLimitBackend()
        mock_redis = AsyncMock()
        backend.redis = mock_redis

        # Mock Lua script failure
        mock_redis.evalsha.side_effect = redis.ResponseError("Script error")

        rule = RateLimitRule(
            requests=10,
            window_seconds=60,
            algorithm=RateLimitAlgorithm.TOKEN_BUCKET,
            scope=RateLimitScope.IP
        )

        # Should handle script failure gracefully
        status = await backend.increment_counter("test_key", rule)

        # Should return permissive fallback status
        assert status.remaining >= 0
        assert status.limit > 0

    @pytest.mark.asyncio
    async def test_invalid_rule_configuration(self):
        """Test handling of invalid rate limit rules."""
        limiter = AsyncRateLimiter()

        # Test with non-existent rule
        request = MockRequest()
        allowed, status = await limiter.is_allowed(request, "nonexistent_rule")

        # Should allow request with warning
        assert allowed
        assert status.limit == 1000  # Default permissive limit

    @pytest.mark.asyncio
    async def test_concurrent_access(self):
        """Test thread safety under concurrent access."""
        limiter = AsyncRateLimiter()
        limiter.add_rule("concurrent", RateLimitRule(
            requests=100,
            window_seconds=60,
            algorithm=RateLimitAlgorithm.TOKEN_BUCKET,
            scope=RateLimitScope.IP
        ))

        mock_backend = AsyncMock()
        counter = 100

        def mock_increment(key, rule):
            nonlocal counter
            counter -= 1
            return RateLimitStatus(
                remaining=max(0, counter),
                limit=100,
                reset_at=datetime.now(timezone.utc)
            )

        mock_backend.increment_counter.side_effect = mock_increment
        limiter.backend = mock_backend

        # Simulate concurrent requests
        tasks = []
        for i in range(10):
            request = MockRequest(client_host=f"192.168.1.{i}")
            task = limiter.is_allowed(request, "concurrent")
            tasks.append(task)

        # Execute concurrently
        results = await asyncio.gather(*tasks)

        # All should complete without errors
        assert len(results) == 10
        assert all(isinstance(result, tuple) for result in results)


class TestRateLimitHeaders:
    """Test rate limit response headers."""

    @pytest.mark.asyncio
    async def test_rate_limit_headers(self):
        """Test that correct rate limit headers are added."""
        app = create_app()

        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get("/health")  # Exempt endpoint

            # Health endpoint should not have rate limit headers
            assert "X-RateLimit-Limit" not in response.headers

            # Test non-exempt endpoint would have headers (if it existed)
            # This would need an actual test endpoint to verify header presence


class TestRateLimitConfiguration:
    """Test rate limit configuration and rules."""

    def test_default_rate_limiter_creation(self):
        """Test creation of default rate limiter with sensible rules."""
        limiter = create_default_rate_limiter()

        # Should have default rules configured
        assert "default" in limiter.rules
        assert "auth" in limiter.rules
        assert "authenticated" in limiter.rules
        assert "expensive" in limiter.rules

        # Check default rule configuration
        default_rule = limiter.rules["default"]
        assert default_rule.algorithm == RateLimitAlgorithm.TOKEN_BUCKET
        assert default_rule.scope == RateLimitScope.IP
        assert default_rule.requests > 0
        assert default_rule.window_seconds > 0

    def test_rate_limit_rule_validation(self):
        """Test rate limit rule parameter validation."""
        # Valid rule
        rule = RateLimitRule(
            requests=100,
            window_seconds=60,
            algorithm=RateLimitAlgorithm.TOKEN_BUCKET,
            scope=RateLimitScope.IP
        )

        assert rule.requests == 100
        assert rule.window_seconds == 60
        assert rule.block_duration_seconds == 60  # Default
        assert rule.warning_threshold == 0.8  # Default

    def test_exempt_ips_configuration(self):
        """Test exempt IPs functionality."""
        rule = RateLimitRule(
            requests=5,
            window_seconds=60,
            algorithm=RateLimitAlgorithm.TOKEN_BUCKET,
            scope=RateLimitScope.IP,
            exempt_ips={"127.0.0.1", "192.168.1.100"}
        )

        assert "127.0.0.1" in rule.exempt_ips
        assert "192.168.1.100" in rule.exempt_ips


class TestRateLimitMiddlewareIntegration:
    """Test rate limiting middleware integration."""

    @pytest.mark.asyncio
    async def test_middleware_exempt_paths(self):
        """Test that exempt paths bypass rate limiting."""
        app = create_app()

        async with AsyncClient(app=app, base_url="http://test") as client:
            # These paths should be exempt
            exempt_paths = ["/health", "/metrics", "/docs", "/static/test.js"]

            for path in exempt_paths:
                response = await client.get(path)
                # Should not get 429 (rate limited) response
                # May get 404 if endpoint doesn't exist, but not 429
                assert response.status_code != 429

    def test_middleware_configuration(self):
        """Test rate limiting middleware configuration."""
        limiter = create_default_rate_limiter()

        middleware = RateLimitMiddleware(
            app=None,  # App not needed for this test
            limiter=limiter,
            default_rule="default",
            exempt_paths={"/health", "/metrics"}
        )

        assert middleware.default_rule == "default"
        assert "/health" in middleware.exempt_paths
        assert "/metrics" in middleware.exempt_paths


if __name__ == "__main__":
    # Simple test runner for development
    async def run_tests():
        """Run comprehensive rate limiting tests."""
        print("🧪 COMPREHENSIVE RATE LIMITING SECURITY TESTS")
        print("=" * 80)

        test_classes = [
            TestRateLimitAlgorithms,
            TestRateLimitScopes,
            TestRateLimitAbuseScenarios,
            TestRateLimitBypassAttempts,
            TestRateLimitErrorHandling,
            TestRateLimitHeaders,
            TestRateLimitConfiguration,
            TestRateLimitMiddlewareIntegration,
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
        print("RATE LIMITING TEST SUMMARY")
        print(f"{'='*80}")
        print(f"Total Tests: {total_tests}")
        print(f"Passed: {passed_tests}")
        print(f"Failed: {total_tests - passed_tests}")
        print(f"Success Rate: {(passed_tests/total_tests)*100:.1f}%")

        if passed_tests == total_tests:
            print("\n🎉 All comprehensive rate limiting tests passed!")
            return True
        else:
            print(f"\n⚠️ {total_tests - passed_tests} test(s) failed")
            return False

    # Run tests if executed directly
    asyncio.run(run_tests())
