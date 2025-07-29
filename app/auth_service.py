"""
JWT Authentication Service for Foute Muziek Bingo
Migrated from PWA project with enhanced security and Python patterns
"""
import os
import jwt
import bcrypt
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, Tuple
from fastapi import HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import asyncio
from app.models import (
    User, UserCreate, UserPublic, UserUpdate, 
    SpotifyUserProfile, SpotifyTokens, JWTTokens, JWTPayload,
    AuthRequest, AuthResponse, TokenRefreshRequest, TokenRefreshResponse
)
from app.database import database, DatabaseError, NotFoundError

logger = logging.getLogger("music_bingo")
security = HTTPBearer()


class AuthenticationError(Exception):
    """Authentication-related errors"""
    def __init__(self, message: str, status_code: int = 401):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class JWTService:
    """JWT token management service"""
    
    def __init__(self):
        self.jwt_secret = os.getenv("JWT_SECRET")
        self.jwt_refresh_secret = os.getenv("JWT_REFRESH_SECRET")
        self.jwt_expires_in = os.getenv("JWT_EXPIRES_IN", "15m")
        self.jwt_refresh_expires_in = os.getenv("JWT_REFRESH_EXPIRES_IN", "7d")
        
        if not self.jwt_secret or not self.jwt_refresh_secret:
            raise ValueError("JWT secrets must be configured in environment")
            
        # Validate JWT secret strength
        if len(self.jwt_secret) < 32:
            logger.warning("JWT secret is shorter than recommended 32 characters")
            
    def _parse_duration(self, duration: str) -> timedelta:
        """Parse duration string like '15m', '7d', '1h' to timedelta"""
        if duration.endswith('m'):
            return timedelta(minutes=int(duration[:-1]))
        elif duration.endswith('h'):
            return timedelta(hours=int(duration[:-1]))
        elif duration.endswith('d'):
            return timedelta(days=int(duration[:-1]))
        elif duration.endswith('s'):
            return timedelta(seconds=int(duration[:-1]))
        else:
            # Default to minutes if no unit specified
            return timedelta(minutes=int(duration))
    
    def generate_tokens(self, user_id: str, spotify_id: str) -> JWTTokens:
        """Generate JWT access and refresh tokens for user"""
        now = datetime.now(timezone.utc)
        access_expires = now + self._parse_duration(self.jwt_expires_in)
        refresh_expires = now + self._parse_duration(self.jwt_refresh_expires_in)
        
        # Access token payload
        access_payload = {
            "user_id": user_id,
            "spotify_id": spotify_id,
            "type": "access",
            "iat": int(now.timestamp()),
            "exp": int(access_expires.timestamp())
        }
        
        # Refresh token payload
        refresh_payload = {
            "user_id": user_id,
            "spotify_id": spotify_id,
            "type": "refresh",
            "iat": int(now.timestamp()),
            "exp": int(refresh_expires.timestamp())
        }
        
        access_token = jwt.encode(access_payload, self.jwt_secret, algorithm="HS256")
        refresh_token = jwt.encode(refresh_payload, self.jwt_refresh_secret, algorithm="HS256")
        
        logger.info(f"[AUTH-JWT-001] Generated tokens for user", extra={
            "user_id": user_id,
            "spotify_id": spotify_id,
            "access_expires": access_expires.isoformat(),
            "refresh_expires": refresh_expires.isoformat()
        })
        
        return JWTTokens(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=int(self._parse_duration(self.jwt_expires_in).total_seconds())
        )
    
    def verify_access_token(self, token: str) -> JWTPayload:
        """Verify and decode JWT access token"""
        try:
            payload = jwt.decode(token, self.jwt_secret, algorithms=["HS256"])
            
            # Validate token type
            if payload.get("type") != "access":
                raise AuthenticationError("Invalid token type")
                
            return JWTPayload(**payload)
            
        except jwt.ExpiredSignatureError:
            logger.warning("[AUTH-JWT-002] Access token expired")
            raise AuthenticationError("Token expired", status.HTTP_401_UNAUTHORIZED)
        except jwt.InvalidTokenError as e:
            logger.warning(f"[AUTH-JWT-003] Invalid access token: {str(e)}")
            raise AuthenticationError("Invalid token", status.HTTP_401_UNAUTHORIZED)
    
    def verify_refresh_token(self, token: str) -> JWTPayload:
        """Verify and decode JWT refresh token"""
        try:
            payload = jwt.decode(token, self.jwt_refresh_secret, algorithms=["HS256"])
            
            # Validate token type
            if payload.get("type") != "refresh":
                raise AuthenticationError("Invalid token type")
                
            return JWTPayload(**payload)
            
        except jwt.ExpiredSignatureError:
            logger.warning("[AUTH-JWT-004] Refresh token expired")
            raise AuthenticationError("Refresh token expired", status.HTTP_401_UNAUTHORIZED)
        except jwt.InvalidTokenError as e:
            logger.warning(f"[AUTH-JWT-005] Invalid refresh token: {str(e)}")
            raise AuthenticationError("Invalid refresh token", status.HTTP_401_UNAUTHORIZED)
    
    def refresh_access_token(self, refresh_token: str) -> str:
        """Generate new access token from refresh token"""
        payload = self.verify_refresh_token(refresh_token)
        
        now = datetime.now(timezone.utc)
        access_expires = now + self._parse_duration(self.jwt_expires_in)
        
        new_payload = {
            "user_id": payload.user_id,
            "spotify_id": payload.spotify_id,
            "type": "access",
            "iat": int(now.timestamp()),
            "exp": int(access_expires.timestamp())
        }
        
        new_token = jwt.encode(new_payload, self.jwt_secret, algorithm="HS256")
        
        logger.info(f"[AUTH-JWT-006] Refreshed access token", extra={
            "user_id": payload.user_id,
            "new_expires": access_expires.isoformat()
        })
        
        return new_token


