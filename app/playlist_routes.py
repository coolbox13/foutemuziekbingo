"""
Playlist Routes Module

This module handles all playlist-related endpoints for the Musical Bingo application.
It provides Spotify playlist integration, playlist management, and track retrieval
functionality with comprehensive caching and error handling.

Key Features:
- Spotify playlist retrieval with intelligent caching
- Playlist synchronization and refresh capabilities
- Track management and validation for game creation
- Playlist filtering for game suitability (minimum 25 tracks)
- Comprehensive error handling and logging

Security Features:
- JWT authentication required for all endpoints
- User-specific playlist access control
- Input validation for playlist IDs
- Rate limiting via global middleware
- CSRF protection via global middleware

Performance Features:
- Intelligent caching via playlist service
- Async operations for Spotify API calls
- Efficient database queries for playlist metadata
- Lazy loading of playlist tracks

Routes:
- GET /api/playlists: Retrieve user's Spotify playlists
- POST /api/playlists/{playlist_id}/sync: Sync specific playlist
- GET /api/playlists/{playlist_id}/tracks: Get playlist tracks
- GET /api/playlists/suitable-for-games: Get game-suitable playlists

Error Handling:
- Standard HTTP status codes (200, 404, 500)
- Structured error responses with user-friendly messages
- Comprehensive audit logging for debugging
- Graceful fallbacks for service failures
"""

from fastapi import APIRouter, HTTPException, Request, Depends
from typing import List
import logging
from app.models import Playlist, User
from app.auth_service import get_current_user
from app.playlist_service import playlist_service, PlaylistError
from app.spotify import get_spotify_client

router = APIRouter()
logger = logging.getLogger("music_bingo")


@router.get("/api/playlists", response_model=List[Playlist])
async def get_user_playlists(
    request: Request, current_user: User = Depends(get_current_user)
):
    """
    Retrieve all playlists for the authenticated user from Spotify.

    This endpoint fetches the user's Spotify playlists with intelligent caching
    to minimize API calls. Results are filtered to show only playlists the user
    owns or follows, providing data necessary for game creation and management.

    Args:
        request (Request): FastAPI request object containing session data
        current_user (User): Authenticated user from JWT token dependency

    Returns:
        List[Playlist]: List of playlist objects with metadata including:
            - spotify_id: Unique Spotify playlist identifier
            - name: User-friendly playlist name
            - description: Playlist description from Spotify
            - track_count: Number of tracks in the playlist
            - owner: Playlist owner information
            - images: Album artwork URLs
            - external_urls: Spotify web links

    Raises:
        HTTPException:
            - 401: Invalid or expired authentication
            - 403: Insufficient Spotify permissions
            - 429: Rate limit exceeded
            - 500: Internal server error or Spotify API failure

    Example:
        GET /api/playlists
        Authorization: Bearer <jwt_token>

        Response:
        [
            {
                "spotify_id": "37i9dQZF1DXcBWIGoYBM5M",
                "name": "Today's Top Hits",
                "description": "The biggest songs of the day",
                "track_count": 50,
                "owner": {"display_name": "Spotify", "id": "spotify"},
                "images": [{"url": "https://...", "width": 640, "height": 640}],
                "external_urls": {"spotify": "https://open.spotify.com/..."}
            }
        ]
    """
    try:
        logger.info("[PLAYLIST-DEBUG-001] Starting get_playlists endpoint")
        spotify_client = await get_spotify_client(request)
        logger.info("[PLAYLIST-DEBUG-002] Spotify client obtained")
        playlists = await playlist_service.get_user_playlists(
            current_user, spotify_client
        )
        logger.info("[PLAYLIST-DEBUG-003] Playlists retrieved from service")

        logger.info(
            "[PLAYLIST-API-001] Retrieved user playlists",
            extra={"user_id": current_user.id, "playlist_count": len(playlists)},
        )

        return playlists

    except PlaylistError as e:
        logger.error(
            "[PLAYLIST-API-ERROR] Playlist service error",
            extra={"user_id": current_user.id, "error": e.message},
        )
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        logger.error(
            "[PLAYLIST-API-ERROR] Unexpected error getting playlists",
            extra={"user_id": current_user.id, "error": str(e)},
        )
        raise HTTPException(status_code=500, detail="Failed to get playlists")


