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
    "cards": {},
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
                    cls._instance.__initialized = False
        return cls._instance

    def __init__(self):
        if not getattr(self, "__initialized", False):
            self.state_lock = Lock()
            self.state = self.load_state()
            self.__initialized = True

    def load_state(self):
        """Load game state from file."""
        try:
            with open(GAME_STATE_FILE, "r") as f:
                return json.load(f)
        except FileNotFoundError:
            return self.reset_to_default()

    def save_state(self, state):
        """Save game state to file."""
        with open(GAME_STATE_FILE, "w") as f:
            json.dump(state, f, indent=4)

    def update_state(self, update_func):
        """Thread-safe state update."""
        with self.state_lock:
            update_func(self.state)
            self.save_state(self.state)
            return self.state.copy()

    def get_state(self):
        """Thread-safe state retrieval."""
        with self.state_lock:
            return self.state.copy()

    def reset_to_default(self):
        """Reset state to default values."""
        self.state = DEFAULT_GAME_STATE.copy()
        self.save_state(self.state)
        return self.state


def load_playlists():
    """Load playlists from the JSON file."""
    if not os.path.exists(PLAYLISTS_FILE):
        save_playlists([])
        return []
    with open(PLAYLISTS_FILE, "r") as f:
        return json.load(f)


def save_playlists(playlists):
    """Save playlists to the JSON file."""
    with open(PLAYLISTS_FILE, "w") as f:
        json.dump(playlists, f, indent=4)


# Create the singleton instance
game_state = ThreadSafeGameState()

# Remove these exports as they're no longer needed
# GAME_STATE = game_state.get_state()
# UNPLAYED_TRACKS = GAME_STATE["unplayed_tracks"]
# PLAYED_TRACKS = GAME_STATE["played_tracks"]
# CARDS = GAME_STATE["cards"]
