from fastapi import APIRouter, HTTPException, Request
from app.spotify import get_spotify_client, pause_playback
from app.state import game_state
import random
import logging

router = APIRouter()
logger = logging.getLogger("music_bingo")


@router.post("/api/play")
async def api_play(request: Request):
    """Play a random track from unplayed tracks."""
    try:
        sp = get_spotify_client(request)
        if not sp:
            raise HTTPException(status_code=401, detail="Not logged in")

        state = game_state.get_state()
        if not state.get("unplayed_tracks"):
            raise HTTPException(status_code=400, detail="No unplayed tracks available")

        track = random.choice(state["unplayed_tracks"])

        def update_track_lists(state):
            if track in state["unplayed_tracks"]:
                state["unplayed_tracks"].remove(track)
            if track not in state["played_tracks"]:
                state["played_tracks"].append(track)

        game_state.update_state(update_track_lists)
        devices = sp.devices()
        active_device = next((d for d in devices["devices"] if d["is_active"]), None)

        if not active_device:
            raise HTTPException(status_code=400, detail="No active Spotify device found")

        sp.start_playback(device_id=active_device["id"], uris=[f"spotify:track:{track['id']}"])

        return {
            "message": "Track playing.",
            "track": track,
            "device": active_device["name"],
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error playing track: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/pause")
async def api_pause(request: Request):
    """Pause current playback."""
    try:
        sp = get_spotify_client(request)
        pause_playback(sp)
        return {"message": "Playback paused"}

    except Exception as e:
        logger.error(f"Error pausing playback: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/played_tracks")
async def api_played_tracks():
    """Get list of played tracks."""
    try:
        state = game_state.get_state()
        return {
            "played_tracks": state.get("played_tracks", []),
            "total_played": len(state.get("played_tracks", [])),
            "total_remaining": len(state.get("unplayed_tracks", [])),
        }

    except Exception as e:
        logger.error(f"Error getting played tracks: {e}")
        raise HTTPException(status_code=500, detail=str(e))
