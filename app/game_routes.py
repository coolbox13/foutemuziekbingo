from fastapi import APIRouter

router = APIRouter()

@router.get("/")
async def game_routes_home():
    return {"message": "game_routes - TODO: migrate from Flask"}
