from fastapi import APIRouter

router = APIRouter()

# TODO: Convert Flask routes to FastAPI
@router.get("/")
async def playlist_home():
    return {"message": "Playlist routes - TODO: migrate from Flask"}