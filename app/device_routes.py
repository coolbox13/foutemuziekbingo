from fastapi import APIRouter, HTTPException, Request
from app.spotify import get_spotify_client, get_available_devices
import logging

router = APIRouter()
logger = logging.getLogger("music_bingo")


@router.get("/api/get_devices")
async def api_get_devices(request: Request):
    try:
        sp = await get_spotify_client(request)
        devices = get_available_devices(sp)
        return {"devices": devices}
    except Exception as e:
        logger.error(f"Error getting devices: {e}")
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
