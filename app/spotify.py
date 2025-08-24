"""
Spotify Integration Module - Updated with Production-Ready Token Management

This module provides Spotify API integration with the new SpotifyTokenManager
for robust OAuth 2.0 token management, automatic refresh, and error handling.

Key Changes from Original:
- Replaced complex session handling with SpotifyTokenManager
- Removed emergency retry logic in favor of proper token refresh
- Simplified get_spotify_client() function
- Added comprehensive error handling and user feedback
- Maintained backward compatibility for existing routes

Security and Performance Improvements:
- Proper OAuth 2.0 refresh flow implementation
- Proactive token refresh (5 minutes before expiry)
- Thread-safe concurrent operations
- Clear user feedback for authentication issues
- Comprehensive logging and monitoring

Author: Claude Code Assistant
Date: 2025-01-18
Issue: CRIT-003 - Spotify token management failure resolution
"""

import os
import asyncio
import time
import logging
from typing import Optional, Dict, List, Any
from datetime import datetime, timezone

import spotipy
from spotipy import Spotify
from spotipy.oauth2 import SpotifyOAuth
from spotipy.exceptions import SpotifyException
from fastapi import Request, HTTPException

from app.spotify_token_manager import (
    spotify_token_manager,
    get_spotify_client_for_user,
    validate_user_spotify_auth
)
from app.auth_service import get_current_user_optional
from app.spotify_utils import (
    spotify_api_call_with_retry,
    SpotifyAPIError,
    convert_spotify_exception_to_http,
    get_devices_with_cache,
)

logger = logging.getLogger("music_bingo")


async def get_current_session(request: Request = None):
    """
    Get current session with token manager integration.

    This function is kept for backward compatibility but now delegates
    to the SpotifyTokenManager for proper token handling.

    Returns:
        dict: Session data or error information
    """
    session_id = f"session-{int(time.time())}"

    if not request:
        logger.warning(
            "[SESSION-ERROR-001] No request provided for session retrieval",
            extra={"session_id": session_id}
        )
        return {"error": "no_request", "message": "No request provided"}

    logger.debug(
        "[SESSION-START-001] Starting session retrieval with token manager",
        extra={"session_id": session_id, "path": request.url.path}
    )

    try:
        # Get current user from session/JWT
        user = await get_current_user_optional(request)

        if not user:
            logger.debug(
                "No authenticated user found in session",
                extra={"session_id": session_id}
            )
            return {
                "error": "no_valid_session",
                "message": "No valid authentication session found",
                "session_id": session_id,
            }

        # Check if user has valid Spotify authentication using token manager
        has_valid_auth = await validate_user_spotify_auth(user.id)

        if not has_valid_auth:
            logger.warning(
                "[SESSION-WARN-001] User found but Spotify authentication invalid",
                extra={
                    "session_id": session_id,
                    "user_id": user.id,
                    "spotify_id": user.spotify_id
                }
            )
            return {
                "error": "invalid_spotify_auth",
                "message": "Spotify authentication required. Please log in again.",
                "session_id": session_id,
                "user_id": user.id
            }

        # Get token info using token manager
        success, access_token, error = await spotify_token_manager.get_valid_token(user.id)

        if not success or not access_token:
            logger.warning(
                "[SESSION-WARN-002] Failed to get valid token for user",
                extra={
                    "session_id": session_id,
                    "user_id": user.id,
                    "error": error
                }
            )
            return {
                "error": "token_refresh_failed",
                "message": error or "Failed to refresh Spotify authentication",
                "session_id": session_id,
                "user_id": user.id
            }

        # Build session-compatible response
        token_info = {
            "access_token": access_token,
            # Additional token info can be added here if needed
        }

        # Convert user to dict for session compatibility
        user_dict = user.dict() if hasattr(user, 'dict') else user.__dict__

        logger.info(
            "[SESSION-SUCCESS-001] Session retrieved successfully via token manager",
            extra={
                "session_id": session_id,
                "user_id": user.id,
                "spotify_id": user.spotify_id,
                "auth_method": "token_manager"
            }
        )

        return {
            "token_info": token_info,
            "user": user_dict,
            "auth_method": "token_manager",
            "session_id": session_id,
        }

    except Exception as e:
        logger.error(
            "[SESSION-ERROR-002] Unexpected error in session retrieval",
            extra={
                "session_id": session_id,
                "error": str(e),
                "error_type": type(e).__name__
            },
            exc_info=True
        )

        return {
            "error": "session_error",
            "message": f"Session error: {str(e)}",
            "session_id": session_id,
        }


