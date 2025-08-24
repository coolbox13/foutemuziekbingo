from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from app.auth_service import get_current_user_optional
from app.models import User
import os
import mimetypes
import logging
from typing import Optional

router = APIRouter()
logger = logging.getLogger("music_bingo")

# Get the absolute path to the sounds directory
SOUNDS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "sounds"))

# Ensure proper MIME type registration
mimetypes.add_type("audio/mpeg", ".mp3")
mimetypes.add_type("audio/wav", ".wav")
mimetypes.add_type("audio/ogg", ".ogg")


@router.get("/api/list_sounds")
async def list_sounds(request: Request, current_user: Optional[User] = None):
    """List all available sound files with their MIME types - public access with optional auth tracking."""
    # Optional authentication for tracking but not required
    if not current_user:
        try:
            current_user = await get_current_user_optional(request)
        except:
            current_user = None

    try:
        # Log access (authenticated vs anonymous)
        if current_user:
            logger.info(
                f"[SOUND-AUTH-001] Authenticated user {current_user.id} listing sounds",
                extra={"user_id": current_user.id, "access_type": "authenticated"}
            )
        else:
            logger.info(
                "[SOUND-PUBLIC-001] Anonymous user listing sounds",
                extra={"client_ip": request.client.host, "access_type": "anonymous"}
            )

        # Ensure the sounds directory exists
        if not os.path.exists(SOUNDS_DIR):
            logger.error(f"Sounds directory not found: {SOUNDS_DIR}")
            raise HTTPException(status_code=500, detail="Sounds directory not found")

        sounds = []
        for filename in os.listdir(SOUNDS_DIR):
            if filename.lower().endswith((".mp3", ".wav", ".ogg")):
                mime_type = mimetypes.guess_type(filename)[0]
                sounds.append({"filename": filename, "mime_type": mime_type})

        logger.info(
            f"[SOUND-LIST-002] Found {len(sounds)} sound files",
            extra={
                "user_id": current_user.id if current_user else "anonymous",
                "sound_count": len(sounds),
                "access_type": "authenticated" if current_user else "anonymous"
            }
        )

        return {"sounds": sorted(sounds, key=lambda x: x["filename"])}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "[SOUND-LIST-ERROR] Error listing sounds",
            extra={
                "user_id": current_user.id if current_user else "anonymous",
                "error": str(e),
                "access_type": "authenticated" if current_user else "anonymous"
            }
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/sounds/{filename}")
async def serve_sound(filename: str, request: Request, current_user: Optional[User] = None):
    """Serve a sound file with proper MIME type - public access with optional auth tracking."""
    # Optional authentication for tracking but not required
    if not current_user:
        try:
            current_user = await get_current_user_optional(request)
        except:
            current_user = None

    try:
        # Log access (authenticated vs anonymous)
        if current_user:
            logger.info(
                f"[SOUND-AUTH-003] Authenticated user {current_user.id} requesting sound: {filename}",
                extra={"user_id": current_user.id, "sound_filename": filename, "access_type": "authenticated"}
            )
        else:
            logger.info(
                f"[SOUND-PUBLIC-002] Anonymous user requesting sound: {filename}",
                extra={"client_ip": request.client.host, "sound_filename": filename, "access_type": "anonymous"}
            )

        if not os.path.exists(SOUNDS_DIR):
            logger.error(f"Sounds directory not found: {SOUNDS_DIR}")
            raise HTTPException(status_code=500, detail="Sounds directory not found")

        # Check if file exists
        file_path = os.path.join(SOUNDS_DIR, filename)
        if not os.path.exists(file_path):
            logger.warning(
                f"[SOUND-SERVE-404] Sound file not found: {filename}",
                extra={
                    "user_id": current_user.id if current_user else "anonymous",
                    "sound_filename": filename,
                    "file_path": file_path,
                    "access_type": "authenticated" if current_user else "anonymous"
                }
            )
            raise HTTPException(status_code=404, detail="Sound file not found")

        mime_type = mimetypes.guess_type(filename)[0]

        logger.info(
            "[SOUND-SERVE-004] Serving sound file successfully",
            extra={
                "user_id": current_user.id if current_user else "anonymous",
                "sound_filename": filename,
                "mime_type": mime_type,
                "access_type": "authenticated" if current_user else "anonymous"
            }
        )

        return FileResponse(
            path=file_path,
            media_type=mime_type or "application/octet-stream",
            filename=filename,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"[SOUND-SERVE-ERROR] Error serving sound file {filename}",
            extra={
                "user_id": current_user.id if current_user else "anonymous",
                "sound_filename": filename,
                "error": str(e),
                "access_type": "authenticated" if current_user else "anonymous"
            }
        )
        raise HTTPException(status_code=500, detail=str(e))
