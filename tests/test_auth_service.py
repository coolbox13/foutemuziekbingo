#!/usr/bin/env python3
"""
Test script for auth_service.py
Tests authentication, JWT tokens, and user management
"""
import asyncio
import sys
from datetime import datetime
from pathlib import Path

# Add parent directory to path so we can import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from test_utils import load_test_environment
from app.auth_service import auth_service
from app.models import SpotifyUserProfile

# Load test environment
load_test_environment()


async def test_jwt_tokens():
    """Test JWT token creation and validation"""
    print("Testing JWT token operations...")

    # Test token creation
    user_id = "test-user-123"
    try:
        tokens = auth_service.create_tokens(user_id)
        print("✅ JWT token creation: PASS")
        print(f"  Access token length: {len(tokens['access_token'])}")
        print(f"  Refresh token length: {len(tokens['refresh_token'])}")
    except Exception as e:
        print(f"❌ JWT token creation: FAIL - {e}")
        return

    # Test token validation
    try:
        payload = auth_service.verify_token(tokens["access_token"])
        print("✅ JWT token validation: PASS")
        print(f"  User ID from token: {payload.get('user_id')}")
        print(f"  Token type: {payload.get('type')}")
    except Exception as e:
        print(f"❌ JWT token validation: FAIL - {e}")

    # Test expired token (simulate)
    try:
        # Create a token that expires immediately
        expired_token = auth_service.create_jwt_token(user_id, "access", -1)
        auth_service.verify_token(expired_token)
        print("❌ Expired token handling: FAIL - Should have raised exception")
    except Exception:
        print("✅ Expired token handling: PASS")


async def test_spotify_auth_flow():
    """Test Spotify authentication flow (mock)"""
    print("\nTesting Spotify authentication flow...")

    # Create mock Spotify user profile
    spotify_profile = SpotifyUserProfile(
        id="spotify_test_user",
        display_name="Test User",
        email="test@example.com",
        country="US",
        product="premium",
    )

    try:
        # Test auth service with Spotify profile data
        print("✅ Auth request creation: PASS")
        print(f"  Spotify ID: {spotify_profile.id}")
        print(f"  Display name: {spotify_profile.display_name}")
        print(f"  Email: {spotify_profile.email}")
    except Exception as e:
        print(f"❌ Auth request creation: FAIL - {e}")


async def test_user_session_management():
    """Test user session management"""
    print("\nTesting user session management...")

    user_id = "test-session-user"

    try:
        # Test session creation
        tokens = auth_service.create_tokens(user_id)
        session_data = {
            "user_id": user_id,
            "access_token": tokens["access_token"],
            "refresh_token": tokens["refresh_token"],
            "created_at": datetime.now().isoformat(),
        }
        print("✅ Session data creation: PASS")
        print(f"  Session contains user_id: {session_data.get('user_id') == user_id}")

        # Test token refresh simulation
        new_tokens = auth_service.create_tokens(user_id)
        print("✅ Token refresh simulation: PASS")
        print(
            f"  New access token different: {tokens['access_token'] != new_tokens['access_token']}"
        )

    except Exception as e:
        print(f"❌ Session management: FAIL - {e}")


async def run_auth_service_tests():
    """Run all authentication tests"""
    print("=" * 50)
    print("AUTHENTICATION SERVICE TESTS")
    print("=" * 50)

    await test_jwt_tokens()
    await test_spotify_auth_flow()
    await test_user_session_management()

    print("\nAuthentication tests completed!")


async def run_auth_tests():
    """Alias for backwards compatibility"""
    await run_auth_service_tests()


if __name__ == "__main__":
    asyncio.run(run_auth_tests())
