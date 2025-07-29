from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from spotipy.oauth2 import SpotifyOAuth
import os
import logging

router = APIRouter()
logger = logging.getLogger("music_bingo")

# Simple session storage (in production, use proper session management)
sessions = {}

@router.get("/login")
async def login(request: Request):
    sp_oauth = SpotifyOAuth(
        client_id=os.getenv("SPOTIFY_CLIENT_ID"),
        client_secret=os.getenv("SPOTIFY_CLIENT_SECRET"),
        redirect_uri=os.getenv(
            "SPOTIFY_REDIRECT_URI", "http://localhost:1313/auth/callback"
        ),
        scope="playlist-read-private user-read-playback-state user-modify-playback-state user-read-currently-playing",
    )
    auth_url = sp_oauth.get_authorize_url()
    logger.info(f"Spotify OAuth URL: {auth_url}")
    return RedirectResponse(url=auth_url, status_code=302)

@router.get("/callback")
async def callback(request: Request, code: str = None, error: str = None):
    client_ip = request.client.host
    
    if error:
        logger.error(f"Spotify auth error: {error}")
        raise HTTPException(status_code=400, detail=f"Spotify Authentication Failed: {error}")

    if code:
        sp_oauth = SpotifyOAuth(
            client_id=os.getenv("SPOTIFY_CLIENT_ID"),
            client_secret=os.getenv("SPOTIFY_CLIENT_SECRET"),
            redirect_uri=os.getenv(
                "SPOTIFY_REDIRECT_URI", "http://localhost:1313/auth/callback"
            ),
            scope="playlist-read-private user-read-playback-state user-modify-playback-state user-read-currently-playing",
        )
        try:
            token_info = sp_oauth.get_access_token(code)
            if client_ip not in sessions:
                sessions[client_ip] = {}
            sessions[client_ip]["token_info"] = token_info
            logger.info("Spotify token acquired successfully")
            return RedirectResponse(url="/dashboard", status_code=302)
        except Exception as e:
            logger.error(f"Error processing Spotify callback: {e}")
            raise HTTPException(
                status_code=500,
                detail="Something went wrong during Spotify authentication. Please try again."
            )

    raise HTTPException(status_code=400, detail="No code found in callback URL.")
