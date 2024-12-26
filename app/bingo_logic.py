from flask import Blueprint, request, jsonify
from app.spotify import get_spotify_client, refresh_spotify_token
from app.utils import generate_bingo_cards
from app.state import game_state  # Import the global game state instance

bp = Blueprint("bingo_logic", __name__)
state = game_state  # Use the existing game state instance


@bp.route("/load_playlist", methods=["POST"])
def load_playlist():
    """Load a Spotify playlist into the game state."""
    try:
        data = request.json
        playlist_id = data.get("playlist_id")
        if not playlist_id:
            return jsonify({"error": "Playlist ID is required."}), 400

        sp = get_spotify_client()
        refresh_spotify_token()
        tracks = sp.playlist_items(playlist_id)["items"]

        state.unplayed_tracks = [
            {
                "id": track["track"]["id"],
                "name": track["track"]["name"],
                "artist": ", ".join(a["name"] for a in track["track"]["artists"]),
            }
            for track in tracks if track["track"]
        ]
        state.num_tracks = len(state.unplayed_tracks)

        return jsonify(
            {"message": "Playlist loaded successfully.", "num_tracks": state.num_tracks}
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/generate_cards", methods=["POST"])
def generate_cards():
    """Generate Bingo cards based on the current state."""
    try:
        data = request.json
        num_cards = int(data.get("num_cards", 1))

        if state.num_tracks < num_cards * 25:
            return jsonify(
                {"error": "Not enough tracks to generate the requested number of cards."}
            ), 400

        cards = generate_bingo_cards(state.unplayed_tracks, num_cards)
        state.cards = cards
        return jsonify({"message": f"{num_cards} cards generated successfully."})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/play_track", methods=["POST"])
def play_track():
    """Play the next track in the queue."""
    try:
        sp = get_spotify_client()
        refresh_spotify_token()

        if not state.unplayed_tracks:
            return jsonify({"error": "No unplayed tracks available."}), 400

        track = state.unplayed_tracks.pop(0)
        sp.start_playback(uris=[f"spotify:track:{track['id']}"])
        return jsonify({"message": "Track playing.", "track": track})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
