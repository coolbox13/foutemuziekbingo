from flask import Blueprint, jsonify, current_app
from app.spotify import get_spotify_client, refresh_spotify_token, pause_playback
from app.state import game_state
import random

bp = Blueprint("playback", __name__)


@bp.route("/api/play", methods=["POST"])
def api_play():
    """Play a random track from unplayed tracks."""
    try:
        sp = get_spotify_client()
        if not sp:
            return jsonify({"error": "Not logged in"}), 401

        refresh_spotify_token()
        state = game_state.get_state()

        if not state.get("unplayed_tracks"):
            return jsonify({"error": "No unplayed tracks available"}), 400

        # Select a random track
        track = random.choice(state["unplayed_tracks"])

        # Get active device before attempting playback
        devices = sp.devices()
        active_device = next((d for d in devices["devices"] if d["is_active"]), None)

        if not active_device:
            return jsonify({"error": "No active Spotify device found"}), 400

        # Update state before starting playback
        def update_track_lists(state):
            if track in state["unplayed_tracks"]:
                state["unplayed_tracks"].remove(track)
            if track not in state["played_tracks"]:
                state["played_tracks"].append(track)

        game_state.update_state(update_track_lists)

        # Start playback
        sp.start_playback(
            device_id=active_device["id"], uris=[f"spotify:track:{track['id']}"]
        )

        return jsonify(
            {
                "message": "Track playing.",
                "track": track,
                "device": active_device["name"],
            }
        )

    except Exception as e:
        current_app.logger.error(f"Error in /api/play: {e}")
        return jsonify({"error": str(e)}), 500


@bp.route("/api/pause", methods=["POST"])
def api_pause():
    """Pause current playback."""
    try:
        sp = get_spotify_client()
        refresh_spotify_token()

        pause_playback(sp)
        return jsonify({"message": "Playback paused"})
    except Exception as e:
        current_app.logger.error(f"Error pausing playback: {e}")
        return jsonify({"error": str(e)}), 500


@bp.route("/api/played_tracks", methods=["GET"])
def api_played_tracks():
    """Get list of played tracks."""
    try:
        state = game_state.get_state()
        return jsonify(
            {
                "played_tracks": state.get("played_tracks", []),
                "total_played": len(state.get("played_tracks", [])),
                "total_remaining": len(state.get("unplayed_tracks", [])),
            }
        )
    except Exception as e:
        current_app.logger.error(f"Error getting played tracks: {e}")
        return jsonify({"error": str(e)}), 500
