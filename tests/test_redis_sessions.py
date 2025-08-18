"""
Tests for Redis/Dragonfly session storage integration.
"""

import pytest
import asyncio

# Load test environment first
from test_utils import load_test_environment
from app.redis_session_store import get_redis_session_store
from app.secure_session import get_session_store

load_test_environment()


class TestRedisSessionStore:
    """Test Redis session store functionality."""

    @pytest.mark.asyncio
    async def test_redis_health_check(self):
        """Test Redis connection health check."""
        store = get_redis_session_store()
        health = await store.health_check()

        # Should connect to Dragonfly if running
        assert "healthy" in health
        await store.close()

    @pytest.mark.asyncio
    async def test_session_lifecycle(self):
        """Test complete session lifecycle."""
        store = get_redis_session_store()

        try:
            # Create session
            session_token = await store.create_session(
                user_id="test_user_123",
                spotify_token_info={"access_token": "test_token", "refresh_token": "refresh"},
                user_data={"id": "test_user_123", "name": "Test User"},
                csrf_token="csrf_123"
            )

            assert session_token
            assert len(session_token) > 20  # Should be secure token

            # Retrieve session
            session_data = await store.get_session(session_token)
            assert session_data is not None
            assert session_data["user_id"] == "test_user_123"
            assert session_data["csrf_token"] == "csrf_123"
            assert "created_at" in session_data
            assert "expires_at" in session_data

            # Update token info
            new_token_info = {"access_token": "new_token", "refresh_token": "new_refresh"}
            success = await store.update_session_token_info(session_token, new_token_info)
            assert success

            # Verify update
            updated_session = await store.get_session(session_token)
            assert updated_session["token_info"]["access_token"] == "new_token"

            # Invalidate session
            invalidated = await store.invalidate_session(session_token)
            assert invalidated

            # Verify session is gone
            invalid_session = await store.get_session(session_token)
            assert invalid_session is None

        finally:
            await store.close()

    @pytest.mark.asyncio
    async def test_session_stats(self):
        """Test session statistics."""
        store = get_redis_session_store()

        try:
            # Create multiple sessions
            tokens = []
            for i in range(3):
                token = await store.create_session(
                    user_id=f"user_{i}",
                    spotify_token_info={"access_token": f"token_{i}"},
                    user_data={"id": f"user_{i}", "name": f"User {i}"},
                    csrf_token=f"csrf_{i}"
                )
                tokens.append(token)

            # Get stats
            stats = await store.get_session_stats()
            assert stats["storage_type"] == "Redis/Dragonfly"
            assert stats["active_sessions"] >= 3
            assert stats["unique_users"] >= 3

            # Clean up
            for token in tokens:
                await store.invalidate_session(token)

        finally:
            await store.close()

    @pytest.mark.asyncio
    async def test_hybrid_session_selection(self):
        """Test that session store selection works correctly."""
        store = await get_session_store()

        # Should select Redis if available, Memory if not
        store_type = type(store).__name__
        assert store_type in ["RedisSessionStore", "MemorySessionStore"]

        if hasattr(store, 'close'):
            await store.close()


if __name__ == "__main__":
    # Simple test runner for development
    async def run_tests():
        test_instance = TestRedisSessionStore()

        print("Testing Redis health check...")
        await test_instance.test_redis_health_check()
        print("✓ Redis health check passed")

        print("Testing session lifecycle...")
        await test_instance.test_session_lifecycle()
        print("✓ Session lifecycle test passed")

        print("Testing session stats...")
        await test_instance.test_session_stats()
        print("✓ Session stats test passed")

        print("Testing hybrid session selection...")
        await test_instance.test_hybrid_session_selection()
        print("✓ Hybrid session selection test passed")

        print("\nAll Redis session tests passed!")

    asyncio.run(run_tests())