# Legacy get_playlists endpoint removed


@router.post("/api/playlists/{playlist_id}/sync", response_model=Playlist)
async def sync_playlist(
    playlist_id: str, request: Request, current_user: User = Depends(get_current_user)
):
    """
    Synchronize a specific playlist from Spotify with fresh data.

    This endpoint forces a refresh of playlist metadata from Spotify, bypassing
    any cached data. Useful when users have modified their playlists externally
    and need the application to reflect the latest changes immediately.

    Args:
        playlist_id (str): Spotify playlist ID to synchronize
        request (Request): FastAPI request object containing session data
        current_user (User): Authenticated user from JWT token dependency

    Returns:
        Playlist: Updated playlist object with fresh metadata including:
            - Updated track count if tracks were added/removed
            - Current playlist name and description
            - Latest album artwork
            - Fresh owner information

    Raises:
        HTTPException:
            - 401: Invalid or expired authentication
            - 403: User doesn't have access to this playlist
            - 404: Playlist not found or no longer exists
            - 429: Rate limit exceeded
            - 500: Spotify API error or internal server error

    Example:
        POST /api/playlists/37i9dQZF1DXcBWIGoYBM5M/sync
        Authorization: Bearer <jwt_token>

        Response:
        {
            "spotify_id": "37i9dQZF1DXcBWIGoYBM5M",
            "name": "Today's Top Hits (Updated)",
            "description": "Fresh hits updated daily",
            "track_count": 52,
            "last_synced": "2025-08-13T10:30:00Z"
        }
    """
    try:
        spotify_client = await get_spotify_client(request)

        # Force refresh of this specific playlist
        playlists = await playlist_service.get_user_playlists(
            current_user, spotify_client
        )

        # Find the requested playlist
        target_playlist = None
        for playlist in playlists:
            if playlist.spotify_id == playlist_id:
                target_playlist = playlist
                break

        if not target_playlist:
            raise HTTPException(status_code=404, detail="Playlist not found")

        logger.info(
            "[PLAYLIST-API-002] Playlist synced successfully",
            extra={
                "user_id": current_user.id,
                "playlist_id": playlist_id,
                "playlist_name": target_playlist.name,
            },
        )

        return target_playlist

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "[PLAYLIST-API-ERROR] Error syncing playlist",
            extra={
                "user_id": current_user.id,
                "playlist_id": playlist_id,
                "error": str(e),
            },
        )
        raise HTTPException(status_code=500, detail="Failed to sync playlist")


