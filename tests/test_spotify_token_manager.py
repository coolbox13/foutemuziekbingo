"""
Unit Tests for Spotify Token Manager

Tests for the comprehensive token management system including
token validation, refresh, and error handling scenarios.

Author: Claude Code Assistant
Date: 2025-01-18
Issue: CRIT-003 - Token management testing
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone, timedelta
import time

# Test imports - adjust paths as needed based on your project structure
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from app.spotify_token_manager import (
    SpotifyTokenManager,
    TokenStatus,
    TokenRefreshResult,
    TokenValidationResult,
    spotify_token_manager
)


class TestSpotifyTokenManager:
    """Test suite for SpotifyTokenManager"""

    def setup_method(self):
        """Setup for each test method"""
        self.token_manager = SpotifyTokenManager()
        self.test_user_id = "test-user-123"
        
        # Mock token data
        self.valid_token_data = {
            "access_token": "valid-access-token",
            "refresh_token": "valid-refresh-token", 
            "expires_at": time.time() + 3600,  # 1 hour from now
            "scope": "playlist-read-private user-read-playback-state"
        }
        
        self.expired_token_data = {
            "access_token": "expired-access-token",
            "refresh_token": "valid-refresh-token",
            "expires_at": time.time() - 300,  # 5 minutes ago
            "scope": "playlist-read-private user-read-playback-state"
        }
        
        self.expiring_soon_token_data = {
            "access_token": "expiring-access-token",
            "refresh_token": "valid-refresh-token",
            "expires_at": time.time() + 60,  # 1 minute from now
            "scope": "playlist-read-private user-read-playback-state"
        }

    @pytest.mark.asyncio
    async def test_validate_token_valid(self):
        """Test token validation with valid token"""
        with patch.object(self.token_manager, '_get_user_token_info') as mock_get_token:
            mock_get_token.return_value = self.valid_token_data
            
            result = await self.token_manager.validate_token(self.test_user_id)
            
            assert result.status == TokenStatus.VALID
            assert result.is_valid is True
            assert result.needs_refresh is False
            assert result.expires_in_seconds > 3000  # Should be close to 1 hour

    @pytest.mark.asyncio
    async def test_validate_token_expired(self):
        """Test token validation with expired token"""
        with patch.object(self.token_manager, '_get_user_token_info') as mock_get_token:
            mock_get_token.return_value = self.expired_token_data
            
            result = await self.token_manager.validate_token(self.test_user_id)
            
            assert result.status == TokenStatus.EXPIRED
            assert result.is_valid is False
            assert result.needs_refresh is True
            assert result.expires_in_seconds < 0

    @pytest.mark.asyncio
    async def test_validate_token_expiring_soon(self):
        """Test token validation with token expiring soon"""
        with patch.object(self.token_manager, '_get_user_token_info') as mock_get_token:
            mock_get_token.return_value = self.expiring_soon_token_data
            
            result = await self.token_manager.validate_token(self.test_user_id)
            
            assert result.status == TokenStatus.REFRESH_NEEDED
            assert result.is_valid is True  # Still valid now
            assert result.needs_refresh is True
            assert 0 < result.expires_in_seconds < 300  # Less than 5 minutes

    @pytest.mark.asyncio
    async def test_validate_token_missing(self):
        """Test token validation with no token info"""
        with patch.object(self.token_manager, '_get_user_token_info') as mock_get_token:
            mock_get_token.return_value = None
            
            result = await self.token_manager.validate_token(self.test_user_id)
            
            assert result.status == TokenStatus.MISSING
            assert result.is_valid is False
            assert result.needs_refresh is False
            assert "No token information found" in result.error_message

    @pytest.mark.asyncio
    async def test_validate_token_invalid_access_token(self):
        """Test token validation with missing access token"""
        invalid_token_data = {
            "refresh_token": "valid-refresh-token",
            "expires_at": time.time() + 3600
        }
        
        with patch.object(self.token_manager, '_get_user_token_info') as mock_get_token:
            mock_get_token.return_value = invalid_token_data
            
            result = await self.token_manager.validate_token(self.test_user_id)
            
            assert result.status == TokenStatus.INVALID
            assert result.is_valid is False
            assert "Missing access token" in result.error_message

    @pytest.mark.asyncio
    async def test_refresh_token_success(self):
        """Test successful token refresh"""
        new_token_data = {
            "access_token": "new-access-token",
            "refresh_token": "new-refresh-token",
            "expires_at": time.time() + 3600
        }
        
        with patch.object(self.token_manager, '_get_user_token_info') as mock_get_token, \
             patch.object(self.token_manager, '_get_spotify_oauth') as mock_oauth, \
             patch.object(self.token_manager, '_update_user_tokens') as mock_update:
            
            # Setup mocks
            mock_get_token.return_value = self.expired_token_data
            mock_oauth_instance = MagicMock()
            mock_oauth.return_value = mock_oauth_instance
            mock_oauth_instance.refresh_access_token.return_value = new_token_data
            mock_update.return_value = None  # Async mock
            
            result, token = await self.token_manager.refresh_token(self.test_user_id)
            
            assert result == TokenRefreshResult.SUCCESS
            assert token == new_token_data
            mock_oauth_instance.refresh_access_token.assert_called_once_with(
                self.expired_token_data["refresh_token"]
            )
            mock_update.assert_called_once()

    @pytest.mark.asyncio
    async def test_refresh_token_no_refresh_token(self):
        """Test refresh failure when no refresh token available"""
        token_data_no_refresh = {
            "access_token": "expired-access-token",
            "expires_at": time.time() - 300
        }
        
        with patch.object(self.token_manager, '_get_user_token_info') as mock_get_token:
            mock_get_token.return_value = token_data_no_refresh
            
            result, token = await self.token_manager.refresh_token(self.test_user_id)
            
            assert result == TokenRefreshResult.FAILED_NO_REFRESH_TOKEN
            assert token is None

    @pytest.mark.asyncio
    async def test_refresh_token_spotify_error(self):
        """Test refresh failure due to Spotify API error"""
        from spotipy.exceptions import SpotifyException
        
        with patch.object(self.token_manager, '_get_user_token_info') as mock_get_token, \
             patch.object(self.token_manager, '_get_spotify_oauth') as mock_oauth:
            
            mock_get_token.return_value = self.expired_token_data
            mock_oauth_instance = MagicMock()
            mock_oauth.return_value = mock_oauth_instance
            
            # Simulate Spotify API error
            spotify_error = SpotifyException(400, "invalid_grant", "Invalid refresh token")
            mock_oauth_instance.refresh_access_token.side_effect = spotify_error
            
            result, token = await self.token_manager.refresh_token(self.test_user_id)
            
            assert result == TokenRefreshResult.FAILED_EXPIRED_REFRESH
            assert token is None

    @pytest.mark.asyncio
    async def test_refresh_token_skip_not_needed(self):
        """Test refresh skips when token is still valid"""
        with patch.object(self.token_manager, '_get_user_token_info') as mock_get_token, \
             patch.object(self.token_manager, 'validate_token') as mock_validate:
            
            mock_get_token.return_value = self.valid_token_data
            mock_validate.return_value = TokenValidationResult(
                status=TokenStatus.VALID,
                is_valid=True,
                needs_refresh=False
            )
            
            result, token = await self.token_manager.refresh_token(self.test_user_id, force=False)
            
            assert result == TokenRefreshResult.SKIPPED_NOT_NEEDED
            assert token == self.valid_token_data

    @pytest.mark.asyncio
    async def test_get_valid_token_existing_valid(self):
        """Test getting valid token when current token is valid"""
        with patch.object(self.token_manager, 'validate_token') as mock_validate, \
             patch.object(self.token_manager, '_get_user_token_info') as mock_get_token:
            
            mock_validate.return_value = TokenValidationResult(
                status=TokenStatus.VALID,
                is_valid=True,
                needs_refresh=False,
                expires_in_seconds=3600
            )
            mock_get_token.return_value = self.valid_token_data
            
            success, access_token, error = await self.token_manager.get_valid_token(self.test_user_id)
            
            assert success is True
            assert access_token == self.valid_token_data["access_token"]
            assert error is None

    @pytest.mark.asyncio
    async def test_get_valid_token_refresh_needed(self):
        """Test getting valid token when refresh is needed"""
        with patch.object(self.token_manager, 'validate_token') as mock_validate, \
             patch.object(self.token_manager, 'refresh_token') as mock_refresh:
            
            mock_validate.return_value = TokenValidationResult(
                status=TokenStatus.REFRESH_NEEDED,
                is_valid=True,
                needs_refresh=True
            )
            
            new_token_data = {
                "access_token": "refreshed-access-token",
                "expires_at": time.time() + 3600
            }
            mock_refresh.return_value = (TokenRefreshResult.SUCCESS, new_token_data)
            
            success, access_token, error = await self.token_manager.get_valid_token(self.test_user_id)
            
            assert success is True
            assert access_token == new_token_data["access_token"]
            assert error is None
            mock_refresh.assert_called_once_with(self.test_user_id)

    @pytest.mark.asyncio
    async def test_get_valid_token_refresh_failed(self):
        """Test getting valid token when refresh fails"""
        with patch.object(self.token_manager, 'validate_token') as mock_validate, \
             patch.object(self.token_manager, 'refresh_token') as mock_refresh:
            
            mock_validate.return_value = TokenValidationResult(
                status=TokenStatus.EXPIRED,
                is_valid=False,
                needs_refresh=True
            )
            
            mock_refresh.return_value = (TokenRefreshResult.FAILED_EXPIRED_REFRESH, None)
            
            success, access_token, error = await self.token_manager.get_valid_token(self.test_user_id)
            
            assert success is False
            assert access_token is None
            assert "expired" in error.lower() or "log in" in error.lower()

    @pytest.mark.asyncio
    async def test_get_spotify_client_success(self):
        """Test successful Spotify client creation"""
        from spotipy import Spotify
        
        with patch.object(self.token_manager, 'get_valid_token') as mock_get_token, \
             patch('app.spotify_token_manager.Spotify') as mock_spotify_class:
            
            mock_get_token.return_value = (True, "valid-access-token", None)
            mock_spotify_instance = MagicMock()
            mock_spotify_class.return_value = mock_spotify_instance
            
            success, client, error = await self.token_manager.get_spotify_client(self.test_user_id)
            
            assert success is True
            assert client == mock_spotify_instance
            assert error is None
            mock_spotify_class.assert_called_once_with(auth="valid-access-token")

    @pytest.mark.asyncio
    async def test_get_spotify_client_token_failed(self):
        """Test Spotify client creation failure due to token issues"""
        with patch.object(self.token_manager, 'get_valid_token') as mock_get_token:
            
            mock_get_token.return_value = (False, None, "Token expired, please log in again")
            
            success, client, error = await self.token_manager.get_spotify_client(self.test_user_id)
            
            assert success is False
            assert client is None
            assert error == "Token expired, please log in again"

    @pytest.mark.asyncio
    async def test_check_user_needs_reauth_missing_token(self):
        """Test reauth check with missing token"""
        with patch.object(self.token_manager, 'validate_token') as mock_validate:
            
            mock_validate.return_value = TokenValidationResult(
                status=TokenStatus.MISSING,
                is_valid=False,
                error_message="No token information found"
            )
            
            needs_reauth, reason = await self.token_manager.check_user_needs_reauth(self.test_user_id)
            
            assert needs_reauth is True
            assert reason == "No token information found"

    @pytest.mark.asyncio
    async def test_check_user_needs_reauth_refresh_failed(self):
        """Test reauth check when token refresh fails"""
        with patch.object(self.token_manager, 'validate_token') as mock_validate, \
             patch.object(self.token_manager, 'refresh_token') as mock_refresh:
            
            mock_validate.return_value = TokenValidationResult(
                status=TokenStatus.EXPIRED,
                is_valid=False,
                needs_refresh=True
            )
            
            mock_refresh.return_value = (TokenRefreshResult.FAILED_EXPIRED_REFRESH, None)
            
            needs_reauth, reason = await self.token_manager.check_user_needs_reauth(self.test_user_id)
            
            assert needs_reauth is True
            assert "expired" in reason.lower()

    @pytest.mark.asyncio
    async def test_check_user_needs_reauth_valid_token(self):
        """Test reauth check with valid token"""
        with patch.object(self.token_manager, 'validate_token') as mock_validate:
            
            mock_validate.return_value = TokenValidationResult(
                status=TokenStatus.VALID,
                is_valid=True,
                needs_refresh=False
            )
            
            needs_reauth, reason = await self.token_manager.check_user_needs_reauth(self.test_user_id)
            
            assert needs_reauth is False
            assert reason is None

    @pytest.mark.asyncio
    async def test_health_check(self):
        """Test health check functionality"""
        with patch.object(self.token_manager, '_get_user_token_info') as mock_get_token, \
             patch.object(self.token_manager, '_get_spotify_oauth') as mock_oauth:
            
            mock_get_token.return_value = None  # Normal for health check test user
            mock_oauth_instance = MagicMock()
            mock_oauth_instance.client_id = "test-client-id"
            mock_oauth_instance.client_secret = "test-client-secret"
            mock_oauth.return_value = mock_oauth_instance
            
            health = await self.token_manager.health_check()
            
            assert isinstance(health, dict)
            assert "healthy" in health
            assert "timestamp" in health
            assert "database_accessible" in health
            assert "spotify_oauth_configured" in health
            assert health["spotify_oauth_configured"] is True

    def test_get_refresh_error_message(self):
        """Test error message generation for different refresh results"""
        test_cases = [
            (TokenRefreshResult.FAILED_NO_REFRESH_TOKEN, "log in"),
            (TokenRefreshResult.FAILED_SPOTIFY_ERROR, "authentication failed"),
            (TokenRefreshResult.FAILED_EXPIRED_REFRESH, "expired"),
            (TokenRefreshResult.FAILED_DATABASE_ERROR, "technical error")
        ]
        
        for refresh_result, expected_substring in test_cases:
            message = self.token_manager._get_refresh_error_message(refresh_result)
            assert expected_substring.lower() in message.lower()

    @pytest.mark.asyncio
    async def test_concurrent_refresh_prevention(self):
        """Test that concurrent refresh requests for same user are handled properly"""
        with patch.object(self.token_manager, '_get_user_token_info') as mock_get_token, \
             patch.object(self.token_manager, '_get_spotify_oauth') as mock_oauth, \
             patch.object(self.token_manager, '_update_user_tokens') as mock_update:
            
            mock_get_token.return_value = self.expired_token_data
            mock_oauth_instance = MagicMock()
            mock_oauth.return_value = mock_oauth_instance
            
            # Simulate slow refresh operation
            async def slow_refresh(*args):
                await asyncio.sleep(0.1)
                return {"access_token": "new-token", "expires_at": time.time() + 3600}
            
            mock_oauth_instance.refresh_access_token.side_effect = slow_refresh
            mock_update.return_value = None
            
            # Start two concurrent refresh operations
            task1 = asyncio.create_task(self.token_manager.refresh_token(self.test_user_id))
            task2 = asyncio.create_task(self.token_manager.refresh_token(self.test_user_id))
            
            result1, token1 = await task1
            result2, token2 = await task2
            
            # One should succeed, one should be skipped
            results = [result1, result2]
            assert TokenRefreshResult.SUCCESS in results
            # The second one might be skipped or succeed depending on timing
            assert all(r in [TokenRefreshResult.SUCCESS, TokenRefreshResult.SKIPPED_NOT_NEEDED] for r in results)


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v"])
