from fastapi import APIRouter

router = APIRouter()

@router.get("/")
async def sound_routes_home():
    return {"message": "sound_routes - TODO: migrate from Flask"}