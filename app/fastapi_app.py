from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv
import os
import logging
import asyncio
from logging.handlers import RotatingFileHandler
from app.routes import register_routes
from app.database import database
from datetime import datetime, timezone


def create_app():
    """Create and configure the FastAPI application."""
    # Load environment variables from .env at project root
    load_dotenv(dotenv_path=os.path.join(os.getcwd(), ".env"), override=False)

    app = FastAPI(title="Foute Muziek Bingo")

    # Add CORS middleware with restricted origins
    allowed_origins_env = os.getenv("ALLOWED_ORIGINS", "http://localhost:1313")
    allowed_origins = [o.strip() for o in allowed_origins_env.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Mount static files
    app.mount("/static", StaticFiles(directory="static"), name="static")

    # Configure Jinja2 templates
    templates = Jinja2Templates(directory="templates")

    # Configure logging
    if not os.path.exists("logs"):
        os.makedirs("logs")

    file_handler = RotatingFileHandler(
        "logs/music_bingo.log", maxBytes=10240, backupCount=10
    )
    file_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s: %(message)s " "[in %(pathname)s:%(lineno)d]"
        )
    )
    file_handler.setLevel(logging.INFO)

    logger = logging.getLogger("music_bingo")
    logger.addHandler(file_handler)
    logger.setLevel(logging.INFO)
    logger.info("Music Bingo startup")

    # Initialize database connection
    @app.on_event("startup")
    async def startup_event():
        """Initialize database connection on startup"""
        logger.info("Initializing database connection...")
        try:
            await database.initialize()
            logger.info("Database connection initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            if os.getenv("NODE_ENV") != "development":
                raise

        # Start background token maintenance task
        async def _token_maintenance_loop():
            from app.secure_session import (
                get_sessions_snapshot,
                update_session_token_info,
            )
            from app.spotify import get_spotify_oauth
            from app.spotify_utils import SpotifyAPIError
            from app.auth_routes import SECRET_KEY
            from app.secure_session import SESSION_COOKIE_NAME
            from spotipy.oauth2 import SpotifyOAuth
            import time

            sp_oauth: SpotifyOAuth = get_spotify_oauth()
            check_interval = int(os.getenv("SPOTIFY_TOKEN_MAINTENANCE_INTERVAL", "60"))
            safety_window = int(os.getenv("SPOTIFY_TOKEN_SAFETY_WINDOW", "180"))

            while True:
                try:
                    snapshot = get_sessions_snapshot()
                    now_epoch = time.time()
                    for token, data in snapshot.items():
                        token_info = data.get("token_info") or {}
                        refresh_token = token_info.get("refresh_token")
                        expires_at = token_info.get("expires_at")
                        if not refresh_token:
                            continue
                        needs_refresh = False
                        try:
                            needs_refresh = (not expires_at) or (
                                now_epoch > float(expires_at) - safety_window
                            )
                        except Exception:
                            needs_refresh = True
                        if not needs_refresh:
                            continue
                        try:
                            refreshed = sp_oauth.refresh_access_token(refresh_token)
                            update_session_token_info(token, refreshed)
                            logger.info("[SPOTIFY-MAINT] Proactive refresh successful")
                        except Exception as e:
                            logger.warning(
                                f"[SPOTIFY-MAINT] Proactive refresh failed: {e}"
                            )
                except Exception as loop_err:
                    logger.warning(
                        f"[SPOTIFY-MAINT] Maintenance loop error: {loop_err}"
                    )
                finally:
                    await asyncio.sleep(check_interval)

        try:
            asyncio.create_task(_token_maintenance_loop())
            logger.info("[SPOTIFY-MAINT] Token maintenance task started")
        except Exception as e:
            logger.warning(f"[SPOTIFY-MAINT] Failed to start maintenance task: {e}")

    @app.on_event("shutdown")
    async def shutdown_event():
        """Cleanup on shutdown"""
        logger.info("Application shutting down...")

    # Register all routes
    register_routes(app)

    # Add root route
    @app.get("/", response_class=HTMLResponse)
    async def root(request: Request):
        # Prefer secure session
        try:
            from app.secure_session import get_session_from_request
            from app.auth_routes import SECRET_KEY

            session_data = get_session_from_request(request, SECRET_KEY)
            if session_data and session_data.get("user"):
                return RedirectResponse(url="/dashboard", status_code=302)
        except Exception:
            pass
        return templates.TemplateResponse("homepage.html", {"request": request})

    # Socket.IO will be mounted separately in app.py

    return app