def get_spotify_oauth():
    """Initialize SpotifyOAuth with current configuration."""
    return SpotifyOAuth(
        client_id=os.getenv("SPOTIFY_CLIENT_ID"),
        client_secret=os.getenv("SPOTIFY_CLIENT_SECRET"),
        redirect_uri=os.getenv(
            "SPOTIFY_REDIRECT_URI", "http://localhost:1313/auth/callback"
        ),
        scope="playlist-read-private user-read-playback-state user-modify-playback-state user-read-private user-read-email",
    )


async def get_spotify_client(request: Request = None) -> Spotify:
    """
    Get Spotify client with automatic token management.

    This function has been simplified to use the SpotifyTokenManager
    for robust token handling, removing the complex session management
    and emergency retry logic from the original implementation.

    Args:
        request: FastAPI request object for user identification

    Returns:
        Spotify: Authenticated Spotify client

    Raises:
        HTTPException: If authentication fails or user needs to re-authenticate
    """
    client_id = f"client-{int(time.time())}"

    logger.debug(
        "[SPOTIFY-CLIENT-001] Creating Spotify client with token manager",
        extra={"client_id": client_id}
    )

    if not request:
        logger.error(
            "[SPOTIFY-CLIENT-ERROR-001] No request provided",
            extra={"client_id": client_id}
        )
        raise HTTPException(
            status_code=500,
            detail="Internal error: No request provided for authentication"
        )

    try:
        # Get current user
        user = await get_current_user_optional(request)

        if not user:
            logger.warning(
                "[SPOTIFY-CLIENT-ERROR-002] No authenticated user found",
                extra={"client_id": client_id}
            )
            raise HTTPException(
                status_code=401,
                detail="Authentication required. Please log in."
            )

        # Use token manager to get Spotify client
        logger.debug(
            "[SPOTIFY-CLIENT-002] Getting Spotify client for user",
            extra={
                "client_id": client_id,
                "user_id": user.id,
                "spotify_id": user.spotify_id
            }
        )

        # This function handles all token validation, refresh, and client creation
        spotify_client = await get_spotify_client_for_user(user.id)

        logger.info(
            "[SPOTIFY-CLIENT-003] Spotify client created successfully",
            extra={
                "client_id": client_id,
                "user_id": user.id,
                "spotify_id": user.spotify_id
            }
        )

        return spotify_client

    except HTTPException:
        # Re-raise HTTPException as-is (from token manager)
        raise
    except Exception as e:
        logger.error(
            "[SPOTIFY-CLIENT-ERROR-003] Unexpected error creating client",
            extra={
                "client_id": client_id,
                "error": str(e),
                "error_type": type(e).__name__
            },
            exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail="Unable to connect to Spotify. Please try again."
        )


async def refresh_spotify_token(request: Request = None):
    """
    Refresh Spotify token using the new token manager.

    This function is kept for backward compatibility but now delegates
    to the SpotifyTokenManager for proper token refresh handling.
    """
    refresh_id = f"refresh-{int(time.time())}"

    logger.info(
        "[SPOTIFY-REFRESH-001] Token refresh requested (delegating to token manager)",
        extra={"refresh_id": refresh_id}
    )

    if not request:
        logger.error(
            "[SPOTIFY-REFRESH-ERROR-001] No request provided",
            extra={"refresh_id": refresh_id}
        )
        raise HTTPException(
            status_code=500,
            detail="Internal error: No request provided for token refresh"
        )

    try:
        # Get current user
        user = await get_current_user_optional(request)

        if not user:
            logger.warning(
                "[SPOTIFY-REFRESH-ERROR-002] No authenticated user found",
                extra={"refresh_id": refresh_id}
            )
            raise HTTPException(
                status_code=401,
                detail="Authentication required. Please log in."
            )

        # Use token manager to refresh token
        logger.debug(
            "[SPOTIFY-REFRESH-002] Delegating refresh to token manager",
            extra={
                "refresh_id": refresh_id,
                "user_id": user.id
            }
        )

        refresh_result, new_token = await spotify_token_manager.refresh_token(user.id)

        if refresh_result.value.startswith("success") or refresh_result.value.startswith("skipped"):
            logger.info(
                "[SPOTIFY-REFRESH-003] Token refresh completed successfully",
                extra={
                    "refresh_id": refresh_id,
                    "user_id": user.id,
                    "result": refresh_result.value
                }
            )
        else:
            logger.warning(
                "[SPOTIFY-REFRESH-004] Token refresh failed",
                extra={
                    "refresh_id": refresh_id,
                    "user_id": user.id,
                    "result": refresh_result.value
                }
            )

            # Get user-friendly error message
            error_msg = spotify_token_manager._get_refresh_error_message(refresh_result)

            if "expired" in error_msg.lower() or "log in" in error_msg.lower():
                raise HTTPException(status_code=401, detail=error_msg)
            else:
                raise HTTPException(status_code=500, detail=error_msg)

    except HTTPException:
        # Re-raise HTTPException as-is
        raise
    except Exception as e:
        logger.error(
            "[SPOTIFY-REFRESH-ERROR-003] Unexpected error during refresh",
            extra={
                "refresh_id": refresh_id,
                "error": str(e),
                "error_type": type(e).__name__
            },
            exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to refresh Spotify authentication. Please try again."
        )