class UserService:
    """User management service with Supabase integration"""
    
    def __init__(self):
        self.jwt_service = JWTService()
    
    async def create_or_update_user(self, spotify_profile: SpotifyUserProfile, 
                                    spotify_tokens: SpotifyTokens) -> User:
        """Create new user or update existing user from Spotify profile"""
        logger.info(f"[AUTH-USER-001] Processing user authentication", extra={
            "spotify_id": spotify_profile.id,
            "display_name": spotify_profile.display_name,
            "email": spotify_profile.email
        })
        
        try:
            # Check if user already exists
            existing_users = await database.query_records(
                "users",
                filters={"spotify_id": spotify_profile.id}
            )
            
            if existing_users:
                # Update existing user
                existing_user = existing_users[0]
                logger.info(f"[AUTH-USER-002] Updating existing user", extra={
                    "user_id": existing_user["id"],
                    "spotify_id": spotify_profile.id
                })
                
                # Prepare update data
                update_data = {
                    "display_name": spotify_profile.display_name,
                    "email": spotify_profile.email,
                    "country": spotify_profile.country,
                    "product": spotify_profile.product,
                    "last_login_at": datetime.now(timezone.utc).isoformat(),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    
                    # Update Spotify profile data
                    "spotify_href": spotify_profile.href,
                    "spotify_uri": spotify_profile.uri,
                    "spotify_external_url": spotify_profile.external_urls.get("spotify") if spotify_profile.external_urls else None,
                    "followers_total": spotify_profile.followers.get("total", 0) if spotify_profile.followers else 0,
                    "images": spotify_profile.images or [],
                    "avatar_url": spotify_profile.images[0]["url"] if spotify_profile.images else None,
                    
                    # Update explicit content settings
                    "explicit_content_filter_enabled": spotify_profile.explicit_content.get("filter_enabled") if spotify_profile.explicit_content else None,
                    "explicit_content_filter_locked": spotify_profile.explicit_content.get("filter_locked") if spotify_profile.explicit_content else None,
                    
                    # Update Spotify tokens
                    "spotify_access_token": spotify_tokens.access_token,
                    "spotify_refresh_token": spotify_tokens.refresh_token,
                    "spotify_token_expires_at": spotify_tokens.expires_at.isoformat() if spotify_tokens.expires_at else None,
                    "spotify_scope": spotify_tokens.scope
                }
                
                updated_user = await database.update_record("users", existing_user["id"], update_data)
                logger.info(f"[AUTH-USER-003] User updated successfully", extra={
                    "user_id": existing_user["id"]
                })
                
                return User(**updated_user)
            
            else:
                # Create new user
                logger.info(f"[AUTH-USER-004] Creating new user", extra={
                    "spotify_id": spotify_profile.id
                })
                
                # Prepare user creation data
                user_data = {
                    "spotify_id": spotify_profile.id,
                    "display_name": spotify_profile.display_name,
                    "email": spotify_profile.email,
                    "country": spotify_profile.country,
                    "product": spotify_profile.product,
                    "subscription_type": "free",
                    
                    # Spotify profile data
                    "spotify_uri": spotify_profile.uri,
                    "spotify_href": spotify_profile.href,
                    "spotify_external_url": spotify_profile.external_urls.get("spotify") if spotify_profile.external_urls else None,
                    "followers_total": spotify_profile.followers.get("total", 0) if spotify_profile.followers else 0,
                    "images": spotify_profile.images or [],
                    "avatar_url": spotify_profile.images[0]["url"] if spotify_profile.images else None,
                    
                    # Explicit content settings
                    "explicit_content_filter_enabled": spotify_profile.explicit_content.get("filter_enabled") if spotify_profile.explicit_content else None,
                    "explicit_content_filter_locked": spotify_profile.explicit_content.get("filter_locked") if spotify_profile.explicit_content else None,
                    
                    # Spotify tokens
                    "spotify_access_token": spotify_tokens.access_token,
                    "spotify_refresh_token": spotify_tokens.refresh_token,
                    "spotify_token_expires_at": spotify_tokens.expires_at.isoformat() if spotify_tokens.expires_at else None,
                    "spotify_scope": spotify_tokens.scope,
                    
                    # Timestamps
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "last_login_at": datetime.now(timezone.utc).isoformat()
                }
                
                new_user = await database.create_record("users", user_data)
                logger.info(f"[AUTH-USER-005] User created successfully", extra={
                    "user_id": new_user["id"],
                    "spotify_id": spotify_profile.id
                })
                
                return User(**new_user)
                
        except Exception as e:
            logger.error(f"[AUTH-USER-ERROR] Failed to create/update user", extra={
                "spotify_id": spotify_profile.id,
                "error": str(e)
            })
            raise AuthenticationError(f"Failed to process user: {str(e)}")
    
    async def get_user_by_id(self, user_id: str) -> Optional[User]:
        """Get user by internal ID"""
        try:
            user_data = await database.get_record("users", user_id)
            return User(**user_data) if user_data else None
        except Exception as e:
            logger.error(f"[AUTH-USER-ERROR] Failed to get user by ID", extra={
                "user_id": user_id,
                "error": str(e)
            })
            return None
    
    async def get_user_by_spotify_id(self, spotify_id: str) -> Optional[User]:
        """Get user by Spotify ID"""
        try:
            users = await database.query_records("users", filters={"spotify_id": spotify_id})
            return User(**users[0]) if users else None
        except Exception as e:
            logger.error(f"[AUTH-USER-ERROR] Failed to get user by Spotify ID", extra={
                "spotify_id": spotify_id,
                "error": str(e)
            })
            return None
    
    def user_to_public(self, user: User) -> UserPublic:
        """Convert User model to UserPublic (safe for API responses)"""
        return UserPublic(
            id=user.id,
            spotify_id=user.spotify_id,
            display_name=user.display_name,
            email=user.email,
            avatar_url=user.avatar_url,
            subscription_type=user.subscription_type,
            created_at=user.created_at,
            last_login_at=user.last_login_at
        )


class AuthService:
    """Main authentication service"""
    
    def __init__(self):
        self.jwt_service = JWTService()
        self.user_service = UserService()
    
    async def authenticate_spotify_user(self, auth_request: AuthRequest) -> AuthResponse:
        """Authenticate user with Spotify OAuth data"""
        request_id = f"auth-{int(datetime.now().timestamp())}"
        
        logger.info(f"[AUTH-001] Starting Spotify authentication", extra={
            "request_id": request_id,
            "spotify_id": auth_request.spotify_user.id,
            "display_name": auth_request.spotify_user.display_name
        })
        
        try:
            # Create Spotify tokens object
            expires_at = datetime.now(timezone.utc) + timedelta(hours=1)  # Spotify tokens typically expire in 1 hour
            spotify_tokens = SpotifyTokens(
                access_token=auth_request.access_token,
                refresh_token=auth_request.refresh_token,
                expires_at=expires_at,
                scope="playlist-read-private user-read-playback-state user-modify-playback-state"
            )
            
            # Create or update user
            user = await self.user_service.create_or_update_user(
                auth_request.spotify_user, 
                spotify_tokens
            )
            
            # Generate JWT tokens
            jwt_tokens = self.jwt_service.generate_tokens(user.id, user.spotify_id)
            
            # Convert to public user model
            public_user = self.user_service.user_to_public(user)
            
            logger.info(f"[AUTH-002] Authentication successful", extra={
                "request_id": request_id,
                "user_id": user.id,
                "spotify_id": user.spotify_id
            })
            
            return AuthResponse(
                success=True,
                user=public_user,
                tokens=jwt_tokens,
                message="Authentication successful"
            )
            
        except Exception as e:
            logger.error(f"[AUTH-ERROR] Authentication failed", extra={
                "request_id": request_id,
                "error": str(e),
                "spotify_id": auth_request.spotify_user.id
            })
            
            raise AuthenticationError(f"Authentication failed: {str(e)}")
    
    async def refresh_token(self, refresh_request: TokenRefreshRequest) -> TokenRefreshResponse:
        """Refresh JWT access token"""
        try:
            new_access_token = self.jwt_service.refresh_access_token(refresh_request.refresh_token)
            
            return TokenRefreshResponse(
                success=True,
                access_token=new_access_token,
                expires_in=int(self.jwt_service._parse_duration(self.jwt_service.jwt_expires_in).total_seconds())
            )
            
        except AuthenticationError:
            raise
        except Exception as e:
            logger.error(f"[AUTH-ERROR] Token refresh failed", extra={
                "error": str(e)
            })
            raise AuthenticationError(f"Token refresh failed: {str(e)}")
    
    async def get_current_user(self, token: str) -> User:
        """Get current user from JWT token"""
        try:
            payload = self.jwt_service.verify_access_token(token)
            user = await self.user_service.get_user_by_id(payload.user_id)
            
            if not user:
                raise AuthenticationError("User not found")
            
            return user
            
        except AuthenticationError:
            raise
        except Exception as e:
            logger.error(f"[AUTH-ERROR] Failed to get current user", extra={
                "error": str(e)
            })
            raise AuthenticationError("Failed to get current user")


# Dependency for FastAPI routes
async def get_current_user(credentials: HTTPAuthorizationCredentials = security) -> User:
    """FastAPI dependency to get current authenticated user"""
    try:
        auth_service = AuthService()
        return await auth_service.get_current_user(credentials.credentials)
    except AuthenticationError as e:
        raise HTTPException(
            status_code=e.status_code,
            detail=e.message,
            headers={"WWW-Authenticate": "Bearer"}
        )


# Optional dependency (returns None if not authenticated)
async def get_current_user_optional(request: Request) -> Optional[User]:
    """Optional authentication - returns None if no valid token"""
    try:
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return None
            
        token = auth_header.split(" ")[1]
        auth_service = AuthService()
        return await auth_service.get_current_user(token)
    except:
        return None


# Global auth service instance
auth_service = AuthService()