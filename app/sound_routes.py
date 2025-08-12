from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
import os
import mimetypes
import logging

router = APIRouter()
logger = logging.getLogger("music_bingo")

# Get the absolute path to the sounds directory
SOUNDS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "sounds"))

# Ensure proper MIME type registration
mimetypes.add_type("audio/mpeg", ".mp3")
mimetypes.add_type("audio/wav", ".wav")
mimetypes.add_type("audio/ogg", ".ogg")


@router.get("/api/list_sounds")
async def list_sounds():
    """List all available sound files with their MIME types."""
    try:
        # Ensure the sounds directory exists
        if not os.path.exists(SOUNDS_DIR):
            logger.error(f"Sounds directory not found: {SOUNDS_DIR}")
            raise HTTPException(status_code=500, detail="Sounds directory not found")

        sounds = []
        for filename in os.listdir(SOUNDS_DIR):
            if filename.lower().endswith((".mp3", ".wav", ".ogg")):
                mime_type = mimetypes.guess_type(filename)[0]
                sounds.append({"filename": filename, "mime_type": mime_type})

        logger.info(f"Found {len(sounds)} sound files in {SOUNDS_DIR}")
        return {"sounds": sorted(sounds, key=lambda x: x["filename"])}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing sounds: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/sounds/{filename}")
async def serve_sound(filename: str):
    """Serve a sound file with proper MIME type."""
    try:
        if not os.path.exists(SOUNDS_DIR):
            logger.error(f"Sounds directory not found: {SOUNDS_DIR}")
            raise HTTPException(status_code=500, detail="Sounds directory not found")

        # Check if file exists
        file_path = os.path.join(SOUNDS_DIR, filename)
        if not os.path.exists(file_path):
            logger.error(f"Sound file not found: {file_path}")
            raise HTTPException(status_code=404, detail="Sound file not found")

        mime_type = mimetypes.guess_type(filename)[0]
        logger.debug(f"Serving sound file: {filename} ({mime_type})")

        return FileResponse(
            path=file_path,
            media_type=mime_type or "application/octet-stream",
            filename=filename,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error serving sound file {filename}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
