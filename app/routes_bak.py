from flask import (
    Blueprint,
    jsonify,
    request,
    render_template,
    session,
    redirect,
    url_for,
    current_app,
    send_file,
)
from app.spotify import (
    get_spotify_client,
    refresh_spotify_token,
    get_available_devices,
    load_playlist_tracks,
    play_random_track,
    pause_playback,
)
from app.state import (
    ThreadSafeGameState,
    load_playlists,
    save_playlists,
    reset_game_state,
)
from app.utils import generate_bingo_cards, check_bingo_status
import random
import os
import uuid
from spotipy.oauth2 import SpotifyOAuth
from io import BytesIO
from flask_socketio import emit

bp = Blueprint("routes", __name__)
game_state = ThreadSafeGameState()

@bp.before_request
def log_request_info():
    current_app.logger.info("Headers: %s", request.headers)
    current_app.logger.info("Body: %s", request.get_data())

# --- Home and Authentication Routes ---
@bp.route("/")
def home():
    if "token_info" in session:
        return redirect(url_for("routes.dashboard"))
    return "<h1>Welcome to Foute Muziek Bingo</h1><p><a href='/login'>Login with Spotify</a></p>"

@bp.route("/login")
def login():
    sp_oauth = SpotifyOAuth(
        client_id=os.getenv("SPOTIFY_CLIENT_ID"),
        client_secret=os.getenv("SPOTIFY_CLIENT_SECRET"),
        redirect_uri=os.getenv(
            "SPOTIFY_REDIRECT_URI", "http://localhost:1313/callback"
        ),
        scope="playlist-read-private user-read-playback-state user-modify-playback-state user-read-currently-playing",
    )
    return redirect(sp_oauth.get_authorize_url())

@bp.route("/callback")
def callback():
    code = request.args.get("code")
    error = request.args.get("error")

    if error:
        return f"Spotify auth error: {error}", 400
    if code:
        sp_oauth = SpotifyOAuth(
            client_id=os.getenv("SPOTIFY_CLIENT_ID"),
            client_secret=os.getenv("SPOTIFY_CLIENT_SECRET"),
            redirect_uri=os.getenv(
                "SPOTIFY_REDIRECT_URI", "http://localhost:1313/callback"
            ),
            scope="playlist-read-private user-read-playback-state user-modify-playback-state user-read-currently-playing",
        )
        try:
            token_info = sp_oauth.get_access_token(code)
            session["token_info"] = token_info
            return redirect(url_for("routes.dashboard"))
        except Exception as e:
            return f"Error processing Spotify callback: {e}", 500

    return "No code found in callback", 400

@bp.route("/dashboard")
def dashboard():
    # Ensure game state is properly initialized
    state = game_state.get_state()
    if not state.get("num_tracks"):
        state["num_tracks"] = len(state.get("unplayed_tracks", []))

    return render_template(
        "dashboard.html",
        game_state={
            "num_tracks": state.get("num_tracks", 0),
            "cards": state.get("cards", {}),
            "bingo_mode": state.get("bingo_mode", "default"),
        },
    )

# --- Playlist Management ---
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

# --- Device Management ---
@bp.route("/api/get_devices", methods=["GET"])
def api_get_devices():
    try:
        sp = get_spotify_client()
        refresh_spotify_token()
        devices = get_available_devices(sp)
        return jsonify({"devices": devices})
    except Exception as e:
        current_app.logger.error(f"Error getting devices: {e}")
        return jsonify({"error": str(e)}), 500

@bp.route("/api/select_device", methods=["POST"])
def api_select_device():
    data = request.json
    device_id = data.get("device_id")
    if not device_id:
        return jsonify({"error": "No device ID provided"}), 400

    try:
        sp = get_spotify_client()
        refresh_spotify_token()
        sp.transfer_playback(device_id=device_id)
        return jsonify({"message": "Device selected successfully"})
    except Exception as e:
        current_app.logger.error(f"Error selecting device: {e}")
        return jsonify({"error": str(e)}), 500

