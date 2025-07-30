from fastapi import APIRouter, HTTPException, Request, Depends
from typing import Optional
from app.spotify import get_spotify_client, pause_playback, find_active_device
from app.spotify_utils import (
    convert_spotify_exception_to_http, 
    SpotifyAPIError, 
    play_track_with_fallback
)
from app.auth_service import get_current_user
from app.game_service import game_service
from app.playlist_service import playlist_service
from app.websocket_service import ws_manager
from app.models import User
from datetime import datetime, timezone
import random
import logging

router = APIRouter()
logger = logging.getLogger("music_bingo")


@router.post("/api/games/{game_id}/play")
async def api_play_track(
    game_id: str,
    request: Request,
    current_user: User = Depends(get_current_user)
):
    """Play a random track from the game playlist (host only)."""
    try:
        # Get game and verify user is host
        game = await game_service.get_game(game_id, include_playlist=True)
        if not game:
            raise HTTPException(status_code=404, detail="Game not found")
        
        if game.host_id != current_user.id:
            raise HTTPException(status_code=403, detail="Only the game host can control playback")
        
        # Get playlist tracks
        if not game.playlist:
            raise HTTPException(status_code=400, detail="No playlist loaded for this game")
        
        # Get full playlist with tracks
        playlist = await playlist_service.get_playlist_by_id(game.playlist.id, include_tracks=True)
        if not playlist or not playlist.tracks:
            raise HTTPException(status_code=400, detail="No tracks available in playlist")
        
        # Filter unplayed tracks (simple implementation - in production you'd track this in database)
        available_tracks = [track for track in playlist.tracks if not track.played]
        if not available_tracks:
            # Reset all tracks if all have been played
            available_tracks = playlist.tracks
            for track in available_tracks:
                track.played = False
        
        # Select random track
        track = random.choice(available_tracks)
        track.played = True
        
        # Get Spotify client and play track with fallback
        sp = await get_spotify_client(request)
        
        # Use improved playback with device fallback
        track_uri = f"spotify:track:{track.id}"
        playback_info = await play_track_with_fallback(sp, track_uri)
        
        logger.info(f"[PLAYBACK-001] Track started playing", extra={
            "game_id": game_id,
            "track_id": track.id,
            "track_name": track.name,
            "user_id": current_user.id,
            "device": playback_info["device_name"]
        })
        
        # Broadcast track playing to all game participants
        await ws_manager.broadcast_to_game(game_id, {
            "type": "track_playing",
            "track": {
                "id": track.id,
                "name": track.name,
                "artist": track.artist,
                "album": track.album
            },
            "device": playback_info["device_name"],
            "timestamp": datetime.now(timezone.utc).isoformat()
        })

        return {
            "message": "Track playing.",
            "track": {
                "id": track.id,
                "name": track.name,
                "artist": track.artist,
                "album": track.album
            },
            "device": playback_info["device_name"],
        }

    except HTTPException:
        raise
    except SpotifyAPIError as e:
        raise convert_spotify_exception_to_http(e, "play track")
    except Exception as e:
        logger.error(f"[PLAYBACK-ERROR] Unexpected error playing track", extra={
            "game_id": game_id,
            "user_id": current_user.id,
            "error": str(e),
            "error_type": type(e).__name__
        })
        raise HTTPException(
            status_code=500, 
            detail="Unable to play track. Please check your Spotify connection and try again."
        )


@router.post("/api/play")
async def api_play_legacy(
    request: Request,
    current_user: User = Depends(get_current_user)
):
    """Legacy endpoint - Play a random track from active game."""
    logger.warning(f"[PLAYBACK-LEGACY] Legacy play endpoint called", extra={
        "user_id": current_user.id
    })
    
    try:
        # Find an active game where this user is the host
        from app.models import GameStatus
        user_games = await game_service.get_user_games(current_user.id, GameStatus.IN_PROGRESS)
        
        # Look for a game where user is host
        host_game = None
        for game in user_games:
            if game.host_id == current_user.id:
                host_game = game
                break
        
        if not host_game:
            # Try to find any waiting game they're hosting
            waiting_games = await game_service.get_user_games(current_user.id, GameStatus.WAITING)
            for game in waiting_games:
                if game.host_id == current_user.id:
                    host_game = game
                    break
        
        if not host_game:
            raise HTTPException(
                status_code=400, 
                detail="No active game found. Create a game first, then use the new API: /api/games/{game_id}/play"
            )
        
        # Redirect to the new endpoint logic
        logger.info(f"[PLAYBACK-LEGACY] Redirecting to game-specific endpoint", extra={
            "user_id": current_user.id,
            "game_id": host_game.id
        })
        
        # Call the new game-specific play endpoint
        return await api_play_track(host_game.id, request, current_user)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[PLAYBACK-LEGACY-ERROR] Unexpected error in legacy play endpoint", extra={
            "user_id": current_user.id,
            "error": str(e),
            "error_type": type(e).__name__
        })
        raise HTTPException(
            status_code=500, 
            detail="Unable to play track. Please try the game-specific endpoint."
        )


