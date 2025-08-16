import os
import asyncio
import time
from threading import Lock
from spotipy import Spotify
from spotipy.oauth2 import SpotifyOAuth
from spotipy.exceptions import SpotifyException
import logging
from typing import Optional, Dict
from app.models import User
from app.auth_service import get_current_user_optional
from app.spotify_utils import (
    spotify_api_call_with_retry,
    SpotifyAPIError,
    convert_spotify_exception_to_http,
    get_devices_with_cache,
)
from fastapi import Request, HTTPException
from datetime import datetime, timezone

logger = logging.getLogger("music_bingo")

# Legacy lock for backward compatibility (not used in new async refresh)
_token_refresh_lock = Lock()

# Global async lock for token refresh to prevent race conditions  
_token_refresh_locks: Dict[str, asyncio.Lock] = {}
_token_refresh_in_progress: Dict[str, bool] = {}


async def get_current_session(request: Request = None):
    """
    Get current session with improved error handling and clear authentication flow.
    
    Authentication Priority:
    1. Secure Redis session (preferred)
    2. JWT token with user database lookup
    3. Return empty session with clear error information
    
    Returns:
        dict: Session data with token_info and user, or empty dict with error info
    """
    session_id = f"session-{int(time.time())}"
    
    if not request:
        logger.warning(
            f"[SESSION-ERROR-001] No request provided for session retrieval",
            extra={"session_id": session_id}
        )
        return {"error": "no_request", "message": "No request provided"}

    logger.debug(
        f"[SESSION-START-001] Starting session retrieval",
        extra={"session_id": session_id, "path": request.url.path}
    )

    # Authentication Method 1: Secure Redis Session (Preferred)
    session_data = None
    session_error = None
    
    try:
        from app.secure_session import get_session_from_request
        from app.config import get_config

        config = get_config()
        session_data = await get_session_from_request(request, config.secret_key)
        
        if session_data:
            # Validate session has required token info
            token_info = session_data.get("token_info")
            user_data = session_data.get("user")
            
            if token_info and user_data:
                logger.info(
                    f"[SESSION-SUCCESS-001] ✅ Secure session found and validated",
                    extra={
                        "session_id": session_id,
                        "user_id": user_data.get("id", "unknown"),
                        "has_access_token": bool(token_info.get("access_token")),
                        "has_refresh_token": bool(token_info.get("refresh_token")),
                        "auth_method": "secure_session"
                    }
                )
                return session_data
            else:
                logger.warning(
                    f"[SESSION-WARN-001] Secure session exists but missing required data",
                    extra={
                        "session_id": session_id,
                        "has_token_info": bool(token_info),
                        "has_user_data": bool(user_data),
                        "auth_method": "secure_session"
                    }
                )
                session_error = "incomplete_session_data"
        else:
            logger.debug(
                f"[SESSION-DEBUG-001] No secure session data found",
                extra={"session_id": session_id, "auth_method": "secure_session"}
            )
            session_error = "no_session_data"
            
    except ImportError as e:
        logger.error(
            f"[SESSION-ERROR-002] Session module import error: {e}",
            extra={"session_id": session_id, "error": str(e), "auth_method": "secure_session"}
        )
        session_error = "import_error"
    except Exception as e:
        logger.error(
            f"[SESSION-ERROR-003] Secure session error: {e}",
            extra={"session_id": session_id, "error": str(e), "auth_method": "secure_session"},
            exc_info=True
        )
        session_error = "session_exception"

    # Authentication Method 2: JWT Token with Database Lookup
    try:
        user = await get_current_user_optional(request)
        
        if user:
            # Validate user has required Spotify tokens
            if user.spotify_access_token:
                # Build session data from user record
                expires_at = None
                if user.spotify_token_expires_at:
                    try:
                        expires_at = user.spotify_token_expires_at.timestamp()
                    except AttributeError as e:
                        logger.warning(
                            f"[SESSION-WARN-002] Invalid token expiration format",
                            extra={
                                "session_id": session_id,
                                "user_id": user.id,
                                "expires_at_type": type(user.spotify_token_expires_at).__name__,
                                "error": str(e)
                            }
                        )
                        expires_at = None

                token_info = {
                    "access_token": user.spotify_access_token,
                    "refresh_token": user.spotify_refresh_token,
                    "expires_at": expires_at,
                }
                
                # Convert user to dict for session compatibility
                user_dict = user.dict() if hasattr(user, 'dict') else user.__dict__
                
                logger.info(
                    f"[SESSION-SUCCESS-002] ✅ JWT session found and validated",
                    extra={
                        "session_id": session_id,
                        "user_id": user.id,
                        "spotify_id": user.spotify_id,
                        "has_access_token": bool(user.spotify_access_token),
                        "has_refresh_token": bool(user.spotify_refresh_token),
                        "auth_method": "jwt_token"
                    }
                )
                
                return {
                    "token_info": token_info,
                    "user": user_dict,
                    "auth_method": "jwt_token",
                    "session_id": session_id,
                }
            else:
                logger.warning(
                    f"[SESSION-WARN-003] User found but missing Spotify access token",
                    extra={
                        "session_id": session_id,
                        "user_id": user.id,
                        "has_refresh_token": bool(user.spotify_refresh_token),
                        "auth_method": "jwt_token"
                    }
                )
        else:
            logger.debug(
                f"[SESSION-DEBUG-002] No JWT user found",
                extra={"session_id": session_id, "auth_method": "jwt_token"}
            )
            
    except Exception as e:
        logger.error(
            f"[SESSION-ERROR-004] JWT token session error: {e}",
            extra={"session_id": session_id, "error": str(e), "auth_method": "jwt_token"},
            exc_info=True
        )

    # No valid session found
    logger.info(
        f"[SESSION-EMPTY-001] No valid session found",
        extra={
            "session_id": session_id,
            "secure_session_error": session_error,
            "path": request.url.path,
            "user_agent": request.headers.get("user-agent", "unknown")[:100],
        }
    )
    
    return {
        "error": "no_valid_session",
        "message": "No valid authentication session found",
        "session_id": session_id,
        "secure_session_error": session_error,
    }


