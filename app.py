from app import create_app, socketio
import app.socket_events  # This is important to register the event handlers

app = create_app()

# Print all registered routes for debugging
with app.app_context():
    for rule in app.url_map.iter_rules():
        print(f"{rule.endpoint}: {rule.rule}")

if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=1313, debug=True)
