from flask import Blueprint, jsonify, request, current_app
from app.spotify import get_spotify_client, refresh_spotify_token, load_playlist_tracks
from app.state import game_state, load_playlists, save_playlists
import random
from app.helpers import handle_error

bp = Blueprint("playlist", __name__)

@bp.route("/api/get_playlists", methods=["GET"])
def api_get_playlists():
    """Get list of saved playlists."""
    try:
        playlists = load_playlists()
        return jsonify({
            "playlists": playlists,
            "total": len(playlists),
            "default": next((p for p in playlists if p.get("is_default")), None),
        })
    except Exception as e:
        return handle_error(e)

@bp.route("/api/add_playlist", methods=["POST"])
def api_add_playlist():
    """Add a new playlist to saved playlists."""
    try:
        data = request.json
        playlist_id = data.get("playlist_id")
        is_default = data.get("is_default", False)
        if not playlist_id:
            return jsonify({"error": "No playlist ID provided"}), 400
        sp = get_spotify_client()
        refresh_spotify_token()
        playlist_info = sp.playlist(playlist_id, fields="name,id,owner")
        playlists = load_playlists()
        if any(p["id"] == playlist_id for p in playlists):
            return jsonify({"error": "Playlist already exists"}), 400
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
        return jsonify({"message": "Playlist added successfully", "playlist": new_playlist})
    except Exception as e:
        return handle_error(e)

@bp.route("/api/remove_playlist", methods=["POST"])
def api_remove_playlist():
    """Remove a playlist from saved playlists."""
    try:
        data = request.json
        playlist_id = data.get("playlist_id")
        if not playlist_id:
            return jsonify({"error": "No playlist ID provided"}), 400
        playlists = load_playlists()
        playlists = [p for p in playlists if p["id"] != playlist_id]
        save_playlists(playlists)
        return jsonify({"message": "Playlist removed successfully"})
    except Exception as e:
        return handle_error(e)

@bp.route("/api/load_playlist", methods=["POST"])
def api_load_playlist():
    """Load tracks from a playlist into the game state."""
    try:
        data = request.json
        playlist_id = data.get("playlist_id")
        if not playlist_id:
            return jsonify({"error": "No playlist_id provided"}), 400
        sp = get_spotify_client()
        refresh_spotify_token()
        tracks = load_playlist_tracks(sp, playlist_id)
        if not tracks:
            return jsonify({"error": "No tracks found in playlist"}), 400
        def update_game_state(state):
            state["unplayed_tracks"] = random.sample(tracks, min(100, len(tracks)))
            state["played_tracks"] = []
            state["cards"] = {}
            state["current_playlist"] = playlist_id
            state["num_tracks"] = len(state["unplayed_tracks"])
        game_state.update_state(update_game_state)
        updated_state = game_state.get_state()
        return jsonify({
            "message": f"Loaded {len(tracks)} tracks from playlist, selected {updated_state['num_tracks']} for the game",
            "tracks_available": len(tracks),
            "tracks_loaded": updated_state["num_tracks"],
        })
    except Exception as e:
        return handle_error(e)

@bp.route("/api/set_default_playlist", methods=["POST"])
def api_set_default_playlist():
    """Set a playlist as the default."""
    try:
        data = request.json
        playlist_id = data.get("playlist_id")
        if not playlist_id:
            return jsonify({"error": "No playlist ID provided"}), 400
        playlists = load_playlists()
        found = False
        for playlist in playlists:
            if playlist["id"] == playlist_id:
                playlist["is_default"] = True
                found = True
            else:
                playlist["is_default"] = False
        if not found:
            return jsonify({"error": "Playlist not found"}), 404
        save_playlists(playlists)
        return jsonify({"message": "Default playlist updated successfully"})
    except Exception as e:
        return handle_error(e)
