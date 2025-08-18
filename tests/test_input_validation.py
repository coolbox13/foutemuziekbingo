"""
Tests for comprehensive input validation models.
"""

import pytest
from pydantic import ValidationError
from app.validation_models import (
    GameIdParam, PlaylistIdParam, TrackIdParam,
    RoomCodeParam, FilenameParam, PaginationQuery, GameFilterQuery,
    DeviceSelectionRequest, GameActionRequest, MarkTrackRequest,
    CardGenerationRequest, validate_uuid, sanitize_string, validate_spotify_id
)


class TestPathParameterValidation:
    """Test path parameter validation models."""

    def test_valid_game_id_formats(self):
        """Test that valid game ID formats are accepted."""
        # UUID format
        valid_uuid = "123e4567-e89b-12d3-a456-426614174000"
        assert GameIdParam(game_id=valid_uuid).game_id == valid_uuid

        # Numeric ID
        assert GameIdParam(game_id="12345").game_id == "12345"

        # Alphanumeric
        assert GameIdParam(game_id="abc123-def").game_id == "abc123-def"

    def test_invalid_game_id_formats(self):
        """Test that invalid game ID formats are rejected."""
        with pytest.raises(ValidationError):
            GameIdParam(game_id="")  # Empty

        with pytest.raises(ValidationError):
            GameIdParam(game_id="ab")  # Too short

        with pytest.raises(ValidationError):
            GameIdParam(game_id="invalid/game/id")  # Contains slashes

        with pytest.raises(ValidationError):
            GameIdParam(game_id="<script>alert('xss')</script>")  # XSS attempt

    def test_valid_spotify_id_formats(self):
        """Test Spotify ID validation."""
        # Valid Spotify IDs are 22 character base62 strings
        valid_spotify_id = "4iV5W9uYEdYUVa79Axb7Rh"
        assert PlaylistIdParam(playlist_id=valid_spotify_id).playlist_id == valid_spotify_id
        assert TrackIdParam(track_id=valid_spotify_id).track_id == valid_spotify_id

    def test_invalid_spotify_id_formats(self):
        """Test invalid Spotify ID rejection."""
        with pytest.raises(ValidationError):
            PlaylistIdParam(playlist_id="invalid_spotify_id!")  # Invalid characters

        with pytest.raises(ValidationError):
            TrackIdParam(track_id="ab")  # Too short

        with pytest.raises(ValidationError):
            PlaylistIdParam(playlist_id="way_too_long_for_spotify_id_validation_this_is_definitely_too_long")  # Too long

    def test_room_code_validation(self):
        """Test room code validation and normalization."""
        # Valid room codes
        assert RoomCodeParam(room_code="abc123").room_code == "ABC123"  # Normalized to uppercase
        assert RoomCodeParam(room_code="GAME-1").room_code == "GAME-1"

        # Invalid room codes
        with pytest.raises(ValidationError):
            RoomCodeParam(room_code="ab")  # Too short

        with pytest.raises(ValidationError):
            RoomCodeParam(room_code="way_too_long_room_code")  # Too long

        with pytest.raises(ValidationError):
            RoomCodeParam(room_code="invalid!")  # Special characters

    def test_filename_validation(self):
        """Test filename validation and security."""
        # Valid filenames
        assert FilenameParam(filename="sound.mp3").filename == "sound.mp3"
        assert FilenameParam(filename="track_123.wav").filename == "track_123.wav"

        # Invalid filenames (security)
        with pytest.raises(ValidationError):
            FilenameParam(filename="../../../etc/passwd")  # Directory traversal

        with pytest.raises(ValidationError):
            FilenameParam(filename="file.exe")  # Disallowed extension

        with pytest.raises(ValidationError):
            FilenameParam(filename="file")  # No extension

        with pytest.raises(ValidationError):
            FilenameParam(filename="fi<le>.mp3")  # Invalid characters


class TestQueryParameterValidation:
    """Test query parameter validation models."""

    def test_pagination_validation(self):
        """Test pagination parameter validation."""
        # Valid pagination
        pagination = PaginationQuery(page=1, limit=20)
        assert pagination.page == 1
        assert pagination.limit == 20

        # Default values
        pagination_default = PaginationQuery()
        assert pagination_default.page == 1
        assert pagination_default.limit == 20

        # Invalid pagination
        with pytest.raises(ValidationError):
            PaginationQuery(page=0)  # Page must be >= 1

        with pytest.raises(ValidationError):
            PaginationQuery(limit=0)  # Limit must be >= 1

        with pytest.raises(ValidationError):
            PaginationQuery(limit=200)  # Limit must be <= 100

    def test_game_filter_validation(self):
        """Test game filter validation."""
        # Valid filters
        filters = GameFilterQuery(status="waiting", host_id="123")
        assert filters.status == "waiting"  # Normalized to lowercase
        assert filters.host_id == "123"

        # Invalid status
        with pytest.raises(ValidationError):
            GameFilterQuery(status="invalid_status")


