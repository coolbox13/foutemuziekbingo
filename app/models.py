"""
User and Database Models for Foute Muziek Bingo
Migrated from PWA project TypeScript interfaces to Python Pydantic models
"""
from typing import Optional, List, Dict, Any, Union
from datetime import datetime
from pydantic import BaseModel, EmailStr, Field, validator
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
    followers: Optional[Dict[str, Any]] = Field(None, description="Followers information")
    images: Optional[List[Dict[str, Any]]] = Field(default_factory=list, description="Profile images")
    external_urls: Optional[Dict[str, str]] = Field(None, description="External URLs")
    href: Optional[str] = Field(None, description="API href for this user")
    uri: Optional[str] = Field(None, description="Spotify URI")
    explicit_content: Optional[Dict[str, bool]] = Field(None, description="Explicit content settings")


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
    subscription_type: SubscriptionType = Field(default=SubscriptionType.FREE, description="Subscription type")


class UserCreate(UserBase):
    """User creation model"""
    spotify_profile: SpotifyUserProfile = Field(..., description="Full Spotify profile data")
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
    images: List[Dict[str, Any]] = Field(default_factory=list, description="Profile images")
    avatar_url: Optional[str] = Field(None, description="Primary avatar URL")
    
    # Content preferences
    explicit_content_filter_enabled: Optional[bool] = Field(None, description="Explicit content filter")
    explicit_content_filter_locked: Optional[bool] = Field(None, description="Explicit content filter locked")
    
    # Tokens (sensitive data, exclude from API responses)
    spotify_access_token: Optional[str] = Field(None, description="Current access token")
    spotify_refresh_token: Optional[str] = Field(None, description="Refresh token")
    spotify_token_expires_at: Optional[datetime] = Field(None, description="Token expiration")
    spotify_scope: Optional[str] = Field(None, description="Granted scopes")
    
    # Subscription data
    subscription_stripe_id: Optional[str] = Field(None, description="Stripe customer ID")
    subscription_expires_at: Optional[datetime] = Field(None, description="Subscription expiry")
    
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
# JWT MODELS
# =============================================

class JWTTokens(BaseModel):
    """JWT token pair"""
    access_token: str = Field(..., description="JWT access token")
    refresh_token: str = Field(..., description="JWT refresh token")
    token_type: str = Field(default="bearer", description="Token type")
    expires_in: int = Field(default=900, description="Expires in seconds (15 minutes)")


class JWTPayload(BaseModel):
    """JWT token payload"""
    user_id: str = Field(..., description="User ID")
    spotify_id: str = Field(..., description="Spotify user ID")
    exp: int = Field(..., description="Expiration timestamp")
    iat: int = Field(..., description="Issued at timestamp")
    type: str = Field(default="access", description="Token type (access/refresh)")


# =============================================
# AUTHENTICATION MODELS
# =============================================

class AuthRequest(BaseModel):
    """Authentication request from frontend"""
    spotify_user: SpotifyUserProfile = Field(..., description="Spotify user profile")
    access_token: str = Field(..., description="Spotify access token")
    refresh_token: Optional[str] = Field(None, description="Spotify refresh token")


class AuthResponse(BaseModel):
    """Authentication response to frontend"""
    success: bool = Field(..., description="Authentication success")
    user: UserPublic = Field(..., description="User information")
    tokens: JWTTokens = Field(..., description="JWT tokens")
    message: Optional[str] = Field(None, description="Optional message")


class TokenRefreshRequest(BaseModel):
    """Token refresh request"""
    refresh_token: str = Field(..., description="JWT refresh token")


class TokenRefreshResponse(BaseModel):
    """Token refresh response"""
    success: bool = Field(..., description="Refresh success")
    access_token: str = Field(..., description="New access token")
    expires_in: int = Field(default=900, description="Expires in seconds")


# =============================================
# GAME MODELS
# =============================================

class Track(BaseModel):
    """Music track model"""
    id: str = Field(..., description="Spotify track ID")
    name: str = Field(..., description="Track name")
    artist: str = Field(..., description="Artist name(s)")
    album: Optional[str] = Field(None, description="Album name")
    duration_ms: Optional[int] = Field(None, description="Track duration in milliseconds")
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
    patterns_completed: List[str] = Field(default_factory=list, description="Completed patterns")
    is_winner: bool = Field(default=False, description="Card has winning pattern")
    created_at: datetime = Field(..., description="Creation timestamp")
    
    class Config:
        from_attributes = True


class GameSettings(BaseModel):
    """Game configuration settings"""
    track_duration: int = Field(default=30, description="Seconds each track plays")
    pause_between_tracks: int = Field(default=5, description="Pause between tracks")
    bingo_mode: BingoMode = Field(default=BingoMode.ROW_COL_DIAG, description="Winning patterns")
    card_size: int = Field(default=5, description="Card grid size (5x5)")
    auto_mark: bool = Field(default=False, description="Auto-mark tracks")
    shuffle_tracks: bool = Field(default=True, description="Shuffle track order")


class GameBase(BaseModel):
    """Base game model"""
    name: str = Field(..., description="Game name")
    description: Optional[str] = Field(None, description="Game description")
    playlist_id: str = Field(..., description="Associated playlist ID")
    settings: GameSettings = Field(default_factory=GameSettings, description="Game settings")
    max_players: int = Field(default=50, description="Maximum number of players")
    is_private: bool = Field(default=False, description="Private game (requires invite code)")


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
    current_track_index: int = Field(default=0, description="Currently playing track index")
    started_at: Optional[datetime] = Field(None, description="Game start timestamp")
    ended_at: Optional[datetime] = Field(None, description="Game end timestamp")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    
    # Relationships
    playlist: Optional[Playlist] = Field(None, description="Associated playlist")
    players: List[UserPublic] = Field(default_factory=list, description="Game players")
    cards: List[BingoCard] = Field(default_factory=list, description="Player bingo cards")
    
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
    timestamp: datetime = Field(default_factory=datetime.now, description="Event timestamp")


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

def validate_spotify_id(v: str) -> str:
    """Validate Spotify ID format"""
    if not v or len(v) < 3:
        raise ValueError("Spotify ID must be at least 3 characters")
    return v


def validate_room_code(v: Optional[str]) -> Optional[str]:
    """Validate room code format"""
    if v is not None and (len(v) != 6 or not v.isdigit()):
        raise ValueError("Room code must be exactly 6 digits")
    return v


# Add validators to models
UserBase.validator('spotify_id', allow_reuse=True)(validate_spotify_id)
Game.validator('room_code', allow_reuse=True)(validate_room_code)