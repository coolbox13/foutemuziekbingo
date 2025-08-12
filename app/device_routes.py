from fastapi import APIRouter, HTTPException, Request, Depends
from app.spotify import get_spotify_client, get_available_devices
from app.spotify_utils import convert_spotify_exception_to_http, SpotifyAPIError
from app.auth_service import get_current_user
from app.models import User
import logging

router = APIRouter()
logger = logging.getLogger("music_bingo")


@router.get("/api/get_devices")
async def api_get_devices(
    request: Request, current_user: User = Depends(get_current_user)
):
    try:
        logger.info(
            "[DEVICE-API-001] Getting devices for user",
            extra={"user_id": current_user.id},
        )

        sp = await get_spotify_client(request)
        devices = await get_available_devices(sp)

        logger.info(
            "[DEVICE-API-002] Devices retrieved successfully",
            extra={
                "device_count": len(devices) if devices else 0,
                "active_devices": len([d for d in devices if d.get("is_active")])
                if devices
                else 0,
            },
        )

        return {"devices": devices}

    except HTTPException:
        # Re-raise HTTPExceptions from auth or client creation
        raise
    except SpotifyAPIError as e:
        raise convert_spotify_exception_to_http(e, "get devices")
    except Exception as e:
        logger.error(
            "[DEVICE-API-ERROR] Unexpected error getting devices",
            extra={
                "user_id": current_user.id,
                "error": str(e),
                "error_type": type(e).__name__,
            },
        )
        raise HTTPException(
            status_code=500, detail="Unable to retrieve devices. Please try again."
        )


@router.post("/api/select_device")
async def api_select_device(
    request: Request, current_user: User = Depends(get_current_user)
):
    try:
        data = await request.json()
        device_id = data.get("device_id")

        if not device_id:
            raise HTTPException(status_code=400, detail="Device ID is required")

        logger.info(
            "[DEVICE-SELECT-001] Selecting device",
            extra={"device_id": device_id, "user_id": current_user.id},
        )

        sp = await get_spotify_client(request)

        # Use retry mechanism for device transfer
        from app.spotify_utils import spotify_api_call_with_retry

        await spotify_api_call_with_retry(
            lambda: sp.transfer_playback(device_id=device_id, force_play=False),
            operation_name="select device",
        )

        # Invalidate device cache since we changed the active device
        from app.spotify_utils import invalidate_device_cache

        invalidate_device_cache()

        logger.info(
            "[DEVICE-SELECT-002] Device selected successfully",
            extra={"device_id": device_id, "user_id": current_user.id},
        )

        return {"message": "Device selected successfully"}

    except HTTPException:
        # Re-raise HTTPExceptions (validation errors, auth errors)
        raise
    except SpotifyAPIError as e:
        raise convert_spotify_exception_to_http(e, "select device")
    except Exception as e:
        logger.error(
            "[DEVICE-SELECT-ERROR] Unexpected error selecting device",
            extra={
                "error": str(e),
                "device_id": device_id if "device_id" in locals() else "unknown",
                "user_id": current_user.id,
                "error_type": type(e).__name__,
            },
        )
        raise HTTPException(
            status_code=500, detail="Unable to select device. Please try again."
        )
