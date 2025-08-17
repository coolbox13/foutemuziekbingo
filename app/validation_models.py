"""
Comprehensive input validation models for FastAPI route parameters.
Provides UUID validation, input sanitization, and type safety for all endpoints.
"""

import re
import uuid
from typing import Optional, List, Dict, Any, Union
from datetime import datetime
from pydantic import BaseModel, Field, field_validator, ConfigDict
from fastapi import Path
from enum import Enum

# Valid patterns for various identifiers
SPOTIFY_ID_PATTERN = re.compile(r'^[a-zA-Z0-9]{22}$')  # Spotify Track/Playlist ID
UUID_PATTERN = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$', re.IGNORECASE)
ALPHANUMERIC_PATTERN = re.compile(r'^[a-zA-Z0-9_-]+$')
SAFE_STRING_PATTERN = re.compile(r'^[a-zA-Z0-9\s._-]+$')


class ValidationError(Exception):
    """Custom validation error for detailed error messages."""
    pass


# =============================================
# PATH PARAMETER VALIDATION MODELS
# =============================================

class GameIdParam(BaseModel):
    """Validation for game ID path parameters."""
    model_config = ConfigDict(str_strip_whitespace=True)
    
    game_id: str = Field(
        ..., 
        min_length=1, 
        max_length=100,
        description="Game identifier (UUID or database ID)"
    )
    
    @field_validator('game_id')
    @classmethod
    def validate_game_id(cls, v: str) -> str:
        """Validate game ID format."""
        if not v:
            raise ValueError("Game ID cannot be empty")
        
        # Allow UUID format or database ID (numbers)
        if UUID_PATTERN.match(v) or v.isdigit():
            return v
        
        # For backward compatibility, allow alphanumeric strings
        if ALPHANUMERIC_PATTERN.match(v) and 3 <= len(v) <= 50:
            return v
            
        raise ValueError("Invalid game ID format. Must be UUID, numeric ID, or alphanumeric string")


class PlaylistIdParam(BaseModel):
    """Validation for playlist ID path parameters."""
    model_config = ConfigDict(str_strip_whitespace=True)
    
    playlist_id: str = Field(
        ..., 
        min_length=1, 
        max_length=50,
        description="Playlist identifier (Spotify ID or database ID)"
    )
    
    @field_validator('playlist_id')
    @classmethod
    def validate_playlist_id(cls, v: str) -> str:
        """Validate playlist ID format."""
        if not v:
            raise ValueError("Playlist ID cannot be empty")
        
        # Spotify playlist IDs are 22 character base62 strings
        if SPOTIFY_ID_PATTERN.match(v):
            return v
            
        # Database IDs are typically numeric
        if v.isdigit():
            return v
            
        # Allow alphanumeric for custom playlists
        if ALPHANUMERIC_PATTERN.match(v) and 3 <= len(v) <= 50:
            return v
            
        raise ValueError("Invalid playlist ID format. Must be Spotify ID, numeric ID, or alphanumeric string")


class TrackIdParam(BaseModel):
    """Validation for track ID path parameters."""
    model_config = ConfigDict(str_strip_whitespace=True)
    
    track_id: str = Field(
        ..., 
        min_length=1, 
        max_length=50,
        description="Track identifier (Spotify ID or database ID)"
    )
    
    @field_validator('track_id')
    @classmethod
    def validate_track_id(cls, v: str) -> str:
        """Validate track ID format."""
        if not v:
            raise ValueError("Track ID cannot be empty")
        
        # Spotify track IDs are 22 character base62 strings
        if SPOTIFY_ID_PATTERN.match(v):
            return v
            
        # Database IDs are typically numeric
        if v.isdigit():
            return v
            
        # Allow alphanumeric for custom tracks
        if ALPHANUMERIC_PATTERN.match(v) and 3 <= len(v) <= 50:
            return v
            
        raise ValueError("Invalid track ID format. Must be Spotify ID, numeric ID, or alphanumeric string")