def get_spotify_oauth():
    """Initialize SpotifyOAuth."""
    return SpotifyOAuth(
        client_id=os.getenv("SPOTIFY_CLIENT_ID"),
        client_secret=os.getenv("SPOTIFY_CLIENT_SECRET"),
        redirect_uri=os.getenv(
            "SPOTIFY_REDIRECT_URI", "http://localhost:1313/auth/callback"
        ),
        scope="playlist-read-private user-read-playback-state user-modify-playback-state",
    )


async def get_spotify_client(request: Request = None):
    """Fetch Spotify client with access token - enhanced error handling and session support"""
    client_id = f"client-{int(time.time())}"
    
    logger.debug(
        f"[SPOTIFY-CLIENT-001] Starting Spotify client creation",
        extra={"client_id": client_id}
    )
    
    session = await get_current_session(request)
    
    # Check for session errors
    if session.get("error"):
        error_type = session.get("error")
        error_message = session.get("message", "Unknown session error")
        session_id = session.get("session_id", "unknown")
        
        logger.warning(
            f"[SPOTIFY-CLIENT-ERROR-001] Session error: {error_type}",
            extra={
                "client_id": client_id,
                "session_id": session_id,
                "error_type": error_type,
                "error_message": error_message
            }
        )
        
        if error_type == "no_request":
            raise HTTPException(
                status_code=500,
                detail="Internal error: No request provided for authentication"
            )
        else:
            raise HTTPException(
                status_code=401,
                detail="Spotify authentication required. Please log in again."
            )
    
    token_info = session.get("token_info")
    if not token_info:
        auth_method = session.get("auth_method", "unknown")
        session_id = session.get("session_id", "unknown")
        
        logger.warning(
            f"[SPOTIFY-CLIENT-ERROR-002] No token info in session",
            extra={
                "client_id": client_id,
                "session_id": session_id,
                "auth_method": auth_method,
                "session_keys": list(session.keys())
            }
        )
        
        raise HTTPException(
            status_code=401,
            detail="Spotify authentication required. Please log in again.",
        )

    # Validate required token fields
    access_token = token_info.get("access_token")
    if not access_token:
        logger.error(
            f"[SPOTIFY-CLIENT-ERROR-003] Missing access token in session",
            extra={
                "client_id": client_id,
                "session_id": session.get("session_id", "unknown"),
                "token_info_keys": list(token_info.keys())
            }
        )
        raise HTTPException(
            status_code=401,
            detail="Invalid Spotify session. Please log in again."
        )

    # Check if token needs refresh
    try:
        expires_at = token_info.get("expires_at")
        needs_refresh = False
        
        if not expires_at:
            logger.info(
                f"[SPOTIFY-CLIENT-002] No expiration time, triggering refresh",
                extra={"client_id": client_id, "session_id": session.get("session_id")}
            )
            needs_refresh = True
        else:
            try:
                # expires_at expected as epoch seconds
                current_time = time.time()
                time_until_expiry = float(expires_at) - current_time
                
                if time_until_expiry <= 120:  # Refresh if expires within 2 minutes
                    logger.info(
                        f"[SPOTIFY-CLIENT-003] Token expires soon, triggering refresh",
                        extra={
                            "client_id": client_id,
                            "session_id": session.get("session_id"),
                            "time_until_expiry": time_until_expiry
                        }
                    )
                    needs_refresh = True
                else:
                    logger.debug(
                        f"[SPOTIFY-CLIENT-004] Token still valid",
                        extra={
                            "client_id": client_id,
                            "time_until_expiry": time_until_expiry
                        }
                    )
            except (ValueError, TypeError) as e:
                logger.warning(
                    f"[SPOTIFY-CLIENT-005] Invalid expiration format, triggering refresh",
                    extra={
                        "client_id": client_id,
                        "expires_at": expires_at,
                        "expires_at_type": type(expires_at).__name__,
                        "error": str(e)
                    }
                )
                needs_refresh = True

        if needs_refresh:
            logger.info(
                f"[SPOTIFY-CLIENT-006] Refreshing Spotify token",
                extra={"client_id": client_id, "session_id": session.get("session_id")}
            )
            
            await refresh_spotify_token(request)
            
            # Get updated session after refresh
            session = await get_current_session(request)
            
            # Re-validate session after refresh
            if session.get("error"):
                logger.error(
                    f"[SPOTIFY-CLIENT-ERROR-004] Session error after refresh",
                    extra={
                        "client_id": client_id,
                        "error": session.get("error"),
                        "message": session.get("message")
                    }
                )
                raise HTTPException(
                    status_code=401,
                    detail="Failed to refresh Spotify authentication. Please log in again."
                )
            
            token_info = session.get("token_info")
            if not token_info or not token_info.get("access_token"):
                logger.error(
                    f"[SPOTIFY-CLIENT-ERROR-005] No valid token after refresh",
                    extra={"client_id": client_id, "session_id": session.get("session_id")}
                )
                raise HTTPException(
                    status_code=401,
                    detail="Failed to refresh Spotify token. Please log in again."
                )
        
        # Create Spotify client
        final_access_token = session["token_info"]["access_token"]
        
        logger.info(
            f"[SPOTIFY-CLIENT-007] Creating Spotify client successfully",
            extra={
                "client_id": client_id,
                "session_id": session.get("session_id"),
                "auth_method": session.get("auth_method", "unknown"),
                "token_refreshed": needs_refresh
            }
        )
        
        return Spotify(auth=final_access_token)
        
    except SpotifyAPIError as e:
        logger.error(
            f"[SPOTIFY-CLIENT-ERROR-006] Spotify API error",
            extra={
                "client_id": client_id,
                "error": str(e),
                "error_type": type(e).__name__
            }
        )
        raise convert_spotify_exception_to_http(e, "get Spotify client")
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        logger.error(
            f"[SPOTIFY-CLIENT-ERROR-007] Unexpected error getting client",
            extra={
                "client_id": client_id,
                "error": str(e),
                "error_type": type(e).__name__
            },
            exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail="Unable to connect to Spotify. Please try logging in again.",
        )


