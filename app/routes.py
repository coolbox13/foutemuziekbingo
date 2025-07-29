from fastapi import FastAPI, Request
import logging

logger = logging.getLogger("music_bingo")


async def log_request_info(request: Request):
    """Centralized request logging for all routes."""
    logger.info("Headers: %s", dict(request.headers))
    if request.method in ["POST", "PUT", "PATCH"]:
        body = await request.body()
        logger.info("Body: %s", body.decode() if body else "")


def register_routes(app: FastAPI):
    """Register all routes to the FastAPI application."""
    logger.info("Registering routes.")

    from app.auth_routes import router as auth_router
    from app.dashboard_routes import router as dashboard_router
    from app.playlist_routes import router as playlist_router
    from app.device_routes import router as device_router
    from app.card_routes import router as card_router
    from app.playback_routes import router as playback_router
    from app.game_routes import router as game_router
    from app.game_management import router as game_management_router
    from app.sound_routes import router as sound_router

    # Register all routers with Flask blueprint prefixes to match frontend expectations
    app.include_router(auth_router, prefix="/auth", tags=["auth"])
    app.include_router(dashboard_router, prefix="/dashboard", tags=["dashboard"])
    app.include_router(playlist_router, prefix="/playlist", tags=["playlist"])
    app.include_router(device_router, prefix="/device", tags=["device"])
    app.include_router(card_router, prefix="/card", tags=["card"])
    app.include_router(playback_router, prefix="/playback", tags=["playback"])
    app.include_router(game_router, prefix="/game", tags=["game"])
    app.include_router(game_management_router, prefix="/game_management", tags=["game_management"])
    app.include_router(sound_router, prefix="/sound", tags=["sound"])