class TestRequestBodyValidation:
    """Test request body validation models."""

    def test_device_selection_request(self):
        """Test device selection request validation."""
        # Valid request
        request = DeviceSelectionRequest(device_id="valid-device-123")
        assert request.device_id == "valid-device-123"

        # Invalid requests
        with pytest.raises(ValidationError):
            DeviceSelectionRequest(device_id="")  # Empty

        with pytest.raises(ValidationError):
            DeviceSelectionRequest(device_id="device<script>")  # XSS attempt

    def test_game_action_request(self):
        """Test game action request validation."""
        # Valid actions
        action = GameActionRequest(action="play", track_id="4iV5W9uYEdYUVa79Axb7Rh")
        assert action.action == "play"  # Normalized to lowercase
        assert action.track_id == "4iV5W9uYEdYUVa79Axb7Rh"

        # Valid action without track ID
        pause_action = GameActionRequest(action="PAUSE")
        assert pause_action.action == "pause"
        assert pause_action.track_id is None

        # Invalid action
        with pytest.raises(ValidationError):
            GameActionRequest(action="invalid_action")

    def test_mark_track_request(self):
        """Test mark track request validation."""
        # Valid request
        request = MarkTrackRequest(track_id="4iV5W9uYEdYUVa79Axb7Rh", marked=True)
        assert request.track_id == "4iV5W9uYEdYUVa79Axb7Rh"
        assert request.marked is True

        # Invalid track ID
        with pytest.raises(ValidationError):
            MarkTrackRequest(track_id="", marked=True)  # Empty track ID

    def test_card_generation_request(self):
        """Test card generation request validation."""
        # Valid request
        request = CardGenerationRequest(count=5, seed=12345)
        assert request.count == 5
        assert request.seed == 12345

        # Default values
        default_request = CardGenerationRequest()
        assert default_request.count == 1
        assert default_request.seed is None

        # Invalid count
        with pytest.raises(ValidationError):
            CardGenerationRequest(count=0)  # Must be >= 1

        with pytest.raises(ValidationError):
            CardGenerationRequest(count=100)  # Must be <= 50


class TestUtilityFunctions:
    """Test utility validation functions."""

    def test_validate_uuid(self):
        """Test UUID validation utility."""
        valid_uuid = "123e4567-e89b-12d3-a456-426614174000"
        assert validate_uuid(valid_uuid) == valid_uuid

        # Normalization
        uppercase_uuid = "123E4567-E89B-12D3-A456-426614174000"
        assert validate_uuid(uppercase_uuid) == valid_uuid.lower()

        # Invalid UUIDs
        with pytest.raises(ValueError):
            validate_uuid("")  # Empty

        with pytest.raises(ValueError):
            validate_uuid("not-a-uuid")  # Invalid format

    def test_sanitize_string(self):
        """Test string sanitization utility."""
        # Valid strings
        assert sanitize_string("  Hello World  ") == "Hello World"  # Trimmed
        assert sanitize_string("abc123-_") == "abc123-_"

        # Invalid strings
        with pytest.raises(ValueError):
            sanitize_string("a" * 300)  # Too long

        with pytest.raises(ValueError):
            sanitize_string("hello\0world")  # Null bytes

        with pytest.raises(ValueError):
            sanitize_string("hello<script>")  # Special characters (when not allowed)

    def test_validate_spotify_id_utility(self):
        """Test Spotify ID validation utility."""
        valid_id = "4iV5W9uYEdYUVa79Axb7Rh"
        assert validate_spotify_id(valid_id) == valid_id

        # Invalid IDs
        with pytest.raises(ValueError):
            validate_spotify_id("")  # Empty

        with pytest.raises(ValueError):
            validate_spotify_id("too_short")  # Wrong length

        with pytest.raises(ValueError):
            validate_spotify_id("invalid_chars!")  # Invalid characters


if __name__ == "__main__":
    # Simple test runner for development
    def run_tests():
        test_classes = [
            TestPathParameterValidation,
            TestQueryParameterValidation,
            TestRequestBodyValidation,
            TestUtilityFunctions
        ]

        total_tests = 0
        passed_tests = 0

        for test_class in test_classes:
            print(f"\nTesting {test_class.__name__}...")
            instance = test_class()

            # Get all test methods
            test_methods = [method for method in dir(instance) if method.startswith('test_')]

            for test_method in test_methods:
                total_tests += 1
                try:
                    getattr(instance, test_method)()
                    print(f"✓ {test_method}")
                    passed_tests += 1
                except Exception as e:
                    print(f"✗ {test_method}: {e}")

        print(f"\nTest Results: {passed_tests}/{total_tests} passed")
        if passed_tests == total_tests:
            print("All input validation tests passed!")
        else:
            print(f"{total_tests - passed_tests} tests failed.")

    run_tests()
