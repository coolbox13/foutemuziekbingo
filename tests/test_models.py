#!/usr/bin/env python3
"""
Test script for models.py
Tests Pydantic models, validation, and data structures
"""
import sys
from pathlib import Path

# Add parent directory to path so we can import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from datetime import datetime
from app.models import (
    UserBase,
    Game,
    GameCreate,
    SpotifyUserProfile,
    SpotifyTokens,
    Playlist,
    Track,
    BingoCard,
    SubscriptionType,
)


class TestUserModels:
    """Test user-related models"""

    def test_user_base_valid(self):
        """Test valid UserBase creation"""
        user = UserBase(
            spotify_id="testuser123",
            display_name="Test User",
            email="test@example.com",
            country="US",
        )
        assert user.spotify_id == "testuser123"
        assert user.display_name == "Test User"
        assert user.email == "test@example.com"
        assert user.country == "US"
        assert user.subscription_type == SubscriptionType.FREE

    def test_user_base_minimal(self):
        """Test UserBase with minimal required fields"""
        user = UserBase(spotify_id="abc123")
        assert user.spotify_id == "abc123"
        assert user.display_name is None
        assert user.email is None
        assert user.country is None
        assert user.subscription_type == SubscriptionType.FREE

    def test_spotify_id_validation_too_short(self):
        """Test Spotify ID validation fails for short IDs"""
        with pytest.raises(
            ValueError, match="Spotify ID must be at least 3 characters"
        ):
            UserBase(spotify_id="ab")

    def test_spotify_id_validation_empty(self):
        """Test Spotify ID validation fails for empty string"""
        with pytest.raises(
            ValueError, match="Spotify ID must be at least 3 characters"
        ):
            UserBase(spotify_id="")


