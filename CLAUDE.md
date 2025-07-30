# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

Start the application:
```bash
python app.py
```

The FastAPI server runs on http://localhost:1313.

Install dependencies (using conda environment 'base'):
```bash
conda activate base
pip install -r requirements.txt
```

Check linters and syntax (using Python 3.11 in conda base environment):
```bash
python3.11 -m py_compile app.py
python3.11 app.py
flake8 app/*.py --max-line-length=100
```

Note: User prefers conda environment 'base' with zsh shell. Uses Python 3.11 with FastAPI packages installed.

## Required Environment Variables

Set these environment variables before running:
```bash
export SPOTIFY_CLIENT_ID="your_client_id"
export SPOTIFY_CLIENT_SECRET="your_client_secret"
export SPOTIFY_REDIRECT_URI="http://localhost:1313/auth/callback"
export SECRET_KEY="your_secret_key"  # Optional, fallback provided
export SUPABASE_URL="your_supabase_url" 
export SUPABASE_SERVICE_KEY="your_supabase_service_key"
export JWT_SECRET="your_jwt_secret"
```

Run tests:
```bash
conda activate base
pip install pyjwt  # Required for tests
python3 tests/run_all_tests.py
```

## Application Architecture

This is a FastAPI-based web application for musical bingo using Spotify integration. Key architectural components:

### Core Structure
- **app.py**: Entry point that creates the FastAPI app and starts Socket.IO server
- **app/fastapi_app.py**: FastAPI application factory
- **app/state.py**: Thread-safe singleton for game state management using JSON persistence

### Router Organization
Routes are organized into focused routers registered in `app/routes.py`:
- `auth_routes`: Spotify OAuth authentication
- `playlist_routes`: Spotify playlist management
- `card_routes`: Bingo card generation and PDF export
- `device_routes`: Spotify device selection
- `playback_routes`: Music playback control
- `game_routes`: Game state and logic
- `game_management`: Save/load game functionality
- `sound_routes`: Sound effect management
- `dashboard_routes`: Main dashboard interface

### State Management
The application uses a thread-safe singleton pattern (`ThreadSafeGameState`) that:
- Persists state to `game_state.json`
- Provides atomic updates with file synchronization
- Maintains separation between played/unplayed tracks and bingo cards

### Real-time Communication
- **python-socketio**: Async WebSocket communication for real-time updates
- **app/socket_handler.py**: Central async socket event handling
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