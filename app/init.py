from flask import Flask
from flask_cors import CORS
from flask_socketio import SocketIO
from dotenv import load_dotenv
import os
import logging
from logging.handlers import RotatingFileHandler

# Create SocketIO instance without app yet
socketio = SocketIO()


def create_app():
    load_dotenv()

    app = Flask(__name__, static_folder="../static", template_folder="../templates")
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "fallback_secret_key")
    CORS(app)

    # Configure logging
    if not app.debug:
        if not os.path.exists("logs"):
            os.mkdir("logs")
        file_handler = RotatingFileHandler(
            "logs/music_bingo.log", maxBytes=10240, backupCount=10
        )
        file_handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]"
            )
        )
        file_handler.setLevel(logging.INFO)
        app.logger.addHandler(file_handler)
        app.logger.setLevel(logging.INFO)
        app.logger.info("Music Bingo startup")

    from app.routes_bak import bp as routes_bp

    app.register_blueprint(routes_bp)

    # Initialize SocketIO with the app
    socketio.init_app(app, cors_allowed_origins="*", logger=True, engineio_logger=True)

    return app