@router.post("/api/games/{game_id}/pause")
async def api_pause_game(
    game_id: str,
    request: Request,
    current_user: User = Depends(get_current_user)
):
    """Pause current playback (host only)."""
    try:
        # Verify user is host of the game
        game = await game_service.get_game(game_id)
        if not game:
            raise HTTPException(status_code=404, detail="Game not found")
        
        if game.host_id != current_user.id:
            raise HTTPException(status_code=403, detail="Only the game host can control playback")
        
        sp = await get_spotify_client(request)
        await pause_playback(sp)
        
        logger.info(f"[PLAYBACK-002] Playback paused", extra={
            "game_id": game_id,
            "user_id": current_user.id
        })
        
        # Broadcast pause to all game participants
        await ws_manager.broadcast_to_game(game_id, {
            "type": "playback_paused",
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        
        return {"message": "Playback paused"}

    except HTTPException:
        raise
    except SpotifyAPIError as e:
        raise convert_spotify_exception_to_http(e, "pause playback")
    except Exception as e:
        logger.error(f"[PLAYBACK-ERROR] Unexpected error pausing playback", extra={
            "game_id": game_id,
            "user_id": current_user.id,
            "error": str(e),
            "error_type": type(e).__name__
        })
        raise HTTPException(
            status_code=500, 
            detail="Unable to pause playback. Please try again."
        )


@router.post("/api/pause")
async def api_pause_legacy(
    request: Request,
    current_user: User = Depends(get_current_user)
):
    """Legacy pause endpoint - Pause playback for active game."""
    logger.warning(f"[PLAYBACK-LEGACY] Legacy pause endpoint called", extra={
        "user_id": current_user.id
    })
    
    try:
        # Find an active game where this user is the host
        from app.models import GameStatus
        user_games = await game_service.get_user_games(current_user.id, GameStatus.IN_PROGRESS)
        
        # Look for a game where user is host
        host_game = None
        for game in user_games:
            if game.host_id == current_user.id:
                host_game = game
                break
        
        if not host_game:
            # Try to find any waiting game they're hosting
            waiting_games = await game_service.get_user_games(current_user.id, GameStatus.WAITING)
            for game in waiting_games:
                if game.host_id == current_user.id:
                    host_game = game
                    break
        
        if not host_game:
            raise HTTPException(
                status_code=400, 
                detail="No active game found. Create a game first, then use the new API: /api/games/{game_id}/pause"
            )
        
        # Call the new game-specific pause endpoint
        return await api_pause_game(host_game.id, request, current_user)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[PLAYBACK-LEGACY-ERROR] Unexpected error in legacy pause endpoint", extra={
            "user_id": current_user.id,
            "error": str(e),
            "error_type": type(e).__name__
        })
        raise HTTPException(
            status_code=500, 
            detail="Unable to pause playback. Please try the game-specific endpoint."
        )


@router.get("/api/games/{game_id}/played-tracks")
async def api_game_played_tracks(
    game_id: str,
    current_user: User = Depends(get_current_user)
):
    """Get list of played tracks for a game."""
    try:
        # Verify user has access to this game
        game = await game_service.get_game(game_id, include_playlist=True, include_players=True)
        if not game:
            raise HTTPException(status_code=404, detail="Game not found")
        
        # Check if user has access to this game
        user_has_access = (
            game.host_id == current_user.id or
            any(player.id == current_user.id for player in game.players)
        )
        
        if not user_has_access and game.is_private:
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Get playlist tracks
        if not game.playlist:
            return {
                "played_tracks": [],
                "total_played": 0,
                "total_remaining": 0,
            }
        
        playlist = await playlist_service.get_playlist_by_id(game.playlist.id, include_tracks=True)
        if not playlist or not playlist.tracks:
            return {
                "played_tracks": [],
                "total_played": 0,
                "total_remaining": 0,
            }
        
        # Filter played and unplayed tracks
        played_tracks = [track for track in playlist.tracks if track.played]
        unplayed_tracks = [track for track in playlist.tracks if not track.played]
        
        return {
            "played_tracks": [
                {
                    "id": track.id,
                    "name": track.name,
                    "artist": track.artist,
                    "album": track.album
                }
                for track in played_tracks
            ],
            "total_played": len(played_tracks),
            "total_remaining": len(unplayed_tracks),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[PLAYBACK-ERROR] Unexpected error getting played tracks", extra={
            "game_id": game_id,
            "user_id": current_user.id,
            "error": str(e),
            "error_type": type(e).__name__
        })
        raise HTTPException(
            status_code=500, 
            detail="Unable to retrieve played tracks. Please try again."
        )


@router.get("/api/played_tracks")
async def api_played_tracks_legacy(
    current_user: User = Depends(get_current_user)
):
    """Legacy endpoint - Get list of played tracks from active game."""
    logger.warning(f"[PLAYBACK-LEGACY] Legacy played_tracks endpoint called", extra={
        "user_id": current_user.id
    })
    
    try:
        # Find an active game where this user is the host or participant
        from app.models import GameStatus
        user_games = await game_service.get_user_games(current_user.id, GameStatus.IN_PROGRESS)
        
        if not user_games:
            # Try waiting games
            user_games = await game_service.get_user_games(current_user.id, GameStatus.WAITING)
        
        if not user_games:
            return {
                "played_tracks": [],
                "total_played": 0,
                "total_remaining": 0,
            }
        
        # Use the first game found
        active_game = user_games[0]
        
        # Call the new game-specific played tracks endpoint
        return await api_game_played_tracks(active_game.id, current_user)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[PLAYBACK-LEGACY-ERROR] Unexpected error in legacy played_tracks endpoint", extra={
            "user_id": current_user.id,
            "error": str(e),
            "error_type": type(e).__name__
        })
        raise HTTPException(
            status_code=500, 
            detail="Unable to retrieve played tracks. Please try the game-specific endpoint."
        )
