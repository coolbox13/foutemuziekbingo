from fastapi import APIRouter

router = APIRouter()

@router.get("/")
async def card_routes_home():
    return {"message": "card_routes - TODO: migrate from Flask"}
