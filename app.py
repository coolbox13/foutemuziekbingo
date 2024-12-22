import os
import json
import uuid
import random
from flask import Flask, request, session, redirect, url_for, jsonify, render_template
from spotipy import Spotify
from spotipy.oauth2 import SpotifyOAuth
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "fallback_secret_key")

SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
SPOTIFY_REDIRECT_URI = os.getenv("SPOTIFY_REDIRECT_URI", "http://localhost:1313/callback")
SCOPES = "playlist-read-private user-read-playback-state user-modify-playback-state"

# Bingo memory
CARDS = {}           # { card_id: [ {id, name, artist} ... ] }
UNPLAYED_TRACKS = [] # pool for random draws
PLAYED_TRACKS = []   # chronological list of played this round

# Store known playlists in a JSON file
PLAYLISTS_FILE = "playlists.json"
PLAYLISTS = []  # loaded on startup

def load_playlists():
    """Load playlists from local JSON file, or create default if not present."""
    global PLAYLISTS
    if not Path(PLAYLISTS_FILE).exists():
        default_data = [
            {"id": "spotify:playlist:37i9dQZF1DXcBWIGoYBM5M", "name": "Pop Example", "is_default": True},
            {"id": "spotify:playlist:37i9dQZF1DX4W3aJJYCDfV", "name": "Rock Example", "is_default": False}
        ]
        with open(PLAYLISTS_FILE, "w", encoding="utf-8") as f:
            json.dump(default_data, f, indent=2)
        PLAYLISTS = default_data
    else:
        with open(PLAYLISTS_FILE, "r", encoding="utf-8") as f:
            PLAYLISTS = json.load(f)

def save_playlists():
    """Save current PLAYLISTS to the JSON file."""
    with open(PLAYLISTS_FILE, "w", encoding="utf-8") as f:
        json.dump(PLAYLISTS, f, indent=2)

load_playlists()

def get_spotify_client():
    token_info = session.get("token_info")
    if not token_info:
        return None
    return Spotify(auth=token_info["access_token"])

def refresh_spotify_token():
    if "token_info" in session:
        sp_oauth = SpotifyOAuth(
            client_id=SPOTIFY_CLIENT_ID,
            client_secret=SPOTIFY_CLIENT_SECRET,
            redirect_uri=SPOTIFY_REDIRECT_URI,
            scope=SCOPES
        )
        if sp_oauth.is_token_expired(session["token_info"]):
            new_token = sp_oauth.refresh_access_token(session["token_info"]["refresh_token"])
            session["token_info"] = new_token

@app.route("/")
def home():
    if "token_info" in session:
        return redirect(url_for("dashboard"))
    return "<h1>Welcome to Foute Muziek Bingo</h1><p><a href='/login'>Login with Spotify</a></p>"

@app.route("/login")
def login():
    sp_oauth = SpotifyOAuth(
        client_id=SPOTIFY_CLIENT_ID,
        client_secret=SPOTIFY_CLIENT_SECRET,
        redirect_uri=SPOTIFY_REDIRECT_URI,
        scope=SCOPES
    )
    return redirect(sp_oauth.get_authorize_url())

@app.route("/callback")
def callback():
    code = request.args.get("code")
    error = request.args.get("error")

    if error:
        return f"Spotify auth error: {error}"
    if code:
        sp_oauth = SpotifyOAuth(
            client_id=SPOTIFY_CLIENT_ID,
            client_secret=SPOTIFY_CLIENT_SECRET,
            redirect_uri=SPOTIFY_REDIRECT_URI,
            scope=SCOPES
        )
        token_info = sp_oauth.get_access_token(code)
        session["token_info"] = token_info
        return redirect(url_for("dashboard"))
    return "No code found"

@app.route("/dashboard")
def dashboard():
    if "token_info" not in session:
        return redirect(url_for("login"))
    return render_template("dashboard.html")

# ---------- Playlist Management ---------- #

@app.route("/api/get_playlists", methods=["GET"])
def api_get_playlists():
    """Return known playlists from playlists.json."""
    return jsonify({"playlists": PLAYLISTS})

@app.route("/api/add_playlist", methods=["POST"])
def api_add_playlist():
    """
    Add a new playlist to the JSON. 
    { "id": "spotify:playlist:xxx", "name": "New PL", "is_default": false }
    """
    data = request.json
    if not data or "id" not in data or "name" not in data:
        return jsonify({"error": "Playlist 'id' and 'name' required."}), 400

    # optional "is_default" key
    new_pl = {
        "id": data["id"],
        "name": data["name"],
        "is_default": data.get("is_default", False)
    }
    # if is_default is True, reset others to false
    if new_pl["is_default"]:
        for pl in PLAYLISTS:
            pl["is_default"] = False

    PLAYLISTS.append(new_pl)
    save_playlists()
    return jsonify({"message": f"Playlist '{new_pl['name']}' added."})

# ---------- Selecting/Loading a Playlist ---------- #

