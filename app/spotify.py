import os
from spotipy import Spotify
from spotipy.oauth2 import SpotifyOAuth
from flask import Blueprint, session, current_app, redirect, jsonify

bp = Blueprint("spotify", __name__)


def get_spotify_oauth():
    """Initialize SpotifyOAuth."""
    return SpotifyOAuth(
        client_id=os.getenv("SPOTIFY_CLIENT_ID"),
        client_secret=os.getenv("SPOTIFY_CLIENT_SECRET"),
        redirect_uri=os.getenv("SPOTIFY_REDIRECT_URI", "http://localhost:1313/callback"),
        scope="playlist-read-private user-read-playback-state user-modify-playback-state user-read-currently-playing",
    )


def get_spotify_client():
    """Fetch Spotify client with access token."""
    token_info = session.get("token_info")
    if not token_info:
        raise Exception("Spotify authentication required. Please log in again.")
    refresh_spotify_token()
    return Spotify(auth=session["token_info"]["access_token"])


def refresh_spotify_token():
    """Refresh Spotify token if expired."""
    if "token_info" not in session:
        raise Exception("No token information found in session.")

    sp_oauth = get_spotify_oauth()  # Ensure the `get_spotify_oauth` function is defined

    token_info = session["token_info"]
    if sp_oauth.is_token_expired(token_info):
        try:
            token_info = sp_oauth.refresh_access_token(token_info["refresh_token"])
            session["token_info"] = token_info
        except Exception as e:
            current_app.logger.error(f"Error refreshing token: {e}")
            raise Exception("Failed to refresh Spotify token. Please log in again.")



def get_available_devices(sp):
    """Retrieve available devices from Spotify."""
    try:
        devices_info = sp.devices()
        return devices_info.get("devices", [])
    except Exception as e:
        current_app.logger.error(f"Error getting devices: {e}")
        raise Exception("Failed to get Spotify devices. Please try again.")


def load_playlist_tracks(sp, playlist_id):
    """Load tracks from a Spotify playlist."""
    try:
        results = sp.playlist_items(playlist_id)
        tracks = []
        while results:
            tracks.extend(
                {
                    "id": track["track"]["id"],
                    "name": track["track"]["name"],
                    "artist": ", ".join(a["name"] for a in track["track"]["artists"]),
                }
                for track in results.get("items", []) if track["track"]
            )
            results = sp.next(results)  # Handle pagination
        return tracks
    except Exception as e:
        current_app.logger.error(f"Error loading playlist: {e}")
        raise Exception("Failed to load playlist tracks. Please try again.")


def play_random_track(sp):
    """Play a random track."""
    try:
        devices = sp.devices()
        active_device = next((d for d in devices["devices"] if d["is_active"]), None)

        if not active_device:
            raise Exception(
                "No active Spotify device found. Please ensure a Spotify client is active."
            )

        return active_device
    except Exception as e:
        current_app.logger.error(f"Error in play_random_track: {e}")
        raise Exception("Failed to play track. Please try again.")


def pause_playback(sp):
    """Pause Spotify playback."""
    try:
        sp.pause_playback()
    except Exception as e:
        current_app.logger.error(f"Error pausing playback: {e}")
        raise Exception("Failed to pause playback. Please try again.")


@bp.route("/login")
def login():
    try:
        sp_oauth = get_spotify_oauth()
        current_app.logger.info("SpotifyOAuth initialized")
        auth_url = sp_oauth.get_authorize_url()
        current_app.logger.info(f"Auth URL generated: {auth_url}")
        return redirect(auth_url)
    except Exception as e:
        current_app.logger.error(f"Login error: {e}")
        return jsonify({"error": f"Error: {e}"}), 500