# The remaining functions are maintained as-is since they don't directly
# involve token management and work correctly with the new client creation

async def get_available_devices(sp):
    """Retrieve available devices from Spotify with caching and proper error handling."""
    try:
        return await get_devices_with_cache(sp)
    except SpotifyAPIError:
        # Re-raise SpotifyAPIError as-is
        raise
    except Exception as e:
        logger.error(
            "[SPOTIFY-DEVICES] Unexpected error getting devices",
            extra={"error": str(e), "error_type": type(e).__name__},
        )
        raise SpotifyAPIError(
            "Unable to retrieve Spotify devices. Please try again.", 500, e
        )


async def load_playlist_tracks(sp, playlist_id):
    """Load tracks from a Spotify playlist with proper error handling and pagination."""
    try:
        tracks = []

        # Get initial results with retry logic
        results = await spotify_api_call_with_retry(
            lambda: sp.playlist_items(playlist_id),
            operation_name=f"load playlist {playlist_id}",
        )

        while results:
            # Process current batch of tracks
            batch_tracks = []
            for item in results.get("items", []):
                if (
                    item["track"] and item["track"]["id"]
                ):  # Ensure track exists and has ID
                    batch_tracks.append(
                        {
                            "id": item["track"]["id"],
                            "name": item["track"]["name"],
                            "artist": ", ".join(
                                a["name"] for a in item["track"]["artists"]
                            ),
                        }
                    )

            tracks.extend(batch_tracks)

            # Get next page if available
            if results.get("next"):
                results = await spotify_api_call_with_retry(
                    lambda: sp.next(results),
                    operation_name=f"load playlist {playlist_id} (pagination)",
                )
            else:
                results = None

        logger.info(
            "[SPOTIFY-PLAYLIST] Loaded playlist tracks",
            extra={"playlist_id": playlist_id, "track_count": len(tracks)},
        )

        return tracks

    except SpotifyAPIError:
        # Re-raise SpotifyAPIError as-is
        raise
    except Exception as e:
        logger.error(
            "[SPOTIFY-PLAYLIST] Unexpected error loading playlist",
            extra={
                "playlist_id": playlist_id,
                "error": str(e),
                "error_type": type(e).__name__,
            },
        )
        raise SpotifyAPIError(
            "Failed to load playlist tracks. Please try again.", 500, e
        )


async def find_active_device(sp):
    """Find an active Spotify device with fallback strategies."""
    try:
        from app.spotify_utils import find_active_device_with_fallback

        return await find_active_device_with_fallback(sp)
    except SpotifyAPIError:
        # Re-raise SpotifyAPIError as-is
        raise
    except Exception as e:
        logger.error(
            "[SPOTIFY-DEVICE] Unexpected error finding device",
            extra={"error": str(e), "error_type": type(e).__name__},
        )
        raise SpotifyAPIError(
            "Unable to find an active Spotify device. Please try again.", 500, e
        )


async def pause_playback(sp, device_id=None):
    """Pause Spotify playback with proper error handling."""
    try:
        from app.spotify_utils import pause_playback_safe

        success = await pause_playback_safe(sp, device_id)
        if not success:
            raise SpotifyAPIError(
                "Failed to pause playback. The device may not be available.", 400
            )
    except SpotifyAPIError:
        # Re-raise SpotifyAPIError as-is
        raise
    except Exception as e:
        logger.error(
            "[SPOTIFY-PLAYBACK] Unexpected error pausing playback",
            extra={"error": str(e), "error_type": type(e).__name__},
        )
        raise SpotifyAPIError("Failed to pause playback. Please try again.", 500, e)