@app.route("/api/select_playlist", methods=["POST"])
def api_select_playlist():
    """Load the tracks from the chosen playlist into UNPLAYED_TRACKS, reset PLAYED_TRACKS."""
    sp = get_spotify_client()
    if not sp:
        return jsonify({"error": "Not logged in"}), 401
    refresh_spotify_token()

    data = request.json
    playlist_id = data.get("playlist_id")
    if not playlist_id:
        return jsonify({"error": "No playlist_id provided."}), 400

    # fetch from Spotify
    try:
        results = sp.playlist_items(playlist_id, additional_types=["track"])
    except Exception as e:
        return jsonify({"error": f"Could not fetch playlist: {str(e)}"}), 400

    tracks = []
    for item in results["items"]:
        t = item["track"]
        if t:
            tracks.append({
                "id": t["id"],
                "name": t["name"],
                "artist": ", ".join(a["name"] for a in t["artists"])
            })

    global UNPLAYED_TRACKS, PLAYED_TRACKS
    UNPLAYED_TRACKS = tracks[:]
    PLAYED_TRACKS = []

    return jsonify({
        "message": f"Loaded {len(tracks)} tracks from {playlist_id}.",
        "track_count": len(tracks)
    })

@app.route("/api/new_round", methods=["POST"])
def api_new_round():
    """
    Reset the current round: clear PLAYED_TRACKS, 
    restore all known tracks to UNPLAYED_TRACKS (like a fresh start).
    """
    global PLAYED_TRACKS, UNPLAYED_TRACKS
    if not UNPLAYED_TRACKS and not PLAYED_TRACKS:
        return jsonify({"error": "No playlist loaded yet; please select a playlist first."}), 400

    # If UNPLAYED_TRACKS is zero but we do have PLAYED_TRACKS, we can unify them:
    UNPLAYED_TRACKS += PLAYED_TRACKS
    PLAYED_TRACKS = []
    return jsonify({"message": "New round started. Played tracks reset."})

# ---------- Devices ---------- #

@app.route("/api/get_devices", methods=["GET"])
def api_get_devices():
    sp = get_spotify_client()
    if not sp:
        return jsonify({"error": "Not logged in"}), 401
    refresh_spotify_token()

    try:
        devices_info = sp.devices()
        return jsonify(devices_info)
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route("/api/select_device", methods=["POST"])
def api_select_device():
    data = request.json
    device_id = data.get("device_id")
    if not device_id:
        return jsonify({"error": "No device_id provided."}), 400
    session["device_id"] = device_id
    return jsonify({"message": f"Device set to {device_id}"})

# ---------- Bingo Card Generation ---------- #

@app.route("/api/generate_cards", methods=["POST"])
def api_generate_cards():
    data = request.json
    num_cards = int(data.get("num_cards", 2))
    # We use UNPLAYED_TRACKS as the track pool for building cards
    if len(UNPLAYED_TRACKS) < 25:
        return jsonify({"error": "Not enough unplayed tracks to form a 5x5 card."}), 400

    global CARDS
    new_cards = []
    for _ in range(num_cards):
        card_id = str(uuid.uuid4())[:8]
        sample_25 = random.sample(UNPLAYED_TRACKS, 25)
        CARDS[card_id] = sample_25
        new_cards.append(card_id)

    return jsonify({
        "message": f"Generated {num_cards} Bingo card(s).",
        "cards": new_cards
    })

@app.route("/api/get_cards", methods=["GET"])
def api_get_cards():
    return jsonify({"cards": CARDS})

@app.route("/api/check_bingo/<card_id>", methods=["GET"])
def api_check_bingo(card_id):
    if card_id not in CARDS:
        return jsonify({"error": "Invalid card ID"}), 404
    card_tracks = CARDS[card_id]
    card_ids = [t["id"] for t in card_tracks]
    played_ids = [t["id"] for t in PLAYED_TRACKS]
    matched_count = sum(1 for cid in card_ids if cid in played_ids)
    is_bingo = (matched_count >= 5)
    return jsonify({
        "card_id": card_id,
        "matched_count": matched_count,
        "is_bingo": is_bingo
    })

# ---------- Playback Controls ---------- #
@app.route("/api/playback/<action>", methods=["POST"])
def api_playback_action(action):
    """
    We map:
    - 'play' => pick a random track from UNPLAYED_TRACKS if not empty, and start playback
    - 'pause' => sp.pause_playback
    - 'next' => pick another random track from UNPLAYED_TRACKS
    """
    sp = get_spotify_client()
    if not sp:
        return jsonify({"error": "Not logged in"}), 401
    refresh_spotify_token()

    device_id = session.get("device_id")

    # Helper to start a random track
    def play_random():
        nonlocal sp, device_id
        if not UNPLAYED_TRACKS:
            raise Exception("No unplayed tracks left or no playlist loaded.")
        chosen = random.choice(UNPLAYED_TRACKS)
        UNPLAYED_TRACKS.remove(chosen)
        PLAYED_TRACKS.append(chosen)
        if device_id:
            sp.start_playback(device_id=device_id, uris=[f"spotify:track:{chosen['id']}"])
        else:
            sp.start_playback(uris=[f"spotify:track:{chosen['id']}"])
        return chosen

    try:
        if action == "play":
            # pick a random track and play
            chosen = play_random()
            return jsonify({"message": "Random track played", "track": chosen})
        elif action == "pause":
            # just pause
            if device_id:
                sp.pause_playback(device_id=device_id)
            else:
                sp.pause_playback()
            return jsonify({"message": "Playback paused"})
        elif action == "next":
            # pick another random track
            chosen = play_random()
            return jsonify({"message": "Next random track played", "track": chosen})
        else:
            return jsonify({"error": f"Unknown action '{action}'"}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 400

# ---------- Misc API ---------- #
@app.route("/api/played_tracks", methods=["GET"])
def api_played_tracks():
    return jsonify({"played_tracks": PLAYED_TRACKS})

@app.route("/api/get_unplayed_count", methods=["GET"])
def api_get_unplayed_count():
    return jsonify({"unplayed_count": len(UNPLAYED_TRACKS)})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=1313, debug=True)