@router.get("/api/playlists/{playlist_id}/tracks")
async def get_playlist_tracks(
    playlist_id: str, request: Request, current_user: User = Depends(get_current_user)
):
    """
    Retrieve all tracks from a specific playlist.

    This endpoint fetches the complete track listing for a playlist, using
    cached data when available or loading fresh from Spotify when needed.
    Track data includes all metadata required for bingo game creation.

    Args:
        playlist_id (str): Spotify playlist ID to get tracks from
        request (Request): FastAPI request object containing session data
        current_user (User): Authenticated user from JWT token dependency

    Returns:
        dict: Object containing tracks array with track metadata:
            - tracks: List of track objects with:
                - spotify_id: Unique track identifier
                - name: Track title
                - artist: Primary artist name
                - album: Album name
                - duration_ms: Track duration in milliseconds
                - preview_url: 30-second audio preview URL (if available)
                - external_urls: Spotify web link
                - images: Album artwork URLs

    Raises:
        HTTPException:
            - 401: Invalid or expired authentication
            - 403: User doesn't have access to this playlist
            - 404: Playlist not found
            - 429: Rate limit exceeded
            - 500: Spotify API error or internal server error

    Example:
        GET /api/playlists/37i9dQZF1DXcBWIGoYBM5M/tracks
        Authorization: Bearer <jwt_token>

        Response:
        {
            "tracks": [
                {
                    "spotify_id": "4iV5W9uYEdYUVa79Axb7Rh",
                    "name": "Shape of You",
                    "artist": "Ed Sheeran",
                    "album": "÷ (Divide)",
                    "duration_ms": 233713,
                    "preview_url": "https://p.scdn.co/mp3-preview/...",
                    "external_urls": {"spotify": "https://open.spotify.com/..."}
                }
            ]
        }
    """
    try:
        # Get playlist from cache/database
        playlist = await playlist_service.get_playlist_by_spotify_id(
            playlist_id, current_user.id
        )

        if not playlist:
            raise HTTPException(status_code=404, detail="Playlist not found")

        # If no tracks cached, load from Spotify
        if not hasattr(playlist, "tracks") or not playlist.tracks:
            spotify_client = await get_spotify_client(request)
            tracks = await playlist_service.load_playlist_tracks_from_spotify(
                spotify_client, playlist_id
            )
            return {"tracks": [track.dict() for track in tracks]}

        return {"tracks": [track.dict() for track in playlist.tracks]}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "[PLAYLIST-API-ERROR] Error getting playlist tracks",
            extra={
                "user_id": current_user.id,
                "playlist_id": playlist_id,
                "error": str(e),
            },
        )
        raise HTTPException(status_code=500, detail="Failed to get playlist tracks")


@router.get("/api/playlists/suitable-for-games")
async def get_suitable_playlists(
    request: Request, current_user: User = Depends(get_current_user)
):
    """
    Get playlists suitable for bingo game creation.

    This endpoint filters the user's playlists to return only those with
    sufficient tracks for bingo game creation. The minimum track count
    requirement ensures games can be created with proper randomization
    and variety.

    Args:
        request (Request): FastAPI request object containing session data
        current_user (User): Authenticated user from JWT token dependency

    Returns:
        dict: Object containing filtered playlists:
            - playlists: List of playlist objects meeting game requirements:
                - Each playlist has minimum 25 tracks (5x5 bingo grid)
                - Includes track count for UI display
                - Contains all standard playlist metadata
                - Sorted by track count (descending) for better UX

    Raises:
        HTTPException:
            - 401: Invalid or expired authentication
            - 403: Insufficient Spotify permissions
            - 429: Rate limit exceeded
            - 500: Internal server error or service failure

    Example:
        GET /api/playlists/suitable-for-games
        Authorization: Bearer <jwt_token>

        Response:
        {
            "playlists": [
                {
                    "spotify_id": "37i9dQZF1DXcBWIGoYBM5M",
                    "name": "My Big Playlist",
                    "description": "Perfect for bingo games",
                    "track_count": 150,
                    "suitable_for_games": true,
                    "owner": {"display_name": "User", "id": "user123"}
                },
                {
                    "spotify_id": "37i9dQZF1DXcBWIGoYBM6N",
                    "name": "Another Good Playlist",
                    "track_count": 78,
                    "suitable_for_games": true
                }
            ]
        }

    Note:
        Only playlists with 25+ tracks are returned as they meet the minimum
        requirement for generating a 5x5 bingo card with sufficient variety.
    """
    try:
        playlists = await playlist_service.get_available_playlists_for_game(
            current_user
        )

        logger.info(
            "[PLAYLIST-API-004] Retrieved suitable playlists",
            extra={"user_id": current_user.id, "suitable_count": len(playlists)},
        )

        return {"playlists": [playlist.dict() for playlist in playlists]}

    except Exception as e:
        logger.error(
            "[PLAYLIST-API-ERROR] Error getting suitable playlists",
            extra={"user_id": current_user.id, "error": str(e)},
        )
        raise HTTPException(status_code=500, detail="Failed to get suitable playlists")
