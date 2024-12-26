#!/usr/bin/env python3
import os
import sys
import webbrowser

from spotipy import Spotify
from spotipy.oauth2 import SpotifyOAuth, SpotifyOauthError

# If you have a .env with SPOTIFY_CLIENT_ID etc., you can do:
from dotenv import load_dotenv

load_dotenv()

SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID", "YOUR_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET", "YOUR_CLIENT_SECRET")
SPOTIFY_REDIRECT_URI = os.getenv(
    "SPOTIFY_REDIRECT_URI", "http://localhost:8888/callback"
)
SCOPE = "user-read-playback-state"

CACHE_PATH = ".cache-checkdevices"


def main():
    if (
        SPOTIFY_CLIENT_ID == "YOUR_CLIENT_ID"
        or SPOTIFY_CLIENT_SECRET == "YOUR_CLIENT_SECRET"
    ):
        print("⚠️  Please set SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET.")
        sys.exit(1)

    # Create a SpotifyOAuth object
    sp_oauth = SpotifyOAuth(
        client_id=SPOTIFY_CLIENT_ID,
        client_secret=SPOTIFY_CLIENT_SECRET,
        redirect_uri=SPOTIFY_REDIRECT_URI,
        scope=SCOPE,
        cache_path=CACHE_PATH,
        show_dialog=False,  # or True if you want to force re-auth
    )

    # Attempt to read a cached token
    token_info = sp_oauth.get_cached_token()

    if token_info:
        # token_info should be a dict with "access_token" if it's the older version of Spotipy,
        # or a string in future versions. Let's handle both.
        if isinstance(token_info, dict):
            access_token = token_info["access_token"]
        else:
            # Spotipy might just return the token string
            access_token = token_info
    else:
        # No cached token => start the auth flow
        auth_url = sp_oauth.get_authorize_url()
        print("Opening browser for Spotify authorization...")
        webbrowser.open(auth_url)

        print(
            "After approving, you'll be redirected. Copy the entire redirect URL and paste it below."
        )
        response_url = input("Paste the URL here: ").strip()

        # Parse out the code
        code = sp_oauth.parse_response_code(response_url)
        if not code:
            print("Error: no code found in redirect URL. Exiting.")
            sys.exit(1)

        # get_access_token() might return just the token or a dict
        try:
            new_token = sp_oauth.get_access_token(code)
        except SpotifyOauthError as e:
            print(f"Error retrieving access token: {e}")
            sys.exit(1)

        if isinstance(new_token, dict):
            access_token = new_token["access_token"]
        else:
            access_token = new_token

    if not access_token:
        print("No valid access token. Exiting.")
        sys.exit(1)

    # Now we can create a Spotipy client with the access token
    sp = Spotify(auth=access_token)

    # Retrieve devices via GET /v1/me/player/devices
    try:
        devices_data = sp.devices()
    except Exception as e:
        print(f"Failed to get devices: {e}")
        sys.exit(1)

    devices = devices_data.get("devices", [])

    if not devices:
        print("No active or available Spotify devices found.")
    else:
        print(f"Found {len(devices)} device(s):")
        for d in devices:
            print("--------------------------------------------------")
            print(f"Name:               {d.get('name')}")
            print(f"Device ID:          {d.get('id')}")
            print(f"Active:             {d.get('is_active')}")
            print(f"Restricted:         {d.get('is_restricted')}")
            print(f"Type:               {d.get('type')}")
            print(f"Volume Percent:     {d.get('volume_percent')}")
            # The new field "supports_volume" might not appear for older devices
            if "supports_volume" in d:
                print(f"Supports Volume:    {d['supports_volume']}")
            else:
                print("Supports Volume:    (not provided)")
    print("\nDone.")


if __name__ == "__main__":
    main()
