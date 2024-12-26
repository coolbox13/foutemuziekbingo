from flask import Blueprint, jsonify, request, current_app
from app.spotify import get_spotify_client, refresh_spotify_token, get_available_devices

bp = Blueprint("device", __name__)

@bp.route("/api/get_devices", methods=["GET"])
def api_get_devices():
    try:
        sp = get_spotify_client()
        refresh_spotify_token()  # Ensure token is valid
        devices = get_available_devices(sp)
        return jsonify({"devices": devices})
    except Exception as e:
        current_app.logger.error(f"Error getting devices: {e}")
        return jsonify({"error": str(e)}), 401  # Return 401 for authentication errors




@bp.route("/api/select_device", methods=["POST"])
def api_select_device():
    data = request.json
    device_id = data.get("device_id")
    if not device_id:
        return jsonify({"error": "No device ID provided"}), 400

    try:
        sp = get_spotify_client()
        refresh_spotify_token()
        sp.transfer_playback(device_id=device_id)
        return jsonify({"message": "Device selected successfully"})
    except Exception as e:
        current_app.logger.error(f"Error selecting device: {e}")
        return jsonify({"error": str(e)}), 500
