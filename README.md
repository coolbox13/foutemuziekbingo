```markdown
# Foute Muziek Bingo

A web-based bingo game that uses Spotify tracks to create and manage musical bingo cards.

## Description
Foute Muziek Bingo is a Flask-based web application that allows you to:
- Generate bingo cards from Spotify playlists
- Play tracks through Spotify
- Validate bingo cards in real-time
- Generate PDF versions of bingo cards
- Track game progress with WebSocket updates

## Prerequisites
- Python 3.8 or higher
- Spotify Developer Account
- Spotify Premium Account (for playback features)

## Spotify Developer Setup
1. Go to [Spotify Developer Dashboard](https://developer.spotify.com/dashboard)
2. Create a new application
3. Note down your Client ID and Client Secret
4. Add the following Redirect URI to your app settings:
   - `http://localhost:1313/auth/callback`
   - Or your custom domain if deployed
5. Configure environment variables:
   ```
   export SPOTIFY_CLIENT_ID="your_client_id"
   export SPOTIFY_CLIENT_SECRET="your_client_secret"
   export SPOTIFY_REDIRECT_URI="http://localhost:1313/auth/callback"
   ```

## Installation
1. Clone the repository:
   ```bash
   git clone [repository-url]
   cd FouteMuziekBingo
   ```

2. Create and activate virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Running the Application
1. Start the Flask server:
   ```bash
   export FLASK_DEBUG=1  # Optional: for development
   python app.py
   ```

2. Open your browser and navigate to:
   ```
   http://localhost:1313
   ```

## Features
- **Playlist Management**: Load and manage Spotify playlists
- **Card Generation**: Create bingo cards from playlist tracks
- **Real-time Updates**: WebSocket integration for live game state
- **PDF Export**: Generate printable bingo cards
- **Device Selection**: Choose Spotify playback device
- **Game State Management**: Track played songs and card status

## Game Flow
1. Add a Spotify playlist
2. Generate bingo cards
3. Select a playback device
4. Start playing tracks
5. Players validate their cards
6. System checks for winning patterns (rows, columns)

## Development
The application uses:
- Flask for the backend
- Flask-SocketIO for real-time updates
- ReportLab for PDF generation
- Spotify Web API for music playback
- Tailwind CSS for styling

## Project Structure
```
FouteMuziekBingo/
.
├── README.md
├── app
│   ├── __init__.py
│   ├── auth_routes.py
│   ├── bingo_logic.py
│   ├── card_routes.py
│   ├── card_status.py
│   ├── dashboard_routes.py
│   ├── device_routes.py
│   ├── game_routes.py
│   ├── init.py
│   ├── pdf_generator.py
│   ├── playback_routes.py
│   ├── playlist_routes.py
│   ├── routes.py
│   ├── routes_bak.py
│   ├── socket_events.py
│   ├── spotify.py
│   ├── state.py
│   ├── utils.py
│   └── websocket.py
├── app.py
├── check_devices.py
├── game_state.json
├── logs
│   └── music_bingo.log
├── playlists.json
├── requirements.txt
├── static
│   ├── css
│   ├── js
│   │   └── dashboard.js
│   └── svg
│       └── tree.svg
└── templates
    ├── dashboard.html
    └── pdf_cards.html
```

## Contributing
Feel free to submit issues and pull requests.

## License
This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details
```