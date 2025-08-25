import uvicorn
import os
import logging
from dotenv import load_dotenv
from app.fastapi_app import create_app
from app.socket_handler import sio
import socketio

# Load .env before building the app stack
load_dotenv(dotenv_path=os.path.join(os.getcwd(), ".env"), override=False)

# Create FastAPI app
fastapi_app = create_app()

# Create combined app with Socket.IO
app = socketio.ASGIApp(sio, other_asgi_app=fastapi_app)

# Initialize logger for startup logging
logger = logging.getLogger("music_bingo")

# Log all registered routes for debugging (properly logged now)
logger.info("Registered routes:")
for route in fastapi_app.routes:
    if hasattr(route, "methods"):
        logger.info(f"  {route.methods}: {route.path}")
    else:
        logger.info(f"  Route: {route}")

if __name__ == "__main__":
    # Configure uvicorn logging to integrate with application logging
    log_config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "format": "%(asctime)s [%(process)d] [%(levelname)s] %(name)s: %(message)s [%(pathname)s:%(lineno)d]",
            },
        },
        "handlers": {
            "default": {
                "formatter": "default",
                "class": "logging.handlers.RotatingFileHandler",
                "filename": "logs/music_bingo.log",
                "maxBytes": 50 * 1024 * 1024,  # 50MB
                "backupCount": 10,
            },
            "console": {
                "formatter": "default",
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stdout",
            },
        },
        "root": {
            "level": "INFO",
            "handlers": ["default", "console"],
        },
        "loggers": {
            "uvicorn": {
                "level": "INFO",
                "handlers": ["default", "console"],
                "propagate": False,
            },
            "uvicorn.error": {
                "level": "INFO",
                "handlers": ["default", "console"],
                "propagate": False,
            },
            "uvicorn.access": {
                "level": "INFO",
                "handlers": ["default", "console"],
                "propagate": False,
            },
            "music_bingo": {
                "level": "INFO",
                "handlers": ["default", "console"],
                "propagate": False,
            },
        },
    }

    logger.info("Starting Music Bingo server on 0.0.0.0:1313")
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=1313,
        reload=False,
        log_config=log_config,
        access_log=True
    )
