"""
Standardized Error Handling Module

This module provides consistent error handling and response formatting
for the Musical Bingo application. It ensures all API endpoints return
structured, user-friendly error messages with proper HTTP status codes.

Features:
- Standardized error response format
- User-friendly error messages
- Proper HTTP status code mapping
- Consistent error logging
- Security-safe error exposure
- Development vs production error detail levels
"""

from fastapi import HTTPException
from typing import Optional, Dict, Any
import logging
from datetime import datetime, timezone
from app.config import get_config

logger = logging.getLogger("music_bingo")
config = get_config()


class StandardError:
    """Standard error response format for all API endpoints."""

    def __init__(
        self,
        status_code: int,
        error_type: str,
        message: str,
        details: Optional[str] = None,
        internal_code: Optional[str] = None
    ):
        self.status_code = status_code
        self.error_type = error_type
        self.message = message
        self.details = details
        self.internal_code = internal_code
        self.timestamp = datetime.now(timezone.utc).isoformat()


class ErrorResponse:
    """Factory for creating standardized error responses."""

    @staticmethod
    def bad_request(message: str, details: Optional[str] = None, internal_code: Optional[str] = None) -> HTTPException:
        """400 Bad Request - Client error."""
        error = StandardError(400, "bad_request", message, details, internal_code)
        return HTTPException(
            status_code=400,
            detail={
                "error": error.error_type,
                "message": error.message,
                "details": error.details,
                "internal_code": error.internal_code,
                "timestamp": error.timestamp
            }
        )

    @staticmethod
    def unauthorized(message: str = "Authentication required", details: Optional[str] = None) -> HTTPException:
        """401 Unauthorized - Authentication error."""
        error = StandardError(401, "unauthorized", message, details)
        return HTTPException(
            status_code=401,
            detail={
                "error": error.error_type,
                "message": error.message,
                "details": error.details,
                "timestamp": error.timestamp
            }
        )

    @staticmethod
    def forbidden(message: str = "Access denied", details: Optional[str] = None) -> HTTPException:
        """403 Forbidden - Permission error."""
        error = StandardError(403, "forbidden", message, details)
        return HTTPException(
            status_code=403,
            detail={
                "error": error.error_type,
                "message": error.message,
                "details": error.details,
                "timestamp": error.timestamp
            }
        )

    @staticmethod
    def not_found(resource: str, identifier: Optional[str] = None) -> HTTPException:
        """404 Not Found - Resource not found."""
        message = f"{resource} not found"
        if identifier:
            message += f": {identifier}"

        error = StandardError(404, "not_found", message)
        return HTTPException(
            status_code=404,
            detail={
                "error": error.error_type,
                "message": error.message,
                "resource": resource,
                "identifier": identifier,
                "timestamp": error.timestamp
            }
        )

    @staticmethod
    def conflict(message: str, details: Optional[str] = None) -> HTTPException:
        """409 Conflict - Resource conflict."""
        error = StandardError(409, "conflict", message, details)
        return HTTPException(
            status_code=409,
            detail={
                "error": error.error_type,
                "message": error.message,
                "details": error.details,
                "timestamp": error.timestamp
            }
        )

    @staticmethod
    def unprocessable_entity(message: str, validation_errors: Optional[Dict[str, Any]] = None) -> HTTPException:
        """422 Unprocessable Entity - Validation error."""
        error = StandardError(422, "validation_error", message)
        return HTTPException(
            status_code=422,
            detail={
                "error": error.error_type,
                "message": error.message,
                "validation_errors": validation_errors,
                "timestamp": error.timestamp
            }
        )

    @staticmethod
    def rate_limit_exceeded(message: str = "Rate limit exceeded", retry_after: Optional[int] = None) -> HTTPException:
        """429 Too Many Requests - Rate limit exceeded."""
        error = StandardError(429, "rate_limit_exceeded", message)
        headers = {}
        if retry_after:
            headers["Retry-After"] = str(retry_after)

        return HTTPException(
            status_code=429,
            detail={
                "error": error.error_type,
                "message": error.message,
                "retry_after": retry_after,
                "timestamp": error.timestamp
            },
            headers=headers
        )

    @staticmethod
    def internal_server_error(
        message: str = "Internal server error",
        error: Optional[Exception] = None,
        operation: Optional[str] = None
    ) -> HTTPException:
        """500 Internal Server Error - Server error."""

        # Log the full error details for debugging
        if error:
            logger.error(
                f"Internal server error during {operation or 'operation'}: {str(error)}",
                exc_info=True
            )

        # In production, don't expose internal error details
        details = None
        if config.environment == "development" and error:
            details = str(error)

        error_obj = StandardError(500, "internal_server_error", message, details)
        return HTTPException(
            status_code=500,
            detail={
                "error": error_obj.error_type,
                "message": error_obj.message,
                "details": error_obj.details,
                "timestamp": error_obj.timestamp
            }
        )

    @staticmethod
    def service_unavailable(message: str = "Service temporarily unavailable") -> HTTPException:
        """503 Service Unavailable - Service down."""
        error = StandardError(503, "service_unavailable", message)
        return HTTPException(
            status_code=503,
            detail={
                "error": error.error_type,
                "message": error.message,
                "timestamp": error.timestamp
            }
        )


