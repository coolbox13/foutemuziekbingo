# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

Start the application:
```bash
python app.py
```

The Flask server runs on http://localhost:1313 with debug mode enabled.

Install dependencies:
```bash
pip install -r requirements.txt
```

## Required Environment Variables

Set these environment variables before running:
```bash
export SPOTIFY_CLIENT_ID="your_client_id"
export SPOTIFY_CLIENT_SECRET="your_client_secret"
export SPOTIFY_REDIRECT_URI="http://localhost:1313/auth/callback"
export SECRET_KEY="your_secret_key"  # Optional, fallback provided
```

## Application Architecture

This is a Flask-based web application for musical bingo using Spotify integration. Key architectural components:

### Core Structure
- **app.py**: Entry point that creates the Flask app and starts SocketIO server
- **app/__init__.py**: Application factory pattern with blueprint registration
- **app/state.py**: Thread-safe singleton for game state management using JSON persistence

### Blueprint Organization
Routes are organized into focused blueprints registered in `app/routes.py`:
- `auth_routes`: Spotify OAuth authentication
- `playlist_routes`: Spotify playlist management
- `card_routes`: Bingo card generation and PDF export
- `device_routes`: Spotify device selection
- `playback_routes`: Music playback control
- `game_routes`: Game state and logic
- `sound_routes`: Sound effect management
- `dashboard_routes`: Main dashboard interface

### State Management
The application uses a thread-safe singleton pattern (`ThreadSafeGameState`) that:
- Persists state to `game_state.json`
- Provides atomic updates with file synchronization
- Maintains separation between played/unplayed tracks and bingo cards

### Real-time Communication
- **Flask-SocketIO**: WebSocket communication for real-time updates
- **app/socket_handler.py**: Central socket event handling
- Events include: card validation, track playing, bingo checking, game state updates

### Key Business Logic
- **Bingo card generation**: Creates 5x5 grids from playlist tracks (minimum 25 tracks)
- **Bingo validation**: Checks rows, columns, and potentially diagonals
- **Track management**: Maintains played/unplayed track queues
- **Multi-card support**: Handles multiple simultaneous bingo cards

### File Structure
- **static/js/**: Frontend JavaScript (dashboard.js, game_management.js, sound_player.js)
- **templates/**: HTML templates (primarily dashboard.html)
- **sounds/**: Audio files for game effects
- **logs/**: Application and audit logging with rotation
- **saved_games/**: JSON snapshots of game states

### External Integrations
- **Spotify Web API**: Playlist access, track playback, device control
- **ReportLab**: PDF generation for printable bingo cards
- **spotipy**: Python Spotify client library

The application follows a modular design with clear separation of concerns between authentication, game logic, real-time communication, and external service integration.