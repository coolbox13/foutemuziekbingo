from fastapi import APIRouter

router = APIRouter()

@router.get("/")
async def game_management_home():
    return {"message": "game_management - TODO: migrate from Flask"}