def handle_service_error(service_error, operation: str, fallback_message: str) -> HTTPException:
    """
    Handle service-specific errors and convert them to standard HTTP exceptions.

    Args:
        service_error: The service-specific error (e.g., GameError, PlaylistError)
        operation: Description of the operation being performed
        fallback_message: Default error message if service error handling fails

    Returns:
        HTTPException: Standardized HTTP exception
    """
    try:
        # Check if it's a service error with status_code and message attributes
        if hasattr(service_error, 'status_code') and hasattr(service_error, 'message'):
            status_code = service_error.status_code
            message = service_error.message

            # Map status codes to appropriate error responses
            if status_code == 400:
                return ErrorResponse.bad_request(message, internal_code=getattr(service_error, 'code', None))
            elif status_code == 401:
                return ErrorResponse.unauthorized(message)
            elif status_code == 403:
                return ErrorResponse.forbidden(message)
            elif status_code == 404:
                # Extract resource type from message if possible
                resource = "Resource"
                if "game" in message.lower():
                    resource = "Game"
                elif "playlist" in message.lower():
                    resource = "Playlist"
                elif "card" in message.lower():
                    resource = "Bingo card"
                elif "user" in message.lower():
                    resource = "User"

                return ErrorResponse.not_found(resource)
            elif status_code == 409:
                return ErrorResponse.conflict(message)
            elif status_code == 422:
                return ErrorResponse.unprocessable_entity(message)
            else:
                return ErrorResponse.internal_server_error(message, service_error, operation)
        else:
            # Generic exception handling
            return ErrorResponse.internal_server_error(fallback_message, service_error, operation)

    except Exception as e:
        # Fallback if error handling itself fails
        logger.error(f"Error in handle_service_error: {e}", exc_info=True)
        return ErrorResponse.internal_server_error(fallback_message, e, operation)


# Common error message templates
class ErrorMessages:
    """Common error messages for consistency."""

    # Authentication & Authorization
    INVALID_TOKEN = "Invalid or expired authentication token"
    MISSING_TOKEN = "Authentication token required"
    INSUFFICIENT_PERMISSIONS = "Insufficient permissions for this action"

    # Resource Not Found
    GAME_NOT_FOUND = "Game not found"
    PLAYLIST_NOT_FOUND = "Playlist not found"
    CARD_NOT_FOUND = "Bingo card not found"
    USER_NOT_FOUND = "User not found"
    DEVICE_NOT_FOUND = "Spotify device not found"

    # Validation Errors
    INVALID_GAME_DATA = "Invalid game configuration"
    INVALID_PLAYLIST_ID = "Invalid playlist ID format"
    INVALID_ROOM_CODE = "Invalid room code format"
    INSUFFICIENT_TRACKS = "Playlist must have at least 25 tracks for bingo games"

    # Game State Errors
    GAME_ALREADY_STARTED = "Game has already started"
    GAME_NOT_STARTED = "Game has not started yet"
    GAME_FULL = "Game is full and cannot accept more players"
    ALREADY_JOINED = "You have already joined this game"
    NOT_HOST = "Only the game host can perform this action"

    # Service Errors
    SPOTIFY_API_ERROR = "Spotify service is temporarily unavailable"
    DATABASE_ERROR = "Database service is temporarily unavailable"
    REDIS_ERROR = "Session service is temporarily unavailable"

    # Rate Limiting
    RATE_LIMIT_DEFAULT = "Too many requests. Please try again later"
    RATE_LIMIT_AUTH = "Too many authentication attempts. Please try again later"

    # Generic Errors
    INTERNAL_ERROR = "An unexpected error occurred"
    SERVICE_UNAVAILABLE = "Service is temporarily unavailable"
    INVALID_REQUEST = "Invalid request format"
