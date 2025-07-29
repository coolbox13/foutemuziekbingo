from fastapi import APIRouter

router = APIRouter()

@router.get("/")
async def playback_routes_home():
    return {"message": "playback_routes - TODO: migrate from Flask"}
