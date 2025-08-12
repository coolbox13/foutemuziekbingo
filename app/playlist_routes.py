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
    """Get user's playlists from Spotify with caching"""
    try:
        spotify_client = await get_spotify_client(request)
        playlists = await playlist_service.get_user_playlists(
            current_user, spotify_client
        )

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
    """Get playlists suitable for game creation (with enough tracks)"""
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