class CardIdParam(BaseModel):
    """Validation for bingo card ID path parameters."""
    model_config = ConfigDict(str_strip_whitespace=True)
    
    card_id: str = Field(
        ..., 
        min_length=1, 
        max_length=100,
        description="Bingo card identifier (UUID or database ID)"
    )
    
    @field_validator('card_id')
    @classmethod
    def validate_card_id(cls, v: str) -> str:
        """Validate card ID format."""
        if not v:
            raise ValueError("Card ID cannot be empty")
        
        # Prefer UUID format for cards
        if UUID_PATTERN.match(v):
            return v
            
        # Allow numeric IDs
        if v.isdigit():
            return v
            
        # Allow alphanumeric strings
        if ALPHANUMERIC_PATTERN.match(v) and 3 <= len(v) <= 50:
            return v
            
        raise ValueError("Invalid card ID format. Must be UUID, numeric ID, or alphanumeric string")


class RoomCodeParam(BaseModel):
    """Validation for room code path parameters."""
    model_config = ConfigDict(str_strip_whitespace=True)
    
    room_code: str = Field(
        ..., 
        min_length=4, 
        max_length=10,
        description="Game room code (4-10 alphanumeric characters)"
    )
    
    @field_validator('room_code')
    @classmethod
    def validate_room_code(cls, v: str) -> str:
        """Validate room code format."""
        if not v:
            raise ValueError("Room code cannot be empty")
        
        # Room codes should be short alphanumeric strings
        if not ALPHANUMERIC_PATTERN.match(v):
            raise ValueError("Room code must contain only letters, numbers, hyphens, and underscores")
        
        if not (4 <= len(v) <= 10):
            raise ValueError("Room code must be between 4 and 10 characters")
            
        return v.upper()  # Standardize to uppercase


class FilenameParam(BaseModel):
    """Validation for filename path parameters."""
    model_config = ConfigDict(str_strip_whitespace=True)
    
    filename: str = Field(
        ..., 
        min_length=1, 
        max_length=255,
        description="Filename for static assets"
    )
    
    @field_validator('filename')
    @classmethod
    def validate_filename(cls, v: str) -> str:
        """Validate filename format."""
        if not v:
            raise ValueError("Filename cannot be empty")
        
        # Prevent directory traversal
        if '..' in v or '/' in v or '\\' in v:
            raise ValueError("Filename cannot contain directory traversal characters")
        
        # Allow common filename characters
        if not re.match(r'^[a-zA-Z0-9._-]+$', v):
            raise ValueError("Filename contains invalid characters")
        
        # Require file extension
        if '.' not in v:
            raise ValueError("Filename must have an extension")
        
        # Check extension is reasonable
        ext = v.split('.')[-1].lower()
        allowed_extensions = {
            'mp3', 'wav', 'ogg', 'flac',  # Audio
            'jpg', 'jpeg', 'png', 'gif', 'svg',  # Images
            'pdf', 'json', 'txt', 'csv'  # Documents
        }
        
        if ext not in allowed_extensions:
            raise ValueError(f"File extension '{ext}' not allowed")
            
        return v


# =============================================
# QUERY PARAMETER VALIDATION MODELS
# =============================================

class PaginationQuery(BaseModel):
    """Validation for pagination query parameters."""
    
    page: int = Field(1, ge=1, le=1000, description="Page number (1-based)")
    limit: int = Field(20, ge=1, le=100, description="Items per page")
    
    @field_validator('page')
    @classmethod
    def validate_page(cls, v: int) -> int:
        """Ensure page is positive."""
        if v < 1:
            raise ValueError("Page number must be at least 1")
        return v
    
    @field_validator('limit')
    @classmethod
    def validate_limit(cls, v: int) -> int:
        """Ensure reasonable page size."""
        if not (1 <= v <= 100):
            raise ValueError("Page size must be between 1 and 100")
        return v


class GameFilterQuery(BaseModel):
    """Validation for game filtering query parameters."""
    
    status: Optional[str] = Field(None, description="Filter by game status")
    host_id: Optional[str] = Field(None, description="Filter by host ID")
    playlist_id: Optional[str] = Field(None, description="Filter by playlist ID")
    
    @field_validator('status')
    @classmethod
    def validate_status(cls, v: Optional[str]) -> Optional[str]:
        """Validate game status filter."""
        if v is None:
            return v
        
        valid_statuses = {'waiting', 'in_progress', 'completed', 'cancelled'}
        if v.lower() not in valid_statuses:
            raise ValueError(f"Invalid status. Must be one of: {', '.join(valid_statuses)}")
        
        return v.lower()


