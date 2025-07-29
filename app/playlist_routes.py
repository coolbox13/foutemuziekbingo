from fastapi import APIRouter, HTTPException, Request
from app.spotify import get_spotify_client, load_playlist_tracks
from app.state import game_state, load_playlists, save_playlists
import random
import logging

router = APIRouter()
logger = logging.getLogger("music_bingo")


@router.get("/api/get_playlists")
async def api_get_playlists():
    """Get list of saved playlists."""
    try:
        playlists = load_playlists()
        return {
            "playlists": playlists,
            "total": len(playlists),
            "default": next((p for p in playlists if p.get("is_default")), None),
        }
    except Exception as e:
        logger.error(f"Error getting playlists: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/add_playlist")
async def api_add_playlist(request: Request):
    """Add a new playlist to saved playlists."""
    try:
        data = await request.json()
        playlist_id = data.get("playlist_id")
        is_default = data.get("is_default", False)
        if not playlist_id:
            raise HTTPException(status_code=400, detail="No playlist ID provided")

        sp = get_spotify_client(request)
        playlist_info = sp.playlist(playlist_id, fields="name,id,owner")
        playlists = load_playlists()

        if any(p["id"] == playlist_id for p in playlists):
            raise HTTPException(status_code=400, detail="Playlist already exists")

        if is_default:
            for playlist in playlists:
                playlist["is_default"] = False

        new_playlist = {
            "id": playlist_id,
            "name": playlist_info["name"],
            "owner": playlist_info["owner"]["display_name"],
            "is_default": is_default,
        }
        playlists.append(new_playlist)
        save_playlists(playlists)
        return {"message": "Playlist added successfully", "playlist": new_playlist}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding playlist: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/remove_playlist")
async def api_remove_playlist(request: Request):
    """Remove a playlist from saved playlists."""
    try:
        data = await request.json()
        playlist_id = data.get("playlist_id")
        if not playlist_id:
            raise HTTPException(status_code=400, detail="No playlist ID provided")

        playlists = load_playlists()
        playlists = [p for p in playlists if p["id"] != playlist_id]
        save_playlists(playlists)
        return {"message": "Playlist removed successfully"}
    except Exception as e:
        logger.error(f"Error removing playlist: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/load_playlist")
async def api_load_playlist(request: Request):
    """Load tracks from a playlist into the game state."""
    try:
        data = await request.json()
        playlist_id = data.get("playlist_id")
        if not playlist_id:
            raise HTTPException(status_code=400, detail="No playlist_id provided")

        sp = get_spotify_client(request)
        tracks = load_playlist_tracks(sp, playlist_id)
        if not tracks:
            raise HTTPException(status_code=400, detail="No tracks found in playlist")

        def update_game_state(state):
            state["unplayed_tracks"] = random.sample(tracks, min(100, len(tracks)))
            state["played_tracks"] = []
            state["cards"] = {}
            state["current_playlist"] = playlist_id
            state["num_tracks"] = len(state["unplayed_tracks"])

        game_state.update_state(update_game_state)
        updated_state = game_state.get_state()
        return {
            "message": (f"Loaded {len(tracks)} tracks from playlist, "
                        f"selected {updated_state['num_tracks']} for the game"),
            "tracks_available": len(tracks),
            "tracks_loaded": updated_state["num_tracks"],
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error loading playlist: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/set_default_playlist")
async def api_set_default_playlist(request: Request):
    """Set a playlist as the default."""
    try:
        data = await request.json()
        playlist_id = data.get("playlist_id")
        if not playlist_id:
            raise HTTPException(status_code=400, detail="No playlist ID provided")

        playlists = load_playlists()
        found = False
        for playlist in playlists:
            if playlist["id"] == playlist_id:
                playlist["is_default"] = True
                found = True
            else:
                playlist["is_default"] = False

        if not found:
            raise HTTPException(status_code=404, detail="Playlist not found")

        save_playlists(playlists)
        return {"message": "Default playlist updated successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error setting default playlist: {e}")
        raise HTTPException(status_code=500, detail=str(e))
