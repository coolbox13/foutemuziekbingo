from flask import jsonify, current_app

def handle_error(e, status=500):
    current_app.logger.error(f"Error: {e}")
    return jsonify({"error": str(e)}), status
