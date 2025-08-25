"""
Authentication Service Module - Session-Only Implementation

This module provides simplified authentication using Redis-backed secure sessions only.
JWT functionality has been removed for cleaner, simpler authentication architecture.

Key Features:
- Session-only authentication (no JWT tokens)
- User management with Supabase integration
- Spotify OAuth profile handling
- Session-based route protection

Security Features:
- Secure Redis-backed sessions
- Authentication error handling
- User profile management
"""

import logging
from datetime import datetime, timezone
from typing import Optional
from fastapi import HTTPException, Request
from app.models import User, UserPublic, SpotifyUserProfile, SpotifyTokens
from app.database import database

logger = logging.getLogger("music_bingo")


class AuthenticationError(Exception):
    """Authentication-related errors"""

    def __init__(self, message: str, status_code: int = 401):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class UserService:
    """User management service with Supabase integration"""

    async def create_or_update_user(
        self, spotify_profile: SpotifyUserProfile, spotify_tokens: SpotifyTokens
    ) -> User:
        """Create new user or update existing user from Spotify profile"""
        logger.info(
            "[AUTH-USER-001] Processing user authentication",
            extra={
                "spotify_id": spotify_profile.id,
                "display_name": spotify_profile.display_name,
                "email": spotify_profile.email,
            },
        )

        try:
            # Check if user already exists
            existing_users = await database.query_records(
                "users", filters={"spotify_id": spotify_profile.id}
            )

            if existing_users:
                # Update existing user
                existing_user = existing_users[0]
                logger.info(
                    "[AUTH-USER-002] Updating existing user",
                    extra={
                        "user_id": existing_user["id"],
                        "spotify_id": spotify_profile.id,
                    },
                )

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
                    "spotify_external_url": spotify_profile.external_urls.get("spotify")
                    if spotify_profile.external_urls
                    else None,
                    "followers_total": spotify_profile.followers.get("total", 0)
                    if spotify_profile.followers
                    else 0,
                    "images": spotify_profile.images or [],
                    "avatar_url": spotify_profile.images[0]["url"]
                    if spotify_profile.images
                    else None,
                    # Update explicit content settings
                    "explicit_content_filter_enabled": spotify_profile.explicit_content.get(
                        "filter_enabled"
                    )
                    if spotify_profile.explicit_content
                    else None,
                    "explicit_content_filter_locked": spotify_profile.explicit_content.get(
                        "filter_locked"
                    )
                    if spotify_profile.explicit_content
                    else None,
                    # Update Spotify tokens
                    "spotify_access_token": spotify_tokens.access_token,
                    "spotify_refresh_token": spotify_tokens.refresh_token,
                    "spotify_token_expires_at": spotify_tokens.expires_at.isoformat()
                    if spotify_tokens.expires_at
                    else None,
                    "spotify_scope": spotify_tokens.scope,
                }

                updated_user = await database.update_record(
                    "users", existing_user["id"], update_data
                )
                logger.info(
                    "[AUTH-USER-003] User updated successfully",
                    extra={"user_id": existing_user["id"]},
                )

                return User(**updated_user)

            else:
                # Create new user
                logger.info(
                    "[AUTH-USER-004] Creating new user",
                    extra={"spotify_id": spotify_profile.id},
                )

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
                    "spotify_external_url": spotify_profile.external_urls.get("spotify")
                    if spotify_profile.external_urls
                    else None,
                    "followers_total": spotify_profile.followers.get("total", 0)
                    if spotify_profile.followers
                    else 0,
                    "images": spotify_profile.images or [],
                    "avatar_url": spotify_profile.images[0]["url"]
                    if spotify_profile.images
                    else None,
                    # Explicit content settings
                    "explicit_content_filter_enabled": spotify_profile.explicit_content.get(
                        "filter_enabled"
                    )
                    if spotify_profile.explicit_content
                    else None,
                    "explicit_content_filter_locked": spotify_profile.explicit_content.get(
                        "filter_locked"
                    )
                    if spotify_profile.explicit_content
                    else None,
                    # Spotify tokens
                    "spotify_access_token": spotify_tokens.access_token,
                    "spotify_refresh_token": spotify_tokens.refresh_token,
                    "spotify_token_expires_at": spotify_tokens.expires_at.isoformat()
                    if spotify_tokens.expires_at
                    else None,
                    "spotify_scope": spotify_tokens.scope,
                    # Timestamps
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "last_login_at": datetime.now(timezone.utc).isoformat(),
                }

                new_user = await database.create_record("users", user_data)
                logger.info(
                    "[AUTH-USER-005] User created successfully",
                    extra={"user_id": new_user["id"], "spotify_id": spotify_profile.id},
                )

                return User(**new_user)

        except Exception as e:
            logger.error(
                "[AUTH-USER-ERROR] Failed to create/update user",
                extra={"spotify_id": spotify_profile.id, "error": str(e)},
            )
            raise AuthenticationError(f"Failed to process user: {str(e)}")

    async def get_user_by_id(self, user_id: str) -> Optional[User]:
        """Get user by internal ID"""
        try:
            user_data = await database.get_record("users", user_id)
            return User(**user_data) if user_data else None
        except Exception as e:
            logger.error(
                "[AUTH-USER-ERROR] Failed to get user by ID",
                extra={"user_id": user_id, "error": str(e)},
            )
            return None

    async def get_user_by_spotify_id(self, spotify_id: str) -> Optional[User]:
        """Get user by Spotify ID"""
        try:
            users = await database.query_records(
                "users", filters={"spotify_id": spotify_id}
            )
            return User(**users[0]) if users else None
        except Exception as e:
            logger.error(
                "[AUTH-USER-ERROR] Failed to get user by Spotify ID",
                extra={"spotify_id": spotify_id, "error": str(e)},
            )
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
            last_login_at=user.last_login_at,
        )


