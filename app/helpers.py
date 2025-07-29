from fastapi import HTTPException
import logging

logger = logging.getLogger("music_bingo")

def handle_error(e, status=500):
    logger.error(f"Error: {e}")
    raise HTTPException(status_code=status, detail=str(e))
