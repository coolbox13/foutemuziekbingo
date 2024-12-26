from flask import Blueprint, jsonify, request, current_app
from app.spotify import get_spotify_client, refresh_spotify_token, load_playlist_tracks
from app.state import ThreadSafeGameState, load_playlists, save_playlists
import random

bp = Blueprint("playlist", __name__)
game_state = ThreadSafeGameState()

@bp.route("/api/get_playlists", methods=["GET"])
def api_get_playlists():
    playlists = load_playlists()
    return jsonify({"playlists": playlists})

@bp.route("/api/add_playlist", methods=["POST"])
def api_add_playlist():
    data = request.json
    playlist_id = data.get("playlist_id")
    is_default = data.get("is_default", False)

    if not playlist_id:
        return jsonify({"error": "No playlist ID provided"}), 400

    try:
        playlists = load_playlists()
        new_playlist = {
            "id": playlist_id,
            "name": playlist_id,
            "is_default": is_default,
        }

        if is_default:
            for playlist in playlists:
                playlist["is_default"] = False

        playlists.append(new_playlist)
        save_playlists(playlists)

        return jsonify({"message": "Playlist added successfully"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@bp.route("/api/load_playlist", methods=["POST"])
def api_load_playlist():
    data = request.json
    playlist_id = data.get("playlist_id")
    if not playlist_id:
        return jsonify({"error": "No playlist_id provided."}), 400

    try:
        sp = get_spotify_client()
        refresh_spotify_token()
        tracks = load_playlist_tracks(sp, playlist_id)

        def update_tracks(state):
            state["unplayed_tracks"] = random.sample(
                tracks, min(100, len(tracks))
            )
            state["played_tracks"] = []
            state["cards"] = {}

        game_state.update_state(update_tracks)
        return jsonify(
            {
                "message": f"Loaded {len(tracks)} tracks from playlist, selected {len(game_state.get_state()['unplayed_tracks'])} for the game"
            }
        )
    except Exception as e:
        current_app.logger.error(f"Error loading playlist: {e}")
        return jsonify({"error": str(e)}), 500