# --- Card Management ---
@bp.route("/api/generate_cards", methods=["POST"])
def api_generate_cards():
    data = request.json
    num_cards = int(data.get("num_cards", 2))

    state = game_state.get_state()
    if len(state.get("unplayed_tracks", [])) < 25:
        return jsonify({"error": "Not enough unplayed tracks to generate cards."}), 400

    def create_cards(state):
        state["cards"] = {}
        for _ in range(num_cards):
            card_id = str(uuid.uuid4())[:8]
            state["cards"][card_id] = {
                "tracks": random.sample(state["unplayed_tracks"], 25),
                "bingo_status": "Not checked",
            }
        return state["cards"]

    new_cards = game_state.update_state(create_cards)
    return jsonify(
        {"message": f"Generated {num_cards} Bingo card(s).", "cards": new_cards}
    )

@bp.route("/api/get_cards", methods=["GET"])
def api_get_cards():
    state = game_state.get_state()
    return jsonify({"cards": state.get("cards", {})})

@bp.route("/api/check_card/<card_id>", methods=["GET"])
def check_card(card_id):
    state = game_state.get_state()
    if card_id not in state.get("cards", {}):
        return jsonify({"error": "Invalid card ID"}), 404

    card = state["cards"][card_id]
    has_bingo = check_bingo_status(card, state.get("played_tracks", []))

    def update_card_status(state):
        state["cards"][card_id]["bingo_status"] = "BINGO!" if has_bingo else "No bingo"

    game_state.update_state(update_card_status)

    if has_bingo:
        emit("bingo_winner", {"card_id": card_id}, broadcast=True)

    return jsonify(
        {
            "card_id": card_id,
            "has_bingo": has_bingo,
            "status": "BINGO!" if has_bingo else "No bingo",
        }
    )

# --- Playback Control ---
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

        from app import socketio

        socketio.emit("new_track", track, namespace="/")

        return jsonify({"message": "Playing track", "track": track})
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

@bp.route("/api/new_round", methods=["POST"])
def api_new_round():
    try:
        reset_game_state()
        return jsonify({"message": "New round started"})
    except Exception as e:
        current_app.logger.error(f"Error starting new round: {e}")
        return jsonify({"error": str(e)}), 500

@bp.route("/api/download_cards_pdf", methods=["GET"])
def api_download_cards_pdf():
    try:
        from app.pdf_generator import BingoCardPDF

        state = game_state.get_state()
        cards = state.get("cards", {})

        if not cards:
            return jsonify({"error": "No cards available"}), 404

        pdf_generator = BingoCardPDF(cards)
        pdf_data = pdf_generator.generate()

        return send_file(
            BytesIO(pdf_data),
            mimetype="application/pdf",
            as_attachment=True,
            download_name="bingo_cards.pdf",
        )
    except Exception as e:
        current_app.logger.error(f"PDF generation error: {str(e)}")
        return jsonify({"error": "Failed to generate PDF", "details": str(e)}), 500

@bp.route("/api/validate_card", methods=["POST"])
def validate_card():
    data = request.json
    card_id = data.get("card_id")
    track_id = data.get("track_id")
    position = data.get("position")

    state = game_state.get_state()
    if card_id not in state.get("cards", {}):
        return jsonify({"error": "Invalid card ID"}), 404

    card = state["cards"][card_id]
    played_tracks = state.get("played_tracks", [])

    card_track = card["tracks"][position]
    if card_track["id"] != track_id:
        return jsonify({"valid": False, "message": "Track doesn't match position"}), 400

    if not any(t["id"] == track_id for t in played_tracks):
        return jsonify({"valid": False, "message": "Track hasn't been played yet"}), 400

    def update_card(state):
        if "matches" not in state["cards"][card_id]:
            state["cards"][card_id]["matches"] = []
        if position not in state["cards"][card_id]["matches"]:
            state["cards"][card_id]["matches"].append(position)

    game_state.update_state(update_card)

    has_bingo = check_bingo_status(card, played_tracks)
    if has_bingo:
        from app import socketio
        socketio.emit("bingo_winner", {"card_id": card_id}, namespace="/")

    return jsonify(
        {
            "valid": True,
            "has_bingo": has_bingo,
            "matches": game_state.get_state()["cards"][card_id]["matches"],
        }
    )