async def refresh_spotify_token(request: Request = None):
    """
    Refresh Spotify token if expired - enhanced with proper async race condition protection.
    
    Uses per-user async locks to prevent multiple simultaneous refresh attempts
    for the same user while allowing different users to refresh concurrently.
    """
    refresh_id = f"refresh-{int(time.time())}"
    
    if not request:
        logger.warning(
            f"[SPOTIFY-REFRESH-ERROR-001] No request provided for token refresh",
            extra={"refresh_id": refresh_id}
        )
        return

    logger.debug(
        f"[SPOTIFY-REFRESH-001] Starting token refresh process",
        extra={"refresh_id": refresh_id}
    )

    # Get session first to identify user for per-user locking
    session = await get_current_session(request)
    
    if session.get("error"):
        logger.error(
            f"[SPOTIFY-REFRESH-ERROR-002] Session error during refresh",
            extra={
                "refresh_id": refresh_id,
                "error": session.get("error"),
                "message": session.get("message")
            }
        )
        raise SpotifyAPIError(
            "Spotify authentication required. Please log in again.", 401
        )
    
    token_info = session.get("token_info")
    if not token_info:
        logger.error(
            f"[SPOTIFY-REFRESH-ERROR-003] No token info in session",
            extra={"refresh_id": refresh_id, "session_keys": list(session.keys())}
        )
        raise SpotifyAPIError(
            "Spotify authentication required. Please log in again.", 401
        )

    # Identify user for locking (prefer user ID, fallback to session ID)
    user_data = session.get("user", {})
    user_id = user_data.get("id") if isinstance(user_data, dict) else None
    session_id = session.get("session_id", "unknown")
    lock_key = user_id or session_id
    
    # Get or create async lock for this user/session
    if lock_key not in _token_refresh_locks:
        _token_refresh_locks[lock_key] = asyncio.Lock()
    
    lock = _token_refresh_locks[lock_key]
    
    logger.debug(
        f"[SPOTIFY-REFRESH-002] Acquiring refresh lock",
        extra={
            "refresh_id": refresh_id,
            "lock_key": lock_key,
            "user_id": user_id,
            "session_id": session_id
        }
    )
    
    async with lock:
        try:
            # Check if refresh is already in progress for this user
            if _token_refresh_in_progress.get(lock_key, False):
                logger.info(
                    f"[SPOTIFY-REFRESH-003] Refresh already in progress, waiting",
                    extra={"refresh_id": refresh_id, "lock_key": lock_key}
                )
                # Another refresh is in progress, wait and return
                return
            
            # Mark refresh as in progress
            _token_refresh_in_progress[lock_key] = True
            
            logger.info(
                f"[SPOTIFY-REFRESH-004] Starting token refresh for user",
                extra={
                    "refresh_id": refresh_id,
                    "lock_key": lock_key,
                    "user_id": user_id
                }
            )
            
            # Re-fetch session in case it was updated by another process
            session = await get_current_session(request)
            token_info = session.get("token_info", {})
            
            if not token_info:
                logger.error(
                    f"[SPOTIFY-REFRESH-ERROR-004] Token info disappeared during refresh",
                    extra={"refresh_id": refresh_id, "lock_key": lock_key}
                )
                raise SpotifyAPIError(
                    "Spotify authentication required. Please log in again.", 401
                )

            sp_oauth = get_spotify_oauth()

            # Check if token is expired (with better error handling)
            expired = False
            try:
                expired = sp_oauth.is_token_expired(token_info)
                logger.debug(
                    f"[SPOTIFY-REFRESH-005] Token expiry check",
                    extra={
                        "refresh_id": refresh_id,
                        "lock_key": lock_key,
                        "expired": expired,
                        "expires_at": token_info.get("expires_at")
                    }
                )
            except Exception as e:
                logger.warning(
                    f"[SPOTIFY-REFRESH-WARN-001] Error checking token expiry, assuming expired",
                    extra={
                        "refresh_id": refresh_id,
                        "lock_key": lock_key,
                        "error": str(e)
                    }
                )
                expired = True

            if not expired:
                logger.info(
                    f"[SPOTIFY-REFRESH-006] Token not expired, skipping refresh",
                    extra={"refresh_id": refresh_id, "lock_key": lock_key}
                )
                return

            # Perform token refresh
            refresh_token = token_info.get("refresh_token")
            if not refresh_token:
                logger.error(
                    f"[SPOTIFY-REFRESH-ERROR-005] No refresh token available",
                    extra={"refresh_id": refresh_id, "lock_key": lock_key}
                )
                raise SpotifyAPIError(
                    "No refresh token available. Please log in again.", 401
                )

            logger.info(
                f"[SPOTIFY-REFRESH-007] Calling Spotify refresh API",
                extra={"refresh_id": refresh_id, "lock_key": lock_key}
            )

            # Use retry mechanism for token refresh
            refreshed_token = await spotify_api_call_with_retry(
                lambda: sp_oauth.refresh_access_token(refresh_token),
                max_retries=2,
                operation_name="refresh Spotify token",
            )

            if not refreshed_token or not refreshed_token.get("access_token"):
                logger.error(
                    f"[SPOTIFY-REFRESH-ERROR-006] Invalid refresh response",
                    extra={
                        "refresh_id": refresh_id,
                        "lock_key": lock_key,
                        "has_response": bool(refreshed_token),
                        "response_keys": list(refreshed_token.keys()) if refreshed_token else []
                    }
                )
                raise SpotifyAPIError(
                    "Failed to refresh Spotify token. Please log in again.", 401
                )

            logger.info(
                f"[SPOTIFY-REFRESH-008] Token refresh successful",
                extra={
                    "refresh_id": refresh_id,
                    "lock_key": lock_key,
                    "new_expires_at": refreshed_token.get("expires_at")
                }
            )

            # Update session storage atomically
            updated_secure_session = False
            updated_database = False
            
            # Update secure session store if present
            try:
                from app.secure_session import get_session_from_request
                from app.config import get_config

                config = get_config()
                session_data = await get_session_from_request(request, config.secret_key)
                if session_data is not None:
                    session_data["token_info"] = refreshed_token
                    # If there's an update_session function, use it
                    # Otherwise, the session should be updated in-place
                    updated_secure_session = True
                    logger.debug(
                        f"[SPOTIFY-REFRESH-009] Updated secure session",
                        extra={"refresh_id": refresh_id, "lock_key": lock_key}
                    )
            except Exception as e:
                logger.warning(
                    f"[SPOTIFY-REFRESH-WARN-002] Failed to update secure session",
                    extra={
                        "refresh_id": refresh_id,
                        "lock_key": lock_key,
                        "error": str(e)
                    }
                )

            # Update user in database if we have user info
            user = session.get("user")
            if user and isinstance(user, dict) and "id" in user:
                try:
                    from app.database import database

                    update_data = {
                        "spotify_access_token": refreshed_token["access_token"],
                        "spotify_refresh_token": refreshed_token.get(
                            "refresh_token", refresh_token  # Use new or keep old
                        ),
                        "spotify_token_expires_at": datetime.fromtimestamp(
                            refreshed_token["expires_at"], timezone.utc
                        ).isoformat()
                        if "expires_at" in refreshed_token
                        else None,
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    }

                    await database.update_record("users", user["id"], update_data)
                    updated_database = True
                    logger.info(
                        f"[SPOTIFY-REFRESH-010] Updated user tokens in database",
                        extra={"refresh_id": refresh_id, "lock_key": lock_key, "user_id": user["id"]}
                    )
                except Exception as db_error:
                    logger.error(
                        f"[SPOTIFY-REFRESH-ERROR-007] Failed to update tokens in database",
                        extra={
                            "refresh_id": refresh_id,
                            "lock_key": lock_key,
                            "user_id": user.get("id"),
                            "error": str(db_error)
                        }
                    )
                    # Don't raise - session update is more critical

            logger.info(
                f"[SPOTIFY-REFRESH-011] Token refresh completed successfully",
                extra={
                    "refresh_id": refresh_id,
                    "lock_key": lock_key,
                    "updated_secure_session": updated_secure_session,
                    "updated_database": updated_database
                }
            )

        except SpotifyException as e:
            logger.error(
                f"[SPOTIFY-REFRESH-ERROR-008] Spotify error during refresh",
                extra={
                    "refresh_id": refresh_id,
                    "lock_key": lock_key,
                    "error": str(e),
                    "status_code": getattr(e, "http_status", "unknown"),
                }
            )
            raise SpotifyAPIError(
                "Failed to refresh Spotify token. Please log in again.", 401, e
            )
        except Exception as e:
            logger.error(
                f"[SPOTIFY-REFRESH-ERROR-009] Unexpected error during refresh",
                extra={
                    "refresh_id": refresh_id,
                    "lock_key": lock_key,
                    "error": str(e),
                    "error_type": type(e).__name__
                },
                exc_info=True
            )
            raise SpotifyAPIError(
                "Failed to refresh Spotify token. Please log in again.", 500, e
            )
        finally:
            # Always clear the in-progress flag
            _token_refresh_in_progress.pop(lock_key, None)
            
            # Clean up old locks periodically
            if len(_token_refresh_locks) > 100:
                # Keep only recent locks
                keys_to_remove = list(_token_refresh_locks.keys())[:-50]
                for key in keys_to_remove:
                    _token_refresh_locks.pop(key, None)
                
                logger.debug(
                    f"[SPOTIFY-REFRESH-CLEANUP] Cleaned up old refresh locks",
                    extra={"refresh_id": refresh_id, "removed_count": len(keys_to_remove)}
                )


async def get_available_devices(sp):
    """Retrieve available devices from Spotify with caching and proper error handling."""
    try:
        return await get_devices_with_cache(sp)
    except SpotifyAPIError:
        # Re-raise SpotifyAPIError as-is
        raise
    except Exception as e:
        logger.error(
            f"[SPOTIFY-DEVICES] Unexpected error getting devices",
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
            f"[SPOTIFY-PLAYLIST] Loaded playlist tracks",
            extra={"playlist_id": playlist_id, "track_count": len(tracks)},
        )

        return tracks

    except SpotifyAPIError:
        # Re-raise SpotifyAPIError as-is
        raise
    except Exception as e:
        logger.error(
            f"[SPOTIFY-PLAYLIST] Unexpected error loading playlist",
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
            f"[SPOTIFY-DEVICE] Unexpected error finding device",
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
            f"[SPOTIFY-PLAYBACK] Unexpected error pausing playback",
            extra={"error": str(e), "error_type": type(e).__name__},
        )
        raise SpotifyAPIError("Failed to pause playback. Please try again.", 500, e)