class PlaylistFilterQuery(BaseModel):
    """Validation for playlist filtering query parameters."""
    
    suitable_for_games: Optional[bool] = Field(None, description="Filter playlists suitable for games")
    min_tracks: Optional[int] = Field(None, ge=1, le=10000, description="Minimum number of tracks")
    max_tracks: Optional[int] = Field(None, ge=1, le=10000, description="Maximum number of tracks")
    
    @field_validator('min_tracks', 'max_tracks')
    @classmethod
    def validate_track_counts(cls, v: Optional[int]) -> Optional[int]:
        """Validate track count ranges."""
        if v is not None and not (1 <= v <= 10000):
            raise ValueError("Track count must be between 1 and 10000")
        return v


# =============================================
# REQUEST BODY VALIDATION MODELS
# =============================================

class DeviceSelectionRequest(BaseModel):
    """Validation for device selection requests."""
    model_config = ConfigDict(str_strip_whitespace=True)
    
    device_id: str = Field(
        ..., 
        min_length=1, 
        max_length=200,
        description="Spotify device ID"
    )
    
    @field_validator('device_id')
    @classmethod
    def validate_device_id(cls, v: str) -> str:
        """Validate device ID format."""
        if not v:
            raise ValueError("Device ID cannot be empty")
        
        # Spotify device IDs can be various formats
        if not SAFE_STRING_PATTERN.match(v):
            raise ValueError("Device ID contains invalid characters")
            
        return v


class GameActionRequest(BaseModel):
    """Validation for game action requests (play, pause, etc.)."""
    model_config = ConfigDict(str_strip_whitespace=True)
    
    action: str = Field(
        ..., 
        description="Action to perform"
    )
    track_id: Optional[str] = Field(
        None, 
        max_length=50,
        description="Optional track ID for specific actions"
    )
    position: Optional[int] = Field(
        None, 
        ge=0, 
        le=300000,  # 5 minutes in seconds
        description="Playback position in seconds"
    )
    
    @field_validator('action')
    @classmethod
    def validate_action(cls, v: str) -> str:
        """Validate action type."""
        valid_actions = {'play', 'pause', 'next', 'previous', 'stop', 'seek'}
        if v.lower() not in valid_actions:
            raise ValueError(f"Invalid action. Must be one of: {', '.join(valid_actions)}")
        return v.lower()
    
    @field_validator('track_id')
    @classmethod
    def validate_track_id(cls, v: Optional[str]) -> Optional[str]:
        """Validate optional track ID."""
        if v is None:
            return v
        
        # Apply same validation as TrackIdParam
        if SPOTIFY_ID_PATTERN.match(v) or v.isdigit() or (ALPHANUMERIC_PATTERN.match(v) and 3 <= len(v) <= 50):
            return v
        
        raise ValueError("Invalid track ID format")


class MarkTrackRequest(BaseModel):
    """Validation for marking tracks on bingo cards."""
    model_config = ConfigDict(str_strip_whitespace=True)
    
    track_id: str = Field(
        ..., 
        min_length=1, 
        max_length=50,
        description="Track ID to mark"
    )
    marked: bool = Field(
        ...,
        description="Whether to mark or unmark the track"
    )
    
    @field_validator('track_id')
    @classmethod
    def validate_track_id(cls, v: str) -> str:
        """Validate track ID format."""
        if not v:
            raise ValueError("Track ID cannot be empty")
        
        if SPOTIFY_ID_PATTERN.match(v) or v.isdigit() or (ALPHANUMERIC_PATTERN.match(v) and 3 <= len(v) <= 50):
            return v
        
        raise ValueError("Invalid track ID format")


class CardGenerationRequest(BaseModel):
    """Validation for bingo card generation requests."""
    
    count: int = Field(
        1, 
        ge=1, 
        le=50,
        description="Number of cards to generate (1-50)"
    )
    seed: Optional[int] = Field(
        None,
        description="Random seed for reproducible card generation"
    )
    
    @field_validator('count')
    @classmethod
    def validate_count(cls, v: int) -> int:
        """Validate card count."""
        if not (1 <= v <= 50):
            raise ValueError("Card count must be between 1 and 50")
        return v


