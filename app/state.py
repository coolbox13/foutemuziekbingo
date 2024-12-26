import json
import os
from threading import Lock

# Paths for storing playlists and game state
PLAYLISTS_FILE = "playlists.json"
GAME_STATE_FILE = "game_state.json"

# Default game state structure
DEFAULT_GAME_STATE = {
    "played_tracks": [],
    "unplayed_tracks": [],
    "cards": {},  # Ensure cards are part of the state
    "bingo_mode": "rowcoldiag",
    "current_playlist": None,
    "num_tracks": 0,
}


class ThreadSafeGameState:
    _instance = None
    _lock = Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, "state_lock"):
            self.state_lock = Lock()
            self.state = self.load_state()

    def load_state(self):
        try:
            with open(GAME_STATE_FILE, "r") as f:
                return json.load(f)
        except FileNotFoundError:
            self.save_state(DEFAULT_GAME_STATE.copy())
            return DEFAULT_GAME_STATE.copy()

    def save_state(self, state):
        with open(GAME_STATE_FILE, "w") as f:
            json.dump(state, f, indent=4)

    def update_state(self, update_func):
        with self.state_lock:
            update_func(self.state)
            self.save_state(self.state)
            return self.state.copy()

    def get_state(self):
        with self.state_lock:
            return self.state.copy()


def load_playlists():
    """Load playlists from the JSON file."""
    if not os.path.exists(PLAYLISTS_FILE):
        return []
    with open(PLAYLISTS_FILE, "r") as f:
        return json.load(f)


def save_playlists(playlists):
    """Save playlists to the JSON file."""
    with open(PLAYLISTS_FILE, "w") as f:
        json.dump(playlists, f, indent=4)


def reset_game_state():
    """Reset the game state to its default."""
    game_state = ThreadSafeGameState()

    def reset(state):
        state.clear()
        state.update(DEFAULT_GAME_STATE.copy())

    game_state.update_state(reset)


# Create the global game state instance
game_state = ThreadSafeGameState()

# For backwards compatibility with existing code
GAME_STATE = game_state.get_state()
UNPLAYED_TRACKS = GAME_STATE["unplayed_tracks"]
PLAYED_TRACKS = GAME_STATE["played_tracks"]
CARDS = GAME_STATE["cards"]
