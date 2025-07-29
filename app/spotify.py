import os
from spotipy import Spotify
from spotipy.oauth2 import SpotifyOAuth
import logging
from typing import Optional
from app.models import User
from app.auth_service import get_current_user_optional
from fastapi import Request
from datetime import datetime, timezone

logger = logging.getLogger("music_bingo")


async def get_current_session(request: Request = None):
    """Get current session - enhanced with Supabase user support"""
    # Try to get user from JWT token first
    if request:
        user = await get_current_user_optional(request)
        if user and user.spotify_access_token:
            return {
                "token_info": {
                    "access_token": user.spotify_access_token,
                    "refresh_token": user.spotify_refresh_token,
                    "expires_at": user.spotify_token_expires_at.timestamp() if user.spotify_token_expires_at else None
                },
                "user": user
            }
    
    # Fallback to legacy session storage
    if request:
        from app.auth_routes import sessions
        client_ip = request.client.host
        return sessions.get(client_ip, {})
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
        raise Exception("Spotify authentication required. Please log in again.")
    
    # Check if token needs refresh
    await refresh_spotify_token(request)
    session = await get_current_session(request)  # Get updated session after refresh
    return Spotify(auth=session["token_info"]["access_token"])


async def refresh_spotify_token(request: Request = None):
    """Refresh Spotify token if expired - enhanced with Supabase support"""
    if not request:
        logger.warning("No request provided for token refresh")
        return

    session = await get_current_session(request)
    token_info = session.get("token_info")
    
    if not token_info:
        raise Exception("No token information found in session.")

    sp_oauth = get_spotify_oauth()

    # Check if token is expired
    if sp_oauth.is_token_expired(token_info):
        try:
            logger.info("[SPOTIFY-REFRESH-001] Refreshing expired Spotify token")
            
            refreshed_token = sp_oauth.refresh_access_token(token_info["refresh_token"])
            
            # Update session storage (legacy)
            from app.auth_routes import sessions
            client_ip = request.client.host
            if client_ip in sessions:
                sessions[client_ip]["token_info"] = refreshed_token
            
            # Update user in database if we have user info
            user = session.get("user")
            if user and isinstance(user, dict) and "id" in user:
                from app.database import database
                update_data = {
                    "spotify_access_token": refreshed_token["access_token"],
                    "spotify_refresh_token": refreshed_token.get("refresh_token", token_info.get("refresh_token")),
                    "spotify_token_expires_at": datetime.fromtimestamp(
                        refreshed_token["expires_at"], timezone.utc
                    ).isoformat() if "expires_at" in refreshed_token else None,
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }
                
                try:
                    await database.update_record("users", user["id"], update_data)
                    logger.info("[SPOTIFY-REFRESH-002] Updated user tokens in database")
                except Exception as db_error:
                    logger.warning(f"[SPOTIFY-REFRESH-WARN] Failed to update tokens in database: {db_error}")
                    # Continue anyway since session is updated
            
            logger.info("[SPOTIFY-REFRESH-003] Spotify token refreshed successfully")
            
        except Exception as e:
            logger.error(f"[SPOTIFY-REFRESH-ERROR] Error refreshing token: {e}")
            raise Exception("Failed to refresh Spotify token. Please log in again.")


def get_available_devices(sp):
    """Retrieve available devices from Spotify."""
    try:
        devices_info = sp.devices()
        return devices_info.get("devices", [])
    except Exception as e:
        logger.error(f"Error getting devices: {e}")
        raise Exception("Failed to get Spotify devices. Please try again.")


def load_playlist_tracks(sp, playlist_id):
    """Load tracks from a Spotify playlist."""
    try:
        results = sp.playlist_items(playlist_id)
        tracks = []
        while results:
            tracks.extend(
                {
                    "id": track["track"]["id"],
                    "name": track["track"]["name"],
                    "artist": ", ".join(a["name"] for a in track["track"]["artists"]),
                }
                for track in results.get("items", [])
                if track["track"]
            )
            results = sp.next(results)  # Handle pagination
        return tracks
    except Exception as e:
        logger.error(f"Error loading playlist: {e}")
        raise Exception("Failed to load playlist tracks. Please try again.")


def play_random_track(sp):
    """Play a random track."""
    try:
        devices = sp.devices()
        active_device = next((d for d in devices["devices"] if d["is_active"]), None)

        if not active_device:
            raise Exception(
                "No active Spotify device found. Please ensure a Spotify client is active."
            )

        return active_device
    except Exception as e:
        logger.error(f"Error in play_random_track: {e}")
        raise Exception("Failed to play track. Please try again.")


def pause_playback(sp):
    """Pause Spotify playback."""
    try:
        sp.pause_playback()
    except Exception as e:
        logger.error(f"Error pausing playback: {e}")
        raise Exception("Failed to pause playback. Please try again.")
