from flask import Blueprint, session, redirect, url_for, request, current_app
from spotipy.oauth2 import SpotifyOAuth
import os

bp = Blueprint("auth", __name__)

@bp.route("/")
def home():
    if "token_info" in session:
        return redirect(url_for("dashboard.dashboard"))
    return """
    <h1>Welcome to Foute Muziek Bingo</h1>
    <p><a href='/auth/login'>Login with Spotify</a></p>
    """

@bp.route("/login")
def login():
    sp_oauth = SpotifyOAuth(
        client_id=os.getenv("SPOTIFY_CLIENT_ID"),
        client_secret=os.getenv("SPOTIFY_CLIENT_SECRET"),
        redirect_uri=os.getenv("SPOTIFY_REDIRECT_URI", "http://localhost:1313/auth/callback"),
        scope="playlist-read-private user-read-playback-state user-modify-playback-state user-read-currently-playing",
    )
    auth_url = sp_oauth.get_authorize_url()
    current_app.logger.info(f"Spotify OAuth URL: {auth_url}")
    return redirect(auth_url)

@bp.route("/callback")
def callback():
    code = request.args.get("code")
    error = request.args.get("error")

    if error:
        current_app.logger.error(f"Spotify auth error: {error}")
        return f"<h1>Spotify Authentication Failed</h1><p>Error: {error}</p>", 400

    if code:
        sp_oauth = SpotifyOAuth(
            client_id=os.getenv("SPOTIFY_CLIENT_ID"),
            client_secret=os.getenv("SPOTIFY_CLIENT_SECRET"),
            redirect_uri=os.getenv("SPOTIFY_REDIRECT_URI", "http://localhost:1313/auth/callback"),
            scope="playlist-read-private user-read-playback-state user-modify-playback-state user-read-currently-playing",
        )
        try:
            token_info = sp_oauth.get_access_token(code)
            session["token_info"] = token_info
            current_app.logger.info("Spotify token acquired successfully")
            return redirect(url_for("dashboard.dashboard"))
        except Exception as e:
            current_app.logger.error(f"Error processing Spotify callback: {e}")
            return (
                "<h1>Authentication Error</h1>"
                "<p>Something went wrong during Spotify authentication. Please try again.</p>",
                500,
            )

    return "<h1>Authentication Error</h1><p>No code found in callback URL.</p>", 400
