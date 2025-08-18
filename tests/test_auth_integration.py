#!/usr/bin/env python3
"""
Integration Tests for Session-Only Authentication System

This test suite validates the complete OAuth flow and session management
for the Musical Bingo application after the JWT removal refactoring.

Test Coverage:
- Complete Spotify OAuth flow
- Session creation and validation
- Session-based route protection
- Session expiration and cleanup
- Error scenarios and edge cases
"""


import pytest
from fastapi.testclient import TestClient
import os
import sys
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime, timezone, timedelta

# Add parent directory to path so we can import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import the main app
from app.fastapi_app import create_app
from app.auth_service import auth_service
from app.models import User, SpotifyUserProfile, SpotifyTokens
from app.config import get_config


class TestAuthIntegration:
    """Integration test suite for session-only authentication"""

    @pytest.fixture
    def app(self):
        """Create test FastAPI app"""
        return create_app()

    @pytest.fixture
    def client(self, app):
        """Create test client"""
        return TestClient(app)

    @pytest.fixture
    def mock_spotify_profile(self):
        """Mock Spotify user profile"""
        return SpotifyUserProfile(
            id="test_spotify_user",
            display_name="Test User",
            email="test@example.com",
            country="US",
            product="premium",
            followers={"total": 100},
            images=[{"url": "https://example.com/avatar.jpg"}],
            external_urls={"spotify": "https://spotify.com/user/test"},
            href="https://api.spotify.com/v1/users/test",
            uri="spotify:user:test",
            explicit_content={"filter_enabled": False, "filter_locked": False}
        )

    @pytest.fixture
    def mock_spotify_tokens(self):
        """Mock Spotify tokens"""
        return SpotifyTokens(
            access_token="spotify_access_token_123",
            refresh_token="spotify_refresh_token_456",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            scope="playlist-read-private user-read-playback-state"
        )

    @pytest.fixture
    def mock_user(self):
        """Mock authenticated user"""
        return User(
            id="user-uuid-123",
            spotify_id="test_spotify_user",
            display_name="Test User",
            email="test@example.com",
            subscription_type="free",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            last_login_at=datetime.now(timezone.utc),
            avatar_url="https://example.com/avatar.jpg"
        )

    def test_login_page_renders(self, client):
        """Test that login page renders correctly"""
        response = client.get("/auth/login/page")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_oauth_redirect(self, client):
        """Test OAuth login redirect"""
        response = client.get("/auth/login")
        assert response.status_code == 302
        location = response.headers["location"]
        assert "accounts.spotify.com" in location
        assert "client_id=" in location
        assert "response_type=code" in location
        assert "state=" in location

    @patch('app.auth_routes.SpotifyOAuth')
    @patch('app.auth_routes.Spotify')
    @patch('app.auth_service.auth_service.authenticate_spotify_user')
    def test_oauth_callback_success(self, mock_auth, mock_spotify, mock_oauth, client, mock_user):
        """Test successful OAuth callback flow"""
        # Mock Spotify OAuth exchange
        mock_oauth_instance = Mock()
        mock_oauth_instance.get_access_token.return_value = {
            "access_token": "spotify_token_123",
            "refresh_token": "spotify_refresh_123",
            "expires_in": 3600
        }
        mock_oauth.return_value = mock_oauth_instance

        # Mock Spotify API user profile
        mock_spotify_instance = Mock()
        mock_spotify_instance.current_user.return_value = {
            "id": "test_spotify_user",
            "display_name": "Test User",
            "email": "test@example.com",
            "country": "US",
            "product": "premium"
        }
        mock_spotify.return_value = mock_spotify_instance

        # Mock auth service
        mock_auth.return_value = mock_user

        # Test callback
        response = client.get("/auth/spotify/callback?code=test_code&state=test_state")
        assert response.status_code == 302
        assert response.headers["location"] == "/dashboard"

        # Verify session cookie is set
        cookies = response.cookies
        assert "music_bingo_session" in cookies

    def test_oauth_callback_error(self, client):
        """Test OAuth callback with error"""
        response = client.get("/auth/spotify/callback?error=access_denied&state=test_state")
        assert response.status_code == 302
        assert "error=access_denied" in response.headers["location"]

    def test_oauth_callback_no_code(self, client):
        """Test OAuth callback without authorization code"""
        response = client.get("/auth/spotify/callback?state=test_state")
        assert response.status_code == 302
        assert "error=no_code" in response.headers["location"]

    def test_oauth_callback_no_state(self, client):
        """Test OAuth callback without CSRF state"""
        response = client.get("/auth/spotify/callback?code=test_code")
        assert response.status_code == 302
        assert "error=csrf_error" in response.headers["location"]

    @patch('app.auth_service.get_session_from_request')
    @patch('app.auth_service.UserService.get_user_by_id')
    def test_protected_route_with_session(self, mock_get_user, mock_get_session, client, mock_user):
        """Test accessing protected route with valid session"""
        # Mock session data
        mock_get_session.return_value = {
            "user": {"id": "user-uuid-123"},
            "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        }
        mock_get_user.return_value = mock_user

        response = client.get("/auth/me")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "user-uuid-123"
        assert data["spotify_id"] == "test_spotify_user"

    @patch('app.auth_service.get_session_from_request')
    def test_protected_route_no_session(self, mock_get_session, client):
        """Test accessing protected route without session"""
        mock_get_session.return_value = None

        response = client.get("/auth/me")
        assert response.status_code == 401
        assert "Not authenticated" in response.json()["detail"]

    @patch('app.auth_service.get_session_from_request')
    def test_protected_route_invalid_session(self, mock_get_session, client):
        """Test accessing protected route with invalid session"""
        mock_get_session.return_value = {"user": {}}  # Invalid user data

        response = client.get("/auth/me")
        assert response.status_code == 401

    def test_auth_status_unauthenticated(self, client):
        """Test auth status for unauthenticated user"""
        response = client.get("/auth/status")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert data["message"] == "Not authenticated"

    @patch('app.auth_service.get_session_from_request')
    @patch('app.auth_service.UserService.get_user_by_id')
    def test_auth_status_authenticated(self, mock_get_user, mock_get_session, client, mock_user):
        """Test auth status for authenticated user"""
        # Mock session data
        mock_get_session.return_value = {
            "user": {"id": "user-uuid-123"},
        }
        mock_get_user.return_value = mock_user

        response = client.get("/auth/status")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["message"] == "Authenticated"
        assert "user" in data["data"]

    @patch('app.auth_routes.get_session_from_request')
    @patch('app.auth_routes.invalidate_session')
    def test_logout_with_session(self, mock_invalidate, mock_get_session, client):
        """Test logout with valid session"""
        mock_get_session.return_value = {"user": {"id": "user-uuid-123"}}

        response = client.post("/auth/logout")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["message"] == "Logged out successfully"
        mock_invalidate.assert_called_once()

    def test_logout_without_session(self, client):
        """Test logout without session"""
        response = client.post("/auth/logout")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["message"] == "Logged out successfully"


class TestSessionManagement:
    """Test session management functionality"""

    @pytest.fixture
    def config(self):
        """Get test config"""
        return get_config()

    @pytest.mark.asyncio
    async def test_session_creation(self, config, mock_user, mock_spotify_tokens):
        """Test session creation process"""
        from fastapi import Response

        response = Response()
        token_info = {
            "access_token": "spotify_token_123",
            "refresh_token": "spotify_refresh_123",
            "expires_in": 3600
        }

        with patch('app.secure_session.get_session_store') as mock_store:
            mock_store_instance = AsyncMock()
            mock_store_instance.set_session.return_value = True
            mock_store.return_value = mock_store_instance

            from app.secure_session import create_secure_session
            session_token = await create_secure_session(
                user_id=mock_user.id,
                spotify_token_info=token_info,
                user_data=mock_user.dict(),
                response=response,
                secret_key=config.secret_key
            )

            assert session_token is not None
            assert len(session_token) > 20  # Should be a proper token

    @pytest.mark.asyncio
    async def test_session_validation(self, config):
        """Test session validation"""
        from app.secure_session import get_session_from_request
        from fastapi import Request

        # Mock request with session cookie
        request = Mock(spec=Request)
        request.cookies = {"music_bingo_session": "valid_session_token.signature"}

        with patch('app.secure_session.get_session_store') as mock_store:
            mock_store_instance = AsyncMock()
            mock_store_instance.get_session.return_value = {
                "user_id": "user-123",
                "user": {"id": "user-123", "spotify_id": "spotify-123"},
                "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
            }
            mock_store.return_value = mock_store_instance

            session_data = await get_session_from_request(request, config.secret_key)
            assert session_data is not None
            assert session_data["user_id"] == "user-123"

    @pytest.mark.asyncio
    async def test_session_expiration(self, config):
        """Test expired session handling"""
        from app.secure_session import get_session_from_request
        from fastapi import Request

        request = Mock(spec=Request)
        request.cookies = {"music_bingo_session": "expired_session_token.signature"}

        with patch('app.secure_session.get_session_store') as mock_store:
            mock_store_instance = AsyncMock()
            # Return expired session
            mock_store_instance.get_session.return_value = {
                "user_id": "user-123",
                "expires_at": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
            }
            mock_store.return_value = mock_store_instance

            session_data = await get_session_from_request(request, config.secret_key)
            assert session_data is None  # Expired session should return None


class TestUserService:
    """Test user service functionality"""

    @pytest.mark.asyncio
    async def test_authenticate_spotify_user(self, mock_spotify_profile, mock_spotify_tokens):
        """Test Spotify user authentication"""
        with patch('app.auth_service.database') as mock_db:
            # Mock existing user
            mock_db.query_records.return_value = []
            mock_db.create_record.return_value = {
                "id": "user-uuid-123",
                "spotify_id": "test_spotify_user",
                "display_name": "Test User",
                "email": "test@example.com",
                "subscription_type": "free",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "last_login_at": datetime.now(timezone.utc).isoformat(),
            }

            user = await auth_service.authenticate_spotify_user(
                mock_spotify_profile, mock_spotify_tokens
            )

            assert user.spotify_id == "test_spotify_user"
            assert user.display_name == "Test User"
            assert user.email == "test@example.com"

    @pytest.mark.asyncio
    async def test_get_user_by_id(self):
        """Test getting user by ID"""
        from app.auth_service import UserService

        user_service = UserService()

        with patch('app.auth_service.database') as mock_db:
            mock_db.get_record.return_value = {
                "id": "user-uuid-123",
                "spotify_id": "test_spotify_user",
                "display_name": "Test User",
                "email": "test@example.com",
                "subscription_type": "free",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }

            user = await user_service.get_user_by_id("user-uuid-123")
            assert user is not None
            assert user.id == "user-uuid-123"

    @pytest.mark.asyncio
    async def test_get_user_by_id_not_found(self):
        """Test getting non-existent user"""
        from app.auth_service import UserService

        user_service = UserService()

        with patch('app.auth_service.database') as mock_db:
            mock_db.get_record.return_value = None

            user = await user_service.get_user_by_id("nonexistent")
            assert user is None


def run_integration_tests():
    """Run all integration tests"""
    print("🧪 Running Authentication Integration Tests...")

    # Set test environment
    os.environ["APP_ENV"] = "test"

    # Run pytest
    import subprocess
    result = subprocess.run([
        "python", "-m", "pytest",
        "tests/test_auth_integration.py",
        "-v", "--tb=short"
    ], capture_output=True, text=True)

    print(result.stdout)
    if result.stderr:
        print("STDERR:", result.stderr)

    return result.returncode == 0


if __name__ == "__main__":
    success = run_integration_tests()
    if success:
        print("✅ All authentication integration tests passed!")
    else:
        print("❌ Some authentication integration tests failed!")
        exit(1)
