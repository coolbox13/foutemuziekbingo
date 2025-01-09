from flask import Blueprint, jsonify, request, current_app
import json
import os
from datetime import datetime
from app.state import game_state

bp = Blueprint("game_management", __name__)

SAVED_GAMES_DIR = "saved_games"

def ensure_saved_games_dir():
    if not os.path.exists(SAVED_GAMES_DIR):
        os.makedirs(SAVED_GAMES_DIR)

@bp.route("/api/save_game", methods=["POST"])
def save_game():
    """Save current game state with a name and description."""
    try:
        data = request.json
        game_name = data.get("name")
        description = data.get("description", "")
        
        if not game_name:
            return jsonify({"error": "Game name is required"}), 400
            
        ensure_saved_games_dir()
        
        current_state = game_state.get_state()
        
        # Add metadata to the state
        save_data = {
            "name": game_name,
            "description": description,
            "timestamp": datetime.now().isoformat(),
            "game_state": current_state
        }
        
        filename = f"{game_name.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        filepath = os.path.join(SAVED_GAMES_DIR, filename)
        
        with open(filepath, 'w') as f:
            json.dump(save_data, f, indent=4)
            
        return jsonify({
            "message": "Game saved successfully",
            "filename": filename
        })
        
    except Exception as e:
        current_app.logger.error(f"Error saving game: {e}")
        return jsonify({"error": str(e)}), 500

@bp.route("/api/load_game/<filename>", methods=["POST"])
def load_game(filename):
    """Load a saved game state."""
    try:
        filepath = os.path.join(SAVED_GAMES_DIR, filename)
        
        if not os.path.exists(filepath):
            return jsonify({"error": "Saved game not found"}), 404
            
        with open(filepath, 'r') as f:
            save_data = json.load(f)
            
        # Update the current game state
        def update_state(state):
            loaded_state = save_data["game_state"]
            state.update(loaded_state)
            
        game_state.update_state(update_state)
        
        return jsonify({
            "message": "Game loaded successfully",
            "game_info": {
                "name": save_data["name"],
                "description": save_data["description"],
                "timestamp": save_data["timestamp"]
            }
        })
        
    except Exception as e:
        current_app.logger.error(f"Error loading game: {e}")
        return jsonify({"error": str(e)}), 500

@bp.route("/api/list_saved_games", methods=["GET"])
def list_saved_games():
    """Get list of all saved games."""
    try:
        ensure_saved_games_dir()
        saved_games = []
        
        for filename in os.listdir(SAVED_GAMES_DIR):
            if filename.endswith('.json'):
                filepath = os.path.join(SAVED_GAMES_DIR, filename)
                with open(filepath, 'r') as f:
                    save_data = json.load(f)
                    saved_games.append({
                        "filename": filename,
                        "name": save_data["name"],
                        "description": save_data["description"],
                        "timestamp": save_data["timestamp"]
                    })
                    
        return jsonify({
            "saved_games": sorted(saved_games, key=lambda x: x["timestamp"], reverse=True)
        })
        
    except Exception as e:
        current_app.logger.error(f"Error listing saved games: {e}")
        return jsonify({"error": str(e)}), 500