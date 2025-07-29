from flask import Blueprint, jsonify, request, current_app
from app.spotify import get_spotify_client, refresh_spotify_token, get_available_devices
from app.helpers import handle_error

bp = Blueprint("device", __name__)

@bp.route("/api/get_devices", methods=["GET"])
def api_get_devices():
    try:
        sp = get_spotify_client()
        refresh_spotify_token()
        devices = get_available_devices(sp)
        return jsonify({"devices": devices})
    except Exception as e:
        return handle_error(e)

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
        return handle_error(e)
