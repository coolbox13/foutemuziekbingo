from flask import Blueprint, jsonify, request, current_app
from app.spotify import get_spotify_client, refresh_spotify_token, play_random_track, pause_playback
from app.state import ThreadSafeGameState
import random

bp = Blueprint("playback", __name__)
game_state = ThreadSafeGameState()

@bp.route("/api/play", methods=["POST"])
def api_play():
    try:
        sp = get_spotify_client()
        if not sp:
            return jsonify({"error": "Not logged in"}), 401

        refresh_spotify_token()
        state = game_state.get_state()

        if not state.get("unplayed_tracks"):
            return jsonify({"error": "No unplayed tracks available"}), 400

        track = random.choice(state["unplayed_tracks"])

        def update_track_lists(state):
            if track in state["unplayed_tracks"]:
                state["unplayed_tracks"].remove(track)
            state["played_tracks"].append(track)

        game_state.update_state(update_track_lists)

        devices = sp.devices()
        active_device = next((d for d in devices["devices"] if d["is_active"]), None)

        if not active_device:
            return jsonify({"error": "No active Spotify device found"}), 400

        sp.start_playback(
            device_id=active_device["id"], uris=[f"spotify:track:{track['id']}"]
        )

        return jsonify({"message": "Track playing.", "track": track})
    except Exception as e:
        current_app.logger.error(f"Error in /api/play: {e}")
        return jsonify({"error": str(e)}), 500

@bp.route("/api/pause", methods=["POST"])
def api_pause():
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
    state = game_state.get_state()
    return jsonify({"played_tracks": state.get("played_tracks", [])})
