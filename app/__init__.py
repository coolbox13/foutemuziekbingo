from flask import Flask
from flask_cors import CORS
from flask_socketio import SocketIO
from dotenv import load_dotenv
import os
import logging
from logging.handlers import RotatingFileHandler
from app.routes import register_blueprints  # New import for centralized registration

socketio = SocketIO()


def create_app():
    load_dotenv()
    app = Flask(__name__, static_folder="../static", template_folder="../templates")
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "fallback_secret_key")
    CORS(app)

    if not app.debug:
        if not os.path.exists("logs"):
            os.makedirs("logs")
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
        app.logger.setLevel(logging.DEBUG)
        app.logger.debug("Application started in debug mode.")

    # Register all blueprints via routes.py
    register_blueprints(app)

    socketio.init_app(app, cors_allowed_origins="*")
    return app
