import os
import asyncio
from threading import Lock
import time
from spotipy import Spotify
from spotipy.oauth2 import SpotifyOAuth
from spotipy.exceptions import SpotifyException
import logging
from typing import Optional
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

# Lock for token refresh to prevent race conditions
_token_refresh_lock = Lock()


async def get_current_session(request: Request = None):
    """Get current session - enhanced with secure session support and Supabase user support"""
    if not request:
        return {}

    # Try secure session first
    try:
        from app.secure_session import get_session_from_request
        from app.config import get_config

        config = get_config(); session_data = get_session_from_request(request, config.secret_key)
        if session_data:
            logger.debug("[SESSION-GET] Using secure session")
            return session_data
    except Exception as e:
        logger.warning(f"[SESSION-GET] Error getting secure session: {e}")

    # Try to get user from JWT token
    try:
        user = await get_current_user_optional(request)
        if user and user.spotify_access_token:
            logger.debug("[SESSION-GET] Using JWT token session")
            return {
                "token_info": {
                    "access_token": user.spotify_access_token,
                    "refresh_token": user.spotify_refresh_token,
                    "expires_at": user.spotify_token_expires_at.timestamp()
                    if user.spotify_token_expires_at
                    else None,
                },
                "user": user,
            }
    except Exception as e:
        logger.debug(f"[SESSION-GET] No JWT token session: {e}")

    # Do not fallback to legacy IP-based session (insecure)
    return {}


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
    """Fetch Spotify client with access token - enhanced with Supabase support"""
    session = await get_current_session(request)
    token_info = session.get("token_info")
    if not token_info:
        raise HTTPException(
            status_code=401,
            detail="Spotify authentication required. Please log in again.",
        )

    # Check if token needs refresh
    try:
        # Proactive refresh if missing/near expiry (<120s)
        token_info = session.get("token_info", {})
        expires_at = token_info.get("expires_at")
        needs_refresh = False
        if not expires_at:
            needs_refresh = True
        else:
            try:
                # expires_at expected as epoch seconds
                if time.time() > float(expires_at) - 120:
                    needs_refresh = True
            except Exception:
                needs_refresh = True

        if needs_refresh:
            await refresh_spotify_token(request)
        session = await get_current_session(
            request
        )  # Get updated session after refresh
        return Spotify(auth=session["token_info"]["access_token"])
    except SpotifyAPIError as e:
        raise convert_spotify_exception_to_http(e, "get Spotify client")
    except Exception as e:
        logger.error(
            f"[SPOTIFY-CLIENT] Unexpected error getting client",
            extra={"error": str(e), "error_type": type(e).__name__},
        )
        raise HTTPException(
            status_code=500,
            detail="Unable to connect to Spotify. Please try logging in again.",
        )


async def refresh_spotify_token(request: Request = None):
    """Refresh Spotify token if expired - enhanced with Supabase support and race condition protection"""
    if not request:
        logger.warning("No request provided for token refresh")
        return

    # Use lock to prevent concurrent refresh attempts
    with _token_refresh_lock:
        session = await get_current_session(request)
        token_info = session.get("token_info")

        if not token_info:
            raise SpotifyAPIError(
                "Spotify authentication required. Please log in again.", 401
            )

        sp_oauth = get_spotify_oauth()

        # Check if token is expired
        # Determine expiry robustly
        expired = False
        try:
            expired = sp_oauth.is_token_expired(token_info)
        except Exception:
            expired = True

        if expired:
            try:
                logger.info("[SPOTIFY-REFRESH-001] Refreshing expired Spotify token")

                # Use retry mechanism for token refresh
                refreshed_token = await spotify_api_call_with_retry(
                    lambda: sp_oauth.refresh_access_token(token_info["refresh_token"]),
                    max_retries=2,
                    operation_name="refresh Spotify token",
                )

                # Update secure session store if present
                try:
                    from app.secure_session import get_session_from_request
                    from app.config import get_config

                    config = get_config(); session_data = get_session_from_request(request, config.secret_key)
                    if session_data is not None:
                        session_data["token_info"] = refreshed_token
                except Exception:
                    pass

                # Update user in database if we have user info
                user = session.get("user")
                if user and isinstance(user, dict) and "id" in user:
                    from app.database import database

                    update_data = {
                        "spotify_access_token": refreshed_token["access_token"],
                        "spotify_refresh_token": refreshed_token.get(
                            "refresh_token", token_info.get("refresh_token")
                        ),
                        "spotify_token_expires_at": datetime.fromtimestamp(
                            refreshed_token["expires_at"], timezone.utc
                        ).isoformat()
                        if "expires_at" in refreshed_token
                        else None,
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    }

                    try:
                        await database.update_record("users", user["id"], update_data)
                        logger.info(
                            "[SPOTIFY-REFRESH-002] Updated user tokens in database"
                        )
                    except Exception as db_error:
                        logger.warning(
                            f"[SPOTIFY-REFRESH-WARN] Failed to update tokens in database: {db_error}"
                        )
                        # Continue anyway since session is updated

                logger.info(
                    "[SPOTIFY-REFRESH-003] Spotify token refreshed successfully"
                )

            except SpotifyException as e:
                logger.error(
                    f"[SPOTIFY-REFRESH-ERROR] Spotify error refreshing token",
                    extra={
                        "error": str(e),
                        "status_code": getattr(e, "http_status", "unknown"),
                    },
                )
                raise SpotifyAPIError(
                    "Failed to refresh Spotify token. Please log in again.", 401, e
                )
            except Exception as e:
                logger.error(
                    f"[SPOTIFY-REFRESH-ERROR] Unexpected error refreshing token",
                    extra={"error": str(e), "error_type": type(e).__name__},
                )
                raise SpotifyAPIError(
                    "Failed to refresh Spotify token. Please log in again.", 500, e
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