class TestGameModels:
    """Test game-related models"""

    def test_game_base_valid(self):
        """Test valid GameBase creation"""
        game = GameCreate(
            name="Test Game",
            description="A test game",
            max_players=10,
            is_private=False,
        )
        assert game.name == "Test Game"
        assert game.description == "A test game"
        assert game.max_players == 10
        assert game.is_private is False

    def test_room_code_validation_valid(self):
        """Test room code validation with valid 6-digit code"""
        game = Game(
            id="test-id",
            host_id="user-123",
            name="Test Game",
            room_code="123456",
            playlist_id="test-playlist-123",
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        assert game.room_code == "123456"

    def test_room_code_validation_invalid_length(self):
        """Test room code validation fails for wrong length"""
        with pytest.raises(ValueError, match="Room code must be exactly 6 digits"):
            Game(
                id="test-id",
                host_id="user-123",
                name="Test Game",
                room_code="12345",  # Too short
                playlist_id="test-playlist-123",
                created_at=datetime.now(),
                updated_at=datetime.now(),
            )

    def test_room_code_validation_non_digits(self):
        """Test room code validation fails for non-digits"""
        with pytest.raises(ValueError, match="Room code must be exactly 6 digits"):
            Game(
                id="test-id",
                host_id="user-123",
                name="Test Game",
                room_code="abc123",  # Contains letters
                playlist_id="test-playlist-123",
                created_at=datetime.now(),
                updated_at=datetime.now(),
            )

    def test_room_code_none_allowed(self):
        """Test room code can be None"""
        game = Game(
            id="test-id",
            host_id="user-123",
            name="Test Game",
            room_code=None,
            playlist_id="test-playlist-123",
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        assert game.room_code is None


class TestSpotifyModels:
    """Test Spotify-related models"""

    def test_spotify_user_profile_valid(self):
        """Test valid SpotifyUserProfile creation"""
        profile = SpotifyUserProfile(
            id="spotify123",
            display_name="Spotify User",
            email="spotify@example.com",
            country="US",
            product="premium",
        )
        assert profile.id == "spotify123"
        assert profile.display_name == "Spotify User"
        assert profile.email == "spotify@example.com"
        assert profile.country == "US"
        assert profile.product == "premium"

    def test_spotify_tokens_valid(self):
        """Test valid SpotifyTokens creation"""
        tokens = SpotifyTokens(
            access_token="access123",
            refresh_token="refresh123",
            expires_in=3600,
            scope="playlist-read",
        )
        assert tokens.access_token == "access123"
        assert tokens.refresh_token == "refresh123"
        assert tokens.expires_in == 3600
        assert tokens.scope == "playlist-read"
        assert tokens.token_type == "Bearer"  # Default value


class TestPlaylistModels:
    """Test playlist-related models"""

    def test_track_valid(self):
        """Test valid Track creation"""
        track = Track(
            id="track123",
            name="Test Song",
            artist="Test Artist",
            album="Test Album",
            duration_ms=180000,
            preview_url="https://example.com/preview.mp3",
        )
        assert track.id == "track123"
        assert track.name == "Test Song"
        assert track.artist == "Test Artist"
        assert track.album == "Test Album"
        assert track.duration_ms == 180000
        assert track.preview_url == "https://example.com/preview.mp3"
        assert track.played is False  # Default value

    def test_playlist_valid(self):
        """Test valid Playlist creation"""
        playlist = Playlist(
            id="playlist123",
            spotify_id="spotify_playlist_123",
            name="Test Playlist",
            description="A test playlist",
            owner_id="user123",
            is_public=True,
            track_count=10,
        )
        assert playlist.id == "playlist123"
        assert playlist.spotify_id == "spotify_playlist_123"
        assert playlist.name == "Test Playlist"
        assert playlist.description == "A test playlist"
        assert playlist.owner_id == "user123"
        assert playlist.is_public is True
        assert playlist.track_count == 10


class TestBingoModels:
    """Test bingo-related models"""

    def test_bingo_card_valid(self):
        """Test valid BingoCard creation"""
        tracks = [
            Track(
                id=f"track{i}",
                name=f"Song {i}",
                artist=f"Artist {i}",
                album=f"Album {i}",
            )
            for i in range(25)
        ]

        card = BingoCard(
            id="card123", user_id="user123", game_id="game123", tracks=tracks
        )
        assert card.id == "card123"
        assert card.user_id == "user123"
        assert card.game_id == "game123"
        assert len(card.tracks) == 25
        assert len(card.matched_positions) == 0  # Default empty list
        assert card.is_winner is False  # Default value


def run_tests():
    """Run all model tests"""
    print("Testing Pydantic models...")

    # Test UserBase
    try:
        user = UserBase(spotify_id="testuser123", display_name="Test User")
        assert user.spotify_id == "testuser123"
        print("✅ UserBase creation: PASS")
    except Exception as e:
        print(f"❌ UserBase creation: FAIL - {e}")

    # Test validation
    try:
        UserBase(spotify_id="ab")  # Should fail
        print("❌ Spotify ID validation: FAIL - Should have raised ValueError")
    except ValueError:
        print("✅ Spotify ID validation: PASS")
    except Exception as e:
        print(f"❌ Spotify ID validation: FAIL - {e}")

    # Test Game model
    try:
        game = Game(
            id="test-id",
            host_id="user-123",
            name="Test Game",
            room_code="123456",
            playlist_id="test-playlist-123",
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        assert game.name == "Test Game"
        print("✅ Game creation: PASS")
    except Exception as e:
        print(f"❌ Game creation: FAIL - {e}")

    # Test room code validation
    try:
        Game(
            id="test-id",
            host_id="user-123",
            name="Test Game",
            room_code="12345",  # Should fail
            playlist_id="test-playlist-123",
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        print("❌ Room code validation: FAIL - Should have raised ValueError")
    except ValueError:
        print("✅ Room code validation: PASS")
    except Exception as e:
        print(f"❌ Room code validation: FAIL - {e}")

    print("Model tests completed!")


async def run_model_tests():
    """Async wrapper for model tests"""
    run_tests()


if __name__ == "__main__":
    run_tests()
