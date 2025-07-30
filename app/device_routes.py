from fastapi import APIRouter, HTTPException, Request, Depends
from app.spotify import get_spotify_client, get_available_devices
from app.auth_service import get_current_user
from app.models import User
import logging

router = APIRouter()
logger = logging.getLogger("music_bingo")


@router.get("/api/get_devices")
async def api_get_devices(
    request: Request,
    current_user: User = Depends(get_current_user)
):
    try:
        logger.info("[DEVICE-DEBUG-001] Starting get_devices endpoint")
        
        sp = await get_spotify_client(request)
        logger.info("[DEVICE-DEBUG-002] Spotify client obtained", extra={
            "client_type": type(sp).__name__
        })
        
        devices = get_available_devices(sp)
        logger.info("[DEVICE-DEBUG-003] Devices retrieved", extra={
            "device_count": len(devices) if devices else 0
        })
        
        return {"devices": devices}
    except Exception as e:
        logger.error("[DEVICE-DEBUG-ERROR] Exception in get_devices", extra={
            "error": str(e),
            "error_type": type(e).__name__
        })
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/select_device")
async def api_select_device(request: Request):
    data = await request.json()
    device_id = data.get("device_id")
    if not device_id:
        raise HTTPException(status_code=400, detail="No device ID provided")
    try:
        sp = await get_spotify_client(request)
        sp.transfer_playback(device_id=device_id)
        return {"message": "Device selected successfully"}
    except Exception as e:
        logger.error(f"Error selecting device: {e}")
        raise HTTPException(status_code=500, detail=str(e))