class AddPlaylistRequest(BaseModel):
    """Validation for adding playlists to the user's collection."""
    model_config = ConfigDict(str_strip_whitespace=True)
    
    playlist_id: str = Field(
        ..., 
        min_length=1, 
        max_length=50,
        description="Spotify playlist ID to add"
    )
    is_default: bool = Field(
        default=False,
        description="Whether to set this playlist as the default for new games"
    )
    
    @field_validator('playlist_id')
    @classmethod
    def validate_playlist_id(cls, v: str) -> str:
        """Validate playlist ID format."""
        if not v:
            raise ValueError("Playlist ID cannot be empty")
        
        # Spotify playlist IDs are 22 character base62 strings
        if SPOTIFY_ID_PATTERN.match(v):
            return v
            
        # Allow alphanumeric for custom playlists
        if ALPHANUMERIC_PATTERN.match(v) and 3 <= len(v) <= 50:
            return v
            
        raise ValueError("Invalid playlist ID format. Must be a valid Spotify playlist ID")


# =============================================
# UTILITY FUNCTIONS FOR VALIDATION
# =============================================

def validate_uuid(value: str, field_name: str = "ID") -> str:
    """
    Validate UUID format and return normalized UUID.
    
    Args:
        value: UUID string to validate
        field_name: Field name for error messages
        
    Returns:
        Normalized UUID string
        
    Raises:
        ValueError: If UUID format is invalid
    """
    if not value:
        raise ValueError(f"{field_name} cannot be empty")
    
    try:
        # Parse and normalize UUID
        uuid_obj = uuid.UUID(value)
        return str(uuid_obj)
    except ValueError:
        raise ValueError(f"Invalid {field_name} format. Must be a valid UUID")


def sanitize_string(value: str, max_length: int = 255, allow_special: bool = False) -> str:
    """
    Sanitize string input for safe database storage.
    
    Args:
        value: String to sanitize
        max_length: Maximum allowed length
        allow_special: Whether to allow special characters
        
    Returns:
        Sanitized string
        
    Raises:
        ValueError: If string contains invalid characters or is too long
    """
    if not isinstance(value, str):
        raise ValueError("Value must be a string")
    
    # Strip whitespace
    value = value.strip()
    
    # Check length
    if len(value) > max_length:
        raise ValueError(f"String too long. Maximum {max_length} characters allowed")
    
    # Check for null bytes (security)
    if '\0' in value:
        raise ValueError("String cannot contain null bytes")
    
    # Check character set
    if not allow_special:
        if not SAFE_STRING_PATTERN.match(value):
            raise ValueError("String contains invalid characters. Only letters, numbers, spaces, periods, hyphens, and underscores allowed")
    
    return value


def validate_spotify_id(value: str, id_type: str = "ID") -> str:
    """
    Validate Spotify ID format.
    
    Args:
        value: Spotify ID to validate
        id_type: Type of ID for error messages (track, playlist, etc.)
        
    Returns:
        Validated Spotify ID
        
    Raises:
        ValueError: If ID format is invalid
    """
    if not value:
        raise ValueError(f"Spotify {id_type} cannot be empty")
    
    if not SPOTIFY_ID_PATTERN.match(value):
        raise ValueError(f"Invalid Spotify {id_type} format. Must be 22 character base62 string")
    
    return value


# =============================================
# DEPENDENCY INJECTION HELPERS
# =============================================

def get_validated_game_id(game_id: str = Path(...)) -> str:
    """FastAPI dependency for validated game ID."""
    return GameIdParam(game_id=game_id).game_id


def get_validated_playlist_id(playlist_id: str = Path(...)) -> str:
    """FastAPI dependency for validated playlist ID."""
    return PlaylistIdParam(playlist_id=playlist_id).playlist_id


def get_validated_track_id(track_id: str = Path(...)) -> str:
    """FastAPI dependency for validated track ID."""
    return TrackIdParam(track_id=track_id).track_id


def get_validated_card_id(card_id: str = Path(...)) -> str:
    """FastAPI dependency for validated card ID."""
    return CardIdParam(card_id=card_id).card_id


def get_validated_room_code(room_code: str = Path(...)) -> str:
    """FastAPI dependency for validated room code."""
    return RoomCodeParam(room_code=room_code).room_code


def get_validated_filename(filename: str = Path(...)) -> str:
    """FastAPI dependency for validated filename."""
    return FilenameParam(filename=filename).filename
