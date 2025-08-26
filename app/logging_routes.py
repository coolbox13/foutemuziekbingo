"""
Frontend Logging Routes Module

This module handles frontend error logging to ensure all client-side JavaScript
errors and console messages are captured in the server application logs.
"""

from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
import logging
from typing import Optional, Dict, Any

router = APIRouter()
logger = logging.getLogger("music_bingo")


class FrontendLogEntry(BaseModel):
    """Pydantic model for frontend log entries."""
    level: str  # error, warn, info, debug
    message: str
    context: Optional[str] = None
    type: Optional[str] = None
    status: Optional[int] = None
    url: Optional[str] = None
    user_agent: Optional[str] = None
    stack: Optional[str] = None
    timestamp: Optional[str] = None
    is_auth_error: Optional[bool] = False
    is_network_error: Optional[bool] = False
    additional_data: Optional[Dict[str, Any]] = None


@router.post("/api/frontend-log")
async def log_frontend_error(log_entry: FrontendLogEntry, request: Request):
    """
    Receive frontend JavaScript errors and log them to server logs.
    
    This endpoint allows the frontend error handler to send JavaScript errors,
    console messages, and other client-side logs to the server application logs
    for centralized debugging and monitoring.
    """
    try:
        # Get client IP for context
        client_ip = request.client.host if request.client else "unknown"
        
        # Build structured log message
        log_message = f"[FRONTEND-{log_entry.level.upper()}] {log_entry.message}"
        
        # Add context to the log message if provided
        if log_entry.context:
            log_message = f"[FRONTEND-{log_entry.level.upper()}] [{log_entry.context}] {log_entry.message}"
        
        # Prepare extra data for structured logging
        extra_data = {
            "frontend_log": True,
            "client_ip": client_ip,
            "log_level": log_entry.level,
            "context": log_entry.context,
            "type": log_entry.type,
            "url": log_entry.url,
            "user_agent": log_entry.user_agent,
            "timestamp": log_entry.timestamp,
            "is_auth_error": log_entry.is_auth_error,
            "is_network_error": log_entry.is_network_error
        }
        
        # Add HTTP status if provided
        if log_entry.status:
            extra_data["status_code"] = log_entry.status
            
        # Add additional data if provided
        if log_entry.additional_data:
            extra_data.update(log_entry.additional_data)
        
        # Log at appropriate level based on frontend level
        if log_entry.level.lower() == "error":
            logger.error(log_message, extra=extra_data)
            # Also log stack trace if provided
            if log_entry.stack:
                logger.error(f"[FRONTEND-STACK] {log_entry.stack}", extra=extra_data)
        elif log_entry.level.lower() == "warn":
            logger.warning(log_message, extra=extra_data)
        elif log_entry.level.lower() == "info":
            logger.info(log_message, extra=extra_data)
        elif log_entry.level.lower() == "debug":
            logger.debug(log_message, extra=extra_data)
        else:
            # Default to info level for unknown levels
            logger.info(log_message, extra=extra_data)
        
        return {"status": "logged", "message": "Frontend log entry recorded successfully"}
        
    except Exception as e:
        logger.error(f"[FRONTEND-LOG-ERROR] Failed to process frontend log entry: {e}")
        raise HTTPException(status_code=500, detail="Failed to process log entry")


@router.post("/api/frontend-batch-log")
async def log_frontend_batch(log_entries: list[FrontendLogEntry], request: Request):
    """
    Receive multiple frontend log entries in a single batch request.
    
    This is useful for reducing server requests when logging multiple errors
    or when sending queued log entries.
    """
    try:
        client_ip = request.client.host if request.client else "unknown"
        success_count = 0
        error_count = 0
        
        for entry in log_entries:
            try:
                # Process each entry individually
                log_message = f"[FRONTEND-{entry.level.upper()}] {entry.message}"
                
                if entry.context:
                    log_message = f"[FRONTEND-{entry.level.upper()}] [{entry.context}] {entry.message}"
                
                extra_data = {
                    "frontend_log": True,
                    "client_ip": client_ip,
                    "log_level": entry.level,
                    "context": entry.context,
                    "type": entry.type,
                    "url": entry.url,
                    "user_agent": entry.user_agent,
                    "timestamp": entry.timestamp,
                    "is_auth_error": entry.is_auth_error,
                    "is_network_error": entry.is_network_error,
                    "batch_entry": True
                }
                
                if entry.status:
                    extra_data["status_code"] = entry.status
                    
                if entry.additional_data:
                    extra_data.update(entry.additional_data)
                
                # Log based on level
                if entry.level.lower() == "error":
                    logger.error(log_message, extra=extra_data)
                    if entry.stack:
                        logger.error(f"[FRONTEND-STACK] {entry.stack}", extra=extra_data)
                elif entry.level.lower() == "warn":
                    logger.warning(log_message, extra=extra_data)
                elif entry.level.lower() == "info":
                    logger.info(log_message, extra=extra_data)
                elif entry.level.lower() == "debug":
                    logger.debug(log_message, extra=extra_data)
                else:
                    logger.info(log_message, extra=extra_data)
                
                success_count += 1
                
            except Exception as e:
                logger.error(f"[FRONTEND-BATCH-ERROR] Failed to process batch entry: {e}")
                error_count += 1
        
        logger.info(
            f"[FRONTEND-BATCH] Processed {len(log_entries)} log entries: {success_count} successful, {error_count} failed",
            extra={"client_ip": client_ip, "total": len(log_entries), "success": success_count, "errors": error_count}
        )
        
        return {
            "status": "processed",
            "total": len(log_entries),
            "successful": success_count,
            "errors": error_count
        }
        
    except Exception as e:
        logger.error(f"[FRONTEND-BATCH-ERROR] Failed to process frontend batch log: {e}")
        raise HTTPException(status_code=500, detail="Failed to process batch log entries")