class AuthService:
    """Main authentication service - session-only implementation"""

    def __init__(self):
        self.user_service = UserService()

    async def authenticate_spotify_user(
        self, spotify_profile: SpotifyUserProfile, spotify_tokens: SpotifyTokens
    ) -> User:
        """Authenticate user with Spotify OAuth data and return User object"""
        request_id = f"auth-{int(datetime.now().timestamp())}"

        logger.info(
            "[AUTH-001] Starting Spotify authentication",
            extra={
                "request_id": request_id,
                "spotify_id": spotify_profile.id,
                "display_name": spotify_profile.display_name,
            },
        )

        try:
            # Create or update user
            user = await self.user_service.create_or_update_user(
                spotify_profile, spotify_tokens
            )

            logger.info(
                "[AUTH-002] Authentication successful",
                extra={
                    "request_id": request_id,
                    "user_id": user.id,
                    "spotify_id": user.spotify_id,
                },
            )

            return user

        except Exception as e:
            logger.error(
                "[AUTH-ERROR] Authentication failed",
                extra={
                    "request_id": request_id,
                    "error": str(e),
                    "spotify_id": spotify_profile.id,
                },
            )

            raise AuthenticationError(f"Authentication failed: {str(e)}")


# Simplified session-only dependency for FastAPI routes
async def get_current_user(request: Request) -> User:
    """Get current user from session cookie only."""

    logger.info(f"[AUTH-GET-USER] Authentication attempt from {request.url.path}")

    try:
        from app.secure_session import get_session_from_request
        from app.config import get_config

        config = get_config()
        session_data = await get_session_from_request(request, config.secret_key)
        logger.info(f"[AUTH-GET-USER] Session data retrieved: {bool(session_data)}")

        if session_data and session_data.get("user"):
            user_dict = session_data["user"]
            # If only user_id is present, fetch full user from DB
            if isinstance(user_dict, dict) and user_dict.get("id"):
                user_service = UserService()
                user = await user_service.get_user_by_id(user_dict["id"])
                if user:
                    return user

        logger.error("[AUTH-GET-USER] Authentication failed - no valid session")
        raise AuthenticationError("Not authenticated")

    except AuthenticationError as e:
        raise HTTPException(
            status_code=e.status_code,
            detail=e.message,
        )
    except Exception as e:
        logger.error(f"[AUTH-GET-USER] Unexpected error: {e}")
        raise HTTPException(
            status_code=401,
            detail="Not authenticated",
        )


# Optional dependency (returns None if not authenticated)
async def get_current_user_optional(request: Request) -> Optional[User]:
    """Optional authentication - returns None if no valid session"""
    try:
        return await get_current_user(request)
    except HTTPException:
        return None


# Global auth service instance
auth_service = AuthService()
