from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from dotenv import load_dotenv
import os
import logging
from logging.handlers import RotatingFileHandler
from app.routes import register_routes
from app.socket_handler import sio_app
import socketio

def create_app():
    """Create and configure the FastAPI application."""
    load_dotenv()

    app = FastAPI(title="Foute Muziek Bingo")
    
    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Mount static files
    app.mount("/static", StaticFiles(directory="static"), name="static")
    
    # Configure logging
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
    
    logger = logging.getLogger("music_bingo")
    logger.addHandler(file_handler)
    logger.setLevel(logging.INFO)
    logger.info("Music Bingo startup")

    # Register all routes
    register_routes(app)
    
    # Add root route
    @app.get("/", response_class=HTMLResponse)
    async def root(request: Request):
        client_ip = request.client.host
        from app.auth_routes import sessions
        if client_ip in sessions and "token_info" in sessions[client_ip]:
            return RedirectResponse(url="/dashboard", status_code=302)
        return """
        <h1>Welcome to Foute Muziek Bingo</h1>
        <p><a href='/auth/login'>Login with Spotify</a></p>
        """
    
    # Socket.IO will be mounted separately in app.py

    return app