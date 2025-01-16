from flask import Blueprint, send_from_directory, jsonify, current_app
import os
import mimetypes

bp = Blueprint("sound", __name__)

# Get the absolute path to the sounds directory
SOUNDS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'sounds'))

# Ensure proper MIME type registration
mimetypes.add_type('audio/mpeg', '.mp3')
mimetypes.add_type('audio/wav', '.wav')
mimetypes.add_type('audio/ogg', '.ogg')

@bp.route("/api/list_sounds", methods=["GET"])
def list_sounds():
    """List all available sound files with their MIME types."""
    try:
        # Ensure the sounds directory exists
        if not os.path.exists(SOUNDS_DIR):
            current_app.logger.error(f"Sounds directory not found: {SOUNDS_DIR}")
            return jsonify({"error": "Sounds directory not found"}), 500

        sounds = []
        for filename in os.listdir(SOUNDS_DIR):
            if filename.lower().endswith(('.mp3', '.wav', '.ogg')):
                mime_type = mimetypes.guess_type(filename)[0]
                sounds.append({
                    'filename': filename,
                    'mime_type': mime_type
                })
        
        current_app.logger.info(f"Found {len(sounds)} sound files in {SOUNDS_DIR}")
        return jsonify({"sounds": sorted(sounds, key=lambda x: x['filename'])})
    except Exception as e:
        current_app.logger.error(f"Error listing sounds: {str(e)}")
        return jsonify({"error": str(e)}), 500

@bp.route("/api/sounds/<filename>")
def serve_sound(filename):
    """Serve a sound file with proper MIME type."""
    try:
        if not os.path.exists(SOUNDS_DIR):
            current_app.logger.error(f"Sounds directory not found: {SOUNDS_DIR}")
            return jsonify({"error": "Sounds directory not found"}), 500

        # Check if file exists
        file_path = os.path.join(SOUNDS_DIR, filename)
        if not os.path.exists(file_path):
            current_app.logger.error(f"Sound file not found: {file_path}")
            return jsonify({"error": "Sound file not found"}), 404

        mime_type = mimetypes.guess_type(filename)[0]
        current_app.logger.debug(f"Serving sound file: {filename} ({mime_type})")
        
        response = send_from_directory(SOUNDS_DIR, filename)
        if mime_type:
            response.headers['Content-Type'] = mime_type
        return response
    except Exception as e:
        current_app.logger.error(f"Error serving sound file {filename}: {str(e)}")
        return jsonify({"error": str(e)}), 500