"""
User and Database Models for Foute Muziek Bingo
Migrated from PWA project TypeScript interfaces to Python Pydantic models
"""
from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, EmailStr, Field, field_validator
from enum import Enum


class SubscriptionType(str, Enum):
    """User subscription types"""

    FREE = "free"
    PREMIUM = "premium"


class GameStatus(str, Enum):
    """Game status enumeration"""

    WAITING = "waiting"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class BingoMode(str, Enum):
    """Bingo pattern modes"""

    ROW = "row"
    COLUMN = "column"
    DIAGONAL = "diagonal"
    FULL_CARD = "full_card"
    ROW_COL_DIAG = "rowcoldiag"


# =============================================
# USER MODELS
# =============================================


class SpotifyUserProfile(BaseModel):
    """Spotify user profile data from API"""

    id: str = Field(..., description="Spotify user ID")
    display_name: Optional[str] = Field(None, description="User's display name")
    email: Optional[EmailStr] = Field(None, description="User's email address")
    country: Optional[str] = Field(None, description="ISO 3166-1 alpha-2 country code")
    product: Optional[str] = Field(None, description="free, open, premium")
    followers: Optional[Dict[str, Any]] = Field(
        None, description="Followers information"
    )
    images: Optional[List[Dict[str, Any]]] = Field(
        default_factory=list, description="Profile images"
    )
    external_urls: Optional[Dict[str, str]] = Field(None, description="External URLs")
    href: Optional[str] = Field(None, description="API href for this user")
    uri: Optional[str] = Field(None, description="Spotify URI")
    explicit_content: Optional[Dict[str, bool]] = Field(
        None, description="Explicit content settings"
    )


class SpotifyTokens(BaseModel):
    """Spotify OAuth token information"""

    access_token: str = Field(..., description="Access token")
    refresh_token: Optional[str] = Field(None, description="Refresh token")
    expires_at: Optional[datetime] = Field(None, description="Token expiration time")
    scope: Optional[str] = Field(None, description="Granted scopes")
    token_type: str = Field(default="Bearer", description="Token type")


class UserBase(BaseModel):
    """Base user model for creation and updates"""

    spotify_id: str = Field(..., description="Spotify user ID")
    display_name: Optional[str] = Field(None, description="User's display name")
    email: Optional[EmailStr] = Field(None, description="User's email address")
    country: Optional[str] = Field(None, description="User's country")
    subscription_type: SubscriptionType = Field(
        default=SubscriptionType.FREE, description="Subscription type"
    )

    @field_validator("spotify_id")
    @classmethod
    def validate_spotify_id(cls, v: str) -> str:
        """Validate Spotify ID format"""
        if not v or len(v) < 3:
            raise ValueError("Spotify ID must be at least 3 characters")
        return v


class UserCreate(UserBase):
    """User creation model"""

    spotify_profile: SpotifyUserProfile = Field(
        ..., description="Full Spotify profile data"
    )
    spotify_tokens: SpotifyTokens = Field(..., description="Spotify OAuth tokens")


class UserUpdate(BaseModel):
    """User update model"""

    display_name: Optional[str] = None
    email: Optional[EmailStr] = None
    country: Optional[str] = None
    subscription_type: Optional[SubscriptionType] = None
    avatar_url: Optional[str] = None
    spotify_tokens: Optional[SpotifyTokens] = None


