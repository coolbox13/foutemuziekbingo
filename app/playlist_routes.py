from fastapi import APIRouter, HTTPException, Request, Depends
from typing import List, Optional
import logging
from app.models import Playlist, User, APIResponse
from app.auth_service import get_current_user
from app.playlist_service import playlist_service, PlaylistError
from app.spotify import get_spotify_client

router = APIRouter()
logger = logging.getLogger("music_bingo")


@router.get("/api/playlists", response_model=List[Playlist])
async def get_user_playlists(
    request: Request, current_user: User = Depends(get_current_user)
):
    """Get user's playlists from Spotify with caching"""
    try:
        spotify_client = await get_spotify_client(request)
        playlists = await playlist_service.get_user_playlists(
            current_user, spotify_client
        )

        logger.info(
            f"[PLAYLIST-API-001] Retrieved user playlists",
            extra={"user_id": current_user.id, "playlist_count": len(playlists)},
        )

        return playlists

    except PlaylistError as e:
        logger.error(
            f"[PLAYLIST-API-ERROR] Playlist service error",
            extra={"user_id": current_user.id, "error": e.message},
        )
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        logger.error(
            f"[PLAYLIST-API-ERROR] Unexpected error getting playlists",
            extra={"user_id": current_user.id, "error": str(e)},
        )
        raise HTTPException(status_code=500, detail="Failed to get playlists")


# Legacy get_playlists endpoint removed


@router.post("/api/playlists/{playlist_id}/sync", response_model=Playlist)
async def sync_playlist(
    playlist_id: str, request: Request, current_user: User = Depends(get_current_user)
):
    """Sync a specific playlist from Spotify"""
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
            f"[PLAYLIST-API-002] Playlist synced successfully",
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
            f"[PLAYLIST-API-ERROR] Error syncing playlist",
            extra={
                "user_id": current_user.id,
                "playlist_id": playlist_id,
                "error": str(e),
            },
        )
        raise HTTPException(status_code=500, detail="Failed to sync playlist")


# Legacy add_playlist endpoint removed
    request: Request, current_user: User = Depends(get_current_user)
):
    """Legacy endpoint - Add a new playlist to saved playlists."""
    try:
        data = await request.json()
        playlist_id = data.get("playlist_id")
        if not playlist_id:
            raise HTTPException(status_code=400, detail="No playlist ID provided")

        # Trigger sync of user playlists to ensure this playlist is cached
        spotify_client = await get_spotify_client(request)
        playlists = await playlist_service.get_user_playlists(
            current_user, spotify_client
        )

        # Find the playlist that was just synced
        target_playlist = None
        for playlist in playlists:
            if playlist.spotify_id == playlist_id:
                target_playlist = playlist
                break

        if not target_playlist:
            raise HTTPException(
                status_code=404, detail="Playlist not found in your Spotify library"
            )

        # Return legacy format
        new_playlist = {
            "id": target_playlist.spotify_id,
            "name": target_playlist.name,
            "owner": current_user.display_name,
            "is_default": False,
        }

        return {"message": "Playlist added successfully", "playlist": new_playlist}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding playlist: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Legacy remove_playlist endpoint removed
    request: Request, current_user: User = Depends(get_current_user)
):
    """Legacy endpoint - Remove a playlist from saved playlists."""
    try:
        data = await request.json()
        playlist_id = data.get("playlist_id")
        if not playlist_id:
            raise HTTPException(status_code=400, detail="No playlist ID provided")

        # Note: In the new system, playlists are automatically synced from Spotify
        # This endpoint now just returns success for compatibility
        logger.info(
            f"[PLAYLIST-API-003] Legacy playlist removal called",
            extra={"user_id": current_user.id, "playlist_id": playlist_id},
        )

        return {"message": "Playlist removed successfully"}
    except Exception as e:
        logger.error(f"Error removing playlist: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/playlists/{playlist_id}/tracks")
async def get_playlist_tracks(
    playlist_id: str, request: Request, current_user: User = Depends(get_current_user)
):
    """Get tracks from a specific playlist"""
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
            f"[PLAYLIST-API-ERROR] Error getting playlist tracks",
            extra={
                "user_id": current_user.id,
                "playlist_id": playlist_id,
                "error": str(e),
            },
        )
        raise HTTPException(status_code=500, detail="Failed to get playlist tracks")


# Legacy load_playlist endpoint removed
    request: Request, current_user: User = Depends(get_current_user)
):
    """Legacy endpoint - Load tracks from a playlist into the game state."""
    try:
        data = await request.json()
        playlist_id = data.get("playlist_id")
        if not playlist_id:
            raise HTTPException(status_code=400, detail="No playlist_id provided")

        # Load tracks using the new service
        spotify_client = await get_spotify_client(request)
        tracks = await playlist_service.load_playlist_tracks_from_spotify(
            spotify_client, playlist_id
        )

        if not tracks:
            raise HTTPException(status_code=400, detail="No tracks found in playlist")

        # Legacy response format for compatibility
        track_data = [
            {
                "id": track.id,
                "name": track.name,
                "artist": track.artist,
            }
            for track in tracks
        ]

        # Note: In the new system, game state is managed through the game service
        # This endpoint now just returns track information for compatibility
        return {
            "message": f"Loaded {len(tracks)} tracks from playlist",
            "tracks_available": len(tracks),
            "tracks_loaded": min(100, len(tracks)),
            "tracks": track_data,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error loading playlist: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/playlists/suitable-for-games")
async def get_suitable_playlists(
    request: Request, current_user: User = Depends(get_current_user)
):
    """Get playlists suitable for game creation (with enough tracks)"""
    try:
        playlists = await playlist_service.get_available_playlists_for_game(
            current_user
        )

        logger.info(
            f"[PLAYLIST-API-004] Retrieved suitable playlists",
            extra={"user_id": current_user.id, "suitable_count": len(playlists)},
        )

        return {"playlists": [playlist.dict() for playlist in playlists]}

    except Exception as e:
        logger.error(
            f"[PLAYLIST-API-ERROR] Error getting suitable playlists",
            extra={"user_id": current_user.id, "error": str(e)},
        )
        raise HTTPException(status_code=500, detail="Failed to get suitable playlists")


# Legacy set_default_playlist endpoint removed
    request: Request, current_user: User = Depends(get_current_user)
):
    """Legacy endpoint - Set a playlist as the default."""
    try:
        data = await request.json()
        playlist_id = data.get("playlist_id")
        if not playlist_id:
            raise HTTPException(status_code=400, detail="No playlist ID provided")

        # Note: In the new system, default playlist logic would be implemented
        # through user preferences or game settings. For now, just return success.
        logger.info(
            f"[PLAYLIST-API-005] Legacy default playlist set",
            extra={"user_id": current_user.id, "playlist_id": playlist_id},
        )

        return {"message": "Default playlist updated successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error setting default playlist: {e}")
        raise HTTPException(status_code=500, detail=str(e))