class User(UserBase):
    """Complete user model"""

    id: str = Field(..., description="Internal user ID (UUID)")
    created_at: datetime = Field(..., description="User creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    last_login_at: Optional[datetime] = Field(None, description="Last login timestamp")

    # Spotify data
    spotify_uri: Optional[str] = Field(None, description="Spotify URI")
    spotify_href: Optional[str] = Field(None, description="Spotify API href")
    spotify_external_url: Optional[str] = Field(None, description="Spotify profile URL")

    # Profile data
    product: Optional[str] = Field(None, description="Spotify product type")
    followers_total: int = Field(default=0, description="Number of followers")
    images: List[Dict[str, Any]] = Field(
        default_factory=list, description="Profile images"
    )
    avatar_url: Optional[str] = Field(None, description="Primary avatar URL")

    # Content preferences
    explicit_content_filter_enabled: Optional[bool] = Field(
        None, description="Explicit content filter"
    )
    explicit_content_filter_locked: Optional[bool] = Field(
        None, description="Explicit content filter locked"
    )

    # Tokens (sensitive data, exclude from API responses)
    spotify_access_token: Optional[str] = Field(
        None, description="Current access token"
    )
    spotify_refresh_token: Optional[str] = Field(None, description="Refresh token")
    spotify_token_expires_at: Optional[datetime] = Field(
        None, description="Token expiration"
    )
    spotify_scope: Optional[str] = Field(None, description="Granted scopes")

    # Subscription data
    subscription_stripe_id: Optional[str] = Field(
        None, description="Stripe customer ID"
    )
    subscription_expires_at: Optional[datetime] = Field(
        None, description="Subscription expiry"
    )

    class Config:
        from_attributes = True


class UserPublic(BaseModel):
    """Public user model (safe for API responses)"""

    id: str
    spotify_id: str
    display_name: Optional[str]
    email: Optional[EmailStr]
    avatar_url: Optional[str]
    subscription_type: SubscriptionType
    created_at: datetime
    last_login_at: Optional[datetime]


# =============================================
# GAME MODELS
# =============================================


class Track(BaseModel):
    """Music track model"""

    id: str = Field(..., description="Spotify track ID")
    name: str = Field(..., description="Track name")
    artist: str = Field(..., description="Artist name(s)")
    album: Optional[str] = Field(None, description="Album name")
    duration_ms: Optional[int] = Field(
        None, description="Track duration in milliseconds"
    )
    preview_url: Optional[str] = Field(None, description="30-second preview URL")
    external_urls: Optional[Dict[str, str]] = Field(None, description="External URLs")
    played: bool = Field(default=False, description="Track has been played")


class Playlist(BaseModel):
    """Spotify playlist model"""

    id: str = Field(..., description="Internal playlist ID (UUID)")
    spotify_id: str = Field(..., description="Spotify playlist ID")
    name: str = Field(..., description="Playlist name")
    description: Optional[str] = Field(None, description="Playlist description")
    owner_id: str = Field(..., description="User ID of playlist owner")
    tracks: List[Track] = Field(default_factory=list, description="Playlist tracks")
    total_tracks: int = Field(default=0, description="Total number of tracks")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")

    class Config:
        from_attributes = True


class BingoCard(BaseModel):
    """Bingo card model"""

    id: str = Field(..., description="Card ID")
    user_id: str = Field(..., description="Owner user ID")
    game_id: str = Field(..., description="Associated game ID")
    grid: List[List[Dict[str, Any]]] = Field(..., description="5x5 grid of tracks")
    marked: List[List[bool]] = Field(..., description="Marked positions")
    patterns_completed: List[str] = Field(
        default_factory=list, description="Completed patterns"
    )
    is_winner: bool = Field(default=False, description="Card has winning pattern")
    created_at: datetime = Field(..., description="Creation timestamp")

    class Config:
        from_attributes = True


class GameSettings(BaseModel):
    """Game configuration settings"""

    track_duration: int = Field(default=30, description="Seconds each track plays")
    pause_between_tracks: int = Field(default=5, description="Pause between tracks")
    bingo_mode: BingoMode = Field(
        default=BingoMode.ROW_COL_DIAG, description="Winning patterns"
    )
    card_size: int = Field(default=5, description="Card grid size (5x5)")
    auto_mark: bool = Field(default=False, description="Auto-mark tracks")
    shuffle_tracks: bool = Field(default=True, description="Shuffle track order")


class GameBase(BaseModel):
    """Base game model"""

    name: str = Field(..., description="Game name")
    description: Optional[str] = Field(None, description="Game description")
    playlist_id: str = Field(..., description="Associated playlist ID")
    settings: GameSettings = Field(
        default_factory=GameSettings, description="Game settings"
    )
    max_players: int = Field(default=50, description="Maximum number of players")
    is_private: bool = Field(
        default=False, description="Private game (requires invite code)"
    )


class GameCreate(GameBase):
    """Game creation model"""

    pass


class GameUpdate(BaseModel):
    """Game update model"""

    name: Optional[str] = None
    description: Optional[str] = None
    settings: Optional[GameSettings] = None
    max_players: Optional[int] = None
    is_private: Optional[bool] = None


class Game(GameBase):
    """Complete game model"""

    id: str = Field(..., description="Game ID (UUID)")
    host_id: str = Field(..., description="Host user ID")
    status: GameStatus = Field(default=GameStatus.WAITING, description="Game status")
    room_code: Optional[str] = Field(None, description="6-digit room code for joining")
    current_track_index: int = Field(
        default=0, description="Currently playing track index"
    )
    started_at: Optional[datetime] = Field(None, description="Game start timestamp")
    ended_at: Optional[datetime] = Field(None, description="Game end timestamp")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")

    # Relationships
    playlist: Optional[Playlist] = Field(None, description="Associated playlist")
    players: List[UserPublic] = Field(default_factory=list, description="Game players")

    @field_validator("room_code")
    @classmethod
    def validate_room_code(cls, v: Optional[str]) -> Optional[str]:
        """Validate room code format"""
        if v is not None and (len(v) != 6 or not v.isdigit()):
            raise ValueError("Room code must be exactly 6 digits")
        return v

    cards: List[BingoCard] = Field(
        default_factory=list, description="Player bingo cards"
    )

    class Config:
        from_attributes = True


class GamePublic(BaseModel):
    """Public game model (safe for API responses)"""

    id: str
    name: str
    description: Optional[str]
    host_id: str
    status: GameStatus
    room_code: Optional[str]
    max_players: int
    current_players: int
    is_private: bool
    created_at: datetime
    started_at: Optional[datetime]


# =============================================
# API RESPONSE MODELS
# =============================================


class APIResponse(BaseModel):
    """Standard API response wrapper"""

    success: bool = Field(..., description="Request success status")
    message: Optional[str] = Field(None, description="Response message")
    data: Optional[Any] = Field(None, description="Response data")
    error: Optional[str] = Field(None, description="Error message if failed")


class PaginatedResponse(BaseModel):
    """Paginated API response"""

    success: bool = Field(..., description="Request success status")
    data: List[Any] = Field(..., description="Response data items")
    pagination: Dict[str, Any] = Field(..., description="Pagination metadata")
    total: int = Field(..., description="Total number of items")


# =============================================
# WEBSOCKET MODELS
# =============================================


class SocketEvent(BaseModel):
    """WebSocket event model"""

    event: str = Field(..., description="Event type")
    data: Dict[str, Any] = Field(..., description="Event data")
    room: Optional[str] = Field(None, description="Socket room")
    user_id: Optional[str] = Field(None, description="User ID who triggered event")
    timestamp: datetime = Field(
        default_factory=datetime.now, description="Event timestamp"
    )


class GameEvent(SocketEvent):
    """Game-specific WebSocket event"""

    game_id: str = Field(..., description="Game ID")
    player_id: Optional[str] = Field(None, description="Player who triggered event")


class PlayerJoinEvent(GameEvent):
    """Player joined game event"""

    event: str = Field(default="player_joined", description="Event type")
    player: UserPublic = Field(..., description="Player who joined")


class TrackStartEvent(GameEvent):
    """Track started playing event"""

    event: str = Field(default="track_started", description="Event type")
    track: Track = Field(..., description="Track that started")
    track_index: int = Field(..., description="Track index in playlist")


class BingoEvent(GameEvent):
    """Bingo completed event"""

    event: str = Field(default="bingo_completed", description="Event type")
    winner: UserPublic = Field(..., description="Winning player")
    card: BingoCard = Field(..., description="Winning card")
    pattern: str = Field(..., description="Winning pattern")


# =============================================
# VALIDATION HELPERS
# =============================================
# Note: Validators are now defined within their respective classes using @field_validator


# =============================================
# STATE MANAGEMENT MODELS
# =============================================


class GameStateType(str, Enum):
    """Game state storage types for hybrid architecture"""

    EPHEMERAL = "ephemeral"  # Redis - TTL managed, real-time data
    PERSISTENT = "persistent"  # Database - permanent storage


class RedisGameState(BaseModel):
    """Redis-stored ephemeral game state"""

    game_id: str = Field(..., description="Game ID")
    played_tracks: List[Track] = Field(default_factory=list, description="Tracks already played")
    unplayed_tracks: List[Track] = Field(default_factory=list, description="Tracks not yet played")
    current_track: Optional[Track] = Field(None, description="Currently playing track")
    current_track_index: int = Field(default=0, description="Current track index")
    active_players: List[str] = Field(default_factory=list, description="Active player IDs")
    websocket_sessions: Dict[str, str] = Field(
        default_factory=dict, description="Player ID to session ID mapping")
    bingo_validations: Dict[str, List[str]] = Field(
        default_factory=dict, description="Player bingo validations cache")
    game_started_at: Optional[datetime] = Field(None, description="Game start time")
    last_activity: datetime = Field(default_factory=datetime.now,
                                    description="Last activity timestamp")
    settings: GameSettings = Field(default_factory=GameSettings, description="Game settings cache")

    # TTL and state management
    ttl_seconds: int = Field(default=7200, description="Redis TTL in seconds (2 hours default)")
    state_version: int = Field(default=1, description="State version for conflict resolution")

    class Config:
        from_attributes = True


class PersistentGameState(BaseModel):
    """Database-stored persistent game state"""

    id: str = Field(..., description="State record ID (UUID)")
    game_id: str = Field(..., description="Game ID")
    state_data: Dict[str, Any] = Field(..., description="Serialized game state")
    state_type: str = Field(..., description="Type of state snapshot")
    created_at: datetime = Field(..., description="State creation timestamp")
    created_by: str = Field(..., description="User ID who created this state")
    description: Optional[str] = Field(None, description="State description")
    is_checkpoint: bool = Field(default=False, description="Is this a checkpoint save")
    is_final: bool = Field(default=False, description="Is this the final game state")

    class Config:
        from_attributes = True


class StateSnapshot(BaseModel):
    """Complete state snapshot combining ephemeral and persistent data"""

    game_id: str = Field(..., description="Game ID")
    ephemeral_state: Optional[RedisGameState] = Field(None, description="Current Redis state")
    persistent_state: Optional[PersistentGameState] = Field(None, description="Latest DB state")
    cards_state: List[BingoCard] = Field(default_factory=list, description="Current bingo cards")
    players_state: List[UserPublic] = Field(default_factory=list, description="Current players")
    sync_status: str = Field(default="synced", description="Sync status between Redis and DB")
    last_sync: datetime = Field(default_factory=datetime.now, description="Last sync timestamp")


class StateOperation(BaseModel):
    """State operation model for tracking changes"""

    operation_type: str = Field(..., description="Type of operation (create, update, delete)")
    game_id: str = Field(..., description="Game ID")
    user_id: Optional[str] = Field(None, description="User performing operation")
    operation_data: Dict[str, Any] = Field(..., description="Operation-specific data")
    timestamp: datetime = Field(default_factory=datetime.now, description="Operation timestamp")
    success: bool = Field(default=True, description="Operation success status")
    error_message: Optional[str] = Field(None, description="Error message if failed")


class StateMigration(BaseModel):
    """State migration tracking model"""

    migration_id: str = Field(..., description="Migration ID")
    source_type: str = Field(..., description="Source storage type (file, redis, db)")
    target_type: str = Field(..., description="Target storage type")
    games_migrated: List[str] = Field(
        default_factory=list, description="Successfully migrated game IDs")
    games_failed: List[str] = Field(default_factory=list, description="Failed migration game IDs")
    started_at: datetime = Field(default_factory=datetime.now, description="Migration start time")
    completed_at: Optional[datetime] = Field(None, description="Migration completion time")
    status: str = Field(default="in_progress", description="Migration status")
    total_games: int = Field(default=0, description="Total games to migrate")
    error_log: List[str] = Field(default_factory=list, description="Migration errors")


# =============================================
# STATE MANAGER INTERFACES
# =============================================


class StateManagerInterface(BaseModel):
    """Interface definition for state managers"""

    class Config:
        arbitrary_types_allowed = True

    async def get_game_state(self, game_id: str) -> Optional[Dict[str, Any]]:
        """Get complete game state"""
        raise NotImplementedError

    async def update_game_state(self, game_id: str, state_data: Dict[str, Any]) -> bool:
        """Update game state"""
        raise NotImplementedError

    async def delete_game_state(self, game_id: str) -> bool:
        """Delete game state"""
        raise NotImplementedError

    async def health_check(self) -> bool:
        """Check state manager health"""
        raise NotImplementedError


# =============================================
# REDIS KEY SCHEMAS
# =============================================


class RedisKeySchema:
    """Redis key naming conventions and schemas"""

    # Game state keys
    GAME_STATE = "game:state:{game_id}"
    GAME_TRACKS_PLAYED = "game:tracks:played:{game_id}"
    GAME_TRACKS_UNPLAYED = "game:tracks:unplayed:{game_id}"
    GAME_CURRENT_TRACK = "game:track:current:{game_id}"

    # Player state keys
    GAME_PLAYERS = "game:players:{game_id}"
    PLAYER_WEBSOCKET = "player:ws:{player_id}"
    PLAYER_BINGO_CACHE = "player:bingo:{player_id}:{game_id}"

    # Session management
    WEBSOCKET_SESSION = "ws:session:{session_id}"
    GAME_WEBSOCKET_MAPPING = "game:ws:mapping:{game_id}"

    # Game metadata
    GAME_SETTINGS = "game:settings:{game_id}"
    GAME_ACTIVITY = "game:activity:{game_id}"
    GAME_STATS = "game:stats:{game_id}"

    # Cross-cutting concerns
    ACTIVE_GAMES = "games:active"
    GAME_LOCKS = "lock:game:{game_id}"

    @classmethod
    def get_key(cls, key_pattern: str, **kwargs) -> str:
        """Generate Redis key from pattern and parameters"""
        return key_pattern.format(**kwargs)

    @classmethod
    def get_ttl(cls, key_type: str) -> int:
        """Get appropriate TTL for key type"""
        ttl_map = {
            "game_state": 7200,      # 2 hours
            "player_state": 3600,    # 1 hour
            "websocket": 1800,       # 30 minutes
            "cache": 900,            # 15 minutes
            "lock": 300,             # 5 minutes
            "activity": 86400,       # 24 hours
        }
        return ttl_map.get(key_type, 3600)  # Default 1 hour


# =============================================
# GAME VALIDATION MODELS
# =============================================

class GameValidationStatus(str, Enum):
    """Game validation status enumeration"""
    
    VALID = "valid"
    INVALID = "invalid"
    NOT_FOUND = "not_found"
    NO_PLAYLIST = "no_playlist"
    INSUFFICIENT_TRACKS = "insufficient_tracks"


class GameValidationResult(BaseModel):
    """Individual game validation result"""
    
    game_id: str = Field(..., description="Game ID")
    status: GameValidationStatus = Field(..., description="Validation status")
    exists: bool = Field(..., description="Whether game exists in database")
    has_playlist: bool = Field(default=False, description="Whether game has playlist data")
    track_count: int = Field(default=0, description="Number of tracks in playlist")
    can_generate_cards: bool = Field(default=False, description="Whether game has enough tracks for bingo cards")
    error_message: Optional[str] = Field(None, description="Error message if validation failed")
    last_activity: Optional[datetime] = Field(None, description="Last activity timestamp")


class BulkGameValidationRequest(BaseModel):
    """Request model for bulk game validation"""
    
    game_ids: List[str] = Field(..., description="List of game IDs to validate", max_items=100)
    include_track_count: bool = Field(default=True, description="Whether to include track count in response")
    filter_status: Optional[GameStatus] = Field(None, description="Optional status filter")


class BulkGameValidationResponse(BaseModel):
    """Response model for bulk game validation"""
    
    success: bool = Field(..., description="Request success status")
    total_requested: int = Field(..., description="Total number of games requested for validation")
    total_processed: int = Field(..., description="Total number of games processed")
    validation_results: List[GameValidationResult] = Field(..., description="Individual game validation results")
    summary: Dict[str, int] = Field(..., description="Summary of validation results by status")
    timestamp: datetime = Field(default_factory=datetime.now, description="Validation timestamp")
    processing_time_ms: Optional[float] = Field(None, description="Processing time in milliseconds")


class GameExistenceCheck(BaseModel):
    """Simple game existence check response"""
    
    game_id: str = Field(..., description="Game ID")
    exists: bool = Field(..., description="Whether game exists")
    accessible: bool = Field(default=False, description="Whether user can access the game")
    status: Optional[GameStatus] = Field(None, description="Game status if exists")

