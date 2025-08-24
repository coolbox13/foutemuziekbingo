"""
Token Management API Routes

This module provides API endpoints for monitoring and managing
Spotify token health, background service status, and user notifications.

Key Features:
- Token status and health endpoints
- Background service monitoring
- User notification management
- Administrative token management tools
- Health check endpoints for monitoring

Author: Claude Code Assistant
Date: 2025-01-18
Issue: CRIT-003 - Token management API and monitoring routes
"""

from fastapi import APIRouter, Request, HTTPException, Depends
from typing import Optional, List
import logging
from datetime import datetime, timezone
from app.auth_service import get_current_user, get_current_user_optional
from app.models import User, UserPublic, APIResponse
from app.spotify_token_manager import (
    spotify_token_manager,
    get_spotify_client_for_user,
    validate_user_spotify_auth,
    refresh_user_spotify_token
)
from app.background_token_service import (
    background_token_service,
    get_background_service_status,
    get_background_service_health,
    start_background_token_service,
    stop_background_token_service
)
from app.user_notification_service import (
    user_notification_service,
    get_user_notifications
)

router = APIRouter()
logger = logging.getLogger("music_bingo")


@router.get(
    "/spotify/status",
    summary="Check Spotify Authentication Status",
    description="Check current user's Spotify authentication status and token validity",
    tags=["Token Management", "Spotify"],
    responses={
        200: {
            "description": "Spotify authentication status",
            "model": APIResponse
        },
        401: {
            "description": "User not authenticated"
        }
    }
)
async def spotify_auth_status(current_user: User = Depends(get_current_user)) -> APIResponse:
    """
    Check current user's Spotify authentication status.

    Returns detailed information about token validity, expiration,
    and whether any action is needed from the user.
    """
    try:
        # Validate token using token manager
        validation = await spotify_token_manager.validate_token(current_user.id)

        # Check if user needs re-authentication
        needs_reauth, reauth_reason = await spotify_token_manager.check_user_needs_reauth(current_user.id)

        response_data = {
            "status": validation.status.value,
            "is_valid": validation.is_valid,
            "needs_refresh": validation.needs_refresh,
            "needs_reauth": needs_reauth,
            "expires_in_seconds": validation.expires_in_seconds,
            "error_message": validation.error_message,
            "reauth_reason": reauth_reason,
            "recommendations": validation.recommendations
        }

        logger.info(
            "[TOKEN-API-001] Spotify status checked",
            extra={
                "user_id": current_user.id,
                "status": validation.status.value,
                "needs_reauth": needs_reauth
            }
        )

        return APIResponse(
            success=True,
            message="Spotify authentication status retrieved",
            data=response_data
        )

    except Exception as e:
        logger.error(
            "[TOKEN-API-ERROR-001] Error checking Spotify status",
            extra={"user_id": current_user.id, "error": str(e)},
            exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to check Spotify authentication status"
        )


@router.post(
    "/spotify/refresh",
    summary="Manually Refresh Spotify Token",
    description="Manually trigger a refresh of the user's Spotify tokens",
    tags=["Token Management", "Spotify"],
    responses={
        200: {
            "description": "Token refresh result",
            "model": APIResponse
        },
        401: {
            "description": "User not authenticated or refresh failed"
        }
    }
)
async def refresh_spotify_token(current_user: User = Depends(get_current_user)) -> APIResponse:
    """
    Manually refresh the current user's Spotify tokens.

    This endpoint allows users to manually trigger a token refresh
    if they're experiencing authentication issues.
    """
    try:
        refresh_result, new_token = await spotify_token_manager.refresh_token(
            current_user.id,
            force=True  # Force refresh even if token appears valid
        )

        success = refresh_result.value.startswith("success")

        response_data = {
            "refresh_result": refresh_result.value,
            "success": success,
            "message": spotify_token_manager._get_refresh_error_message(refresh_result)
                      if not success else "Token refreshed successfully"
        }

        logger.info(
            "[TOKEN-API-002] Manual token refresh requested",
            extra={
                "user_id": current_user.id,
                "result": refresh_result.value,
                "success": success
            }
        )

        if not success and refresh_result.value in ["failed_no_refresh_token", "failed_expired_refresh"]:
            raise HTTPException(
                status_code=401,
                detail=response_data["message"]
            )

        return APIResponse(
            success=success,
            message=response_data["message"],
            data=response_data
        )

    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        logger.error(
            "[TOKEN-API-ERROR-002] Error refreshing Spotify token",
            extra={"user_id": current_user.id, "error": str(e)},
            exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to refresh Spotify token"
        )


@router.get(
    "/notifications",
    summary="Get User Notifications",
    description="Get notifications for the current user, including token-related alerts",
    tags=["Notifications", "User"],
    responses={
        200: {
            "description": "User notifications",
            "model": APIResponse
        },
        401: {
            "description": "User not authenticated"
        }
    }
)
async def get_user_notifications_endpoint(
    include_read: bool = False,
    limit: int = 50,
    current_user: User = Depends(get_current_user)
) -> APIResponse:
    """
    Get notifications for the current user.

    Args:
        include_read: Whether to include already-read notifications
        limit: Maximum number of notifications to return (max 100)

    Returns:
        List of user notifications with metadata
    """
    try:
        # Validate limit
        limit = min(max(1, limit), 100)

        # Get notifications
        notifications = await get_user_notifications(current_user.id, include_read)

        # Apply limit
        notifications = notifications[:limit]

        logger.debug(
            "[TOKEN-API-003] User notifications retrieved",
            extra={
                "user_id": current_user.id,
                "count": len(notifications),
                "include_read": include_read
            }
        )

        return APIResponse(
            success=True,
            message=f"Retrieved {len(notifications)} notifications",
            data={
                "notifications": notifications,
                "total": len(notifications),
                "include_read": include_read
            }
        )

    except Exception as e:
        logger.error(
            "[TOKEN-API-ERROR-003] Error getting user notifications",
            extra={"user_id": current_user.id, "error": str(e)},
            exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve notifications"
        )


@router.post(
    "/notifications/{notification_id}/read",
    summary="Mark Notification as Read",
    description="Mark a specific notification as read",
    tags=["Notifications", "User"],
    responses={
        200: {
            "description": "Notification marked as read",
            "model": APIResponse
        },
        404: {
            "description": "Notification not found"
        }
    }
)
async def mark_notification_read(
    notification_id: str,
    current_user: User = Depends(get_current_user)
) -> APIResponse:
    """Mark a notification as read for the current user."""
    try:
        success = await user_notification_service.mark_notification_read(
            notification_id,
            current_user.id
        )

        if not success:
            raise HTTPException(
                status_code=404,
                detail="Notification not found or cannot be marked as read"
            )

        logger.debug(
            "[TOKEN-API-004] Notification marked as read",
            extra={
                "user_id": current_user.id,
                "notification_id": notification_id
            }
        )

        return APIResponse(
            success=True,
            message="Notification marked as read"
        )

    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        logger.error(
            "[TOKEN-API-ERROR-004] Error marking notification as read",
            extra={
                "user_id": current_user.id,
                "notification_id": notification_id,
                "error": str(e)
            },
            exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to mark notification as read"
        )


@router.post(
    "/notifications/{notification_id}/dismiss",
    summary="Dismiss Notification",
    description="Dismiss a specific notification (marks as read and dismissed)",
    tags=["Notifications", "User"],
    responses={
        200: {
            "description": "Notification dismissed",
            "model": APIResponse
        },
        404: {
            "description": "Notification not found"
        }
    }
)
async def dismiss_notification(
    notification_id: str,
    current_user: User = Depends(get_current_user)
) -> APIResponse:
    """Dismiss a notification for the current user."""
    try:
        success = await user_notification_service.dismiss_notification(
            notification_id,
            current_user.id
        )

        if not success:
            raise HTTPException(
                status_code=404,
                detail="Notification not found or cannot be dismissed"
            )

        logger.debug(
            "[TOKEN-API-005] Notification dismissed",
            extra={
                "user_id": current_user.id,
                "notification_id": notification_id
            }
        )

        return APIResponse(
            success=True,
            message="Notification dismissed"
        )

    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        logger.error(
            "[TOKEN-API-ERROR-005] Error dismissing notification",
            extra={
                "user_id": current_user.id,
                "notification_id": notification_id,
                "error": str(e)
            },
            exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to dismiss notification"
        )


@router.get(
    "/admin/token-service/status",
    summary="Background Token Service Status",
    description="Get status and statistics of the background token refresh service",
    tags=["Admin", "Monitoring", "Token Management"],
    responses={
        200: {
            "description": "Background service status",
            "model": APIResponse
        }
    }
)
async def get_token_service_status() -> APIResponse:
    """
    Get background token service status and statistics.

    This endpoint provides information about the background service
    that automatically refreshes tokens for all users.
    """
    try:
        status = get_background_service_status()

        logger.debug("[TOKEN-API-006] Background service status requested")

        return APIResponse(
            success=True,
            message="Background token service status retrieved",
            data=status
        )

    except Exception as e:
        logger.error(
            "[TOKEN-API-ERROR-006] Error getting background service status",
            extra={"error": str(e)},
            exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to get background service status"
        )


@router.get(
    "/admin/token-service/health",
    summary="Background Token Service Health Check",
    description="Check health of the background token refresh service",
    tags=["Admin", "Monitoring", "Health"],
    responses={
        200: {
            "description": "Background service health status",
            "model": APIResponse
        }
    }
)
async def get_token_service_health() -> APIResponse:
    """
    Check health of the background token service.

    Returns health indicators including service uptime,
    error rates, and operational status.
    """
    try:
        health = get_background_service_health()

        logger.debug("[TOKEN-API-007] Background service health check requested")

        # Determine HTTP status based on health
        http_status = 200 if health.get("healthy", False) else 503

        response = APIResponse(
            success=health.get("healthy", False),
            message="Background token service health checked",
            data=health
        )

        if http_status != 200:
            raise HTTPException(status_code=http_status, detail=response.dict())

        return response

    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        logger.error(
            "[TOKEN-API-ERROR-007] Error checking background service health",
            extra={"error": str(e)},
            exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to check background service health"
        )


@router.get(
    "/health/token-manager",
    summary="Token Manager Health Check",
    description="Check health of the Spotify token management system",
    tags=["Health", "Monitoring", "Token Management"],
    responses={
        200: {
            "description": "Token manager health status",
            "model": APIResponse
        }
    }
)
async def get_token_manager_health() -> APIResponse:
    """
    Check health of the Spotify token management system.

    This endpoint tests database connectivity, Spotify OAuth configuration,
    and other critical components of the token management system.
    """
    try:
        health = await spotify_token_manager.health_check()

        logger.debug("[TOKEN-API-008] Token manager health check requested")

        # Determine HTTP status based on health
        http_status = 200 if health.get("healthy", False) else 503

        response = APIResponse(
            success=health.get("healthy", False),
            message="Token manager health checked",
            data=health
        )

        if http_status != 200:
            raise HTTPException(status_code=http_status, detail=response.dict())

        return response

    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        logger.error(
            "[TOKEN-API-ERROR-008] Error checking token manager health",
            extra={"error": str(e)},
            exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to check token manager health"
        )


@router.post(
    "/admin/token-service/start",
    summary="Start Background Token Service",
    description="Start the background token refresh service",
    tags=["Admin", "Token Management"],
    responses={
        200: {
            "description": "Service started successfully",
            "model": APIResponse
        }
    }
)
async def start_token_service() -> APIResponse:
    """
    Start the background token refresh service.

    This endpoint allows administrators to start the background service
    that proactively refreshes user tokens before they expire.
    """
    try:
        success = await start_background_token_service()

        if not success:
            raise HTTPException(
                status_code=400,
                detail="Failed to start background token service"
            )

        logger.info("[TOKEN-API-009] Background token service started via API")

        return APIResponse(
            success=True,
            message="Background token service started successfully"
        )

    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        logger.error(
            "[TOKEN-API-ERROR-009] Error starting background service",
            extra={"error": str(e)},
            exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to start background token service"
        )


@router.post(
    "/admin/token-service/stop",
    summary="Stop Background Token Service",
    description="Stop the background token refresh service",
    tags=["Admin", "Token Management"],
    responses={
        200: {
            "description": "Service stopped successfully",
            "model": APIResponse
        }
    }
)
async def stop_token_service() -> APIResponse:
    """
    Stop the background token refresh service.

    This endpoint allows administrators to gracefully stop the background
    service that refreshes user tokens.
    """
    try:
        success = await stop_background_token_service()

        if not success:
            raise HTTPException(
                status_code=400,
                detail="Failed to stop background token service"
            )

        logger.info("[TOKEN-API-010] Background token service stopped via API")

        return APIResponse(
            success=True,
            message="Background token service stopped successfully"
        )

    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        logger.error(
            "[TOKEN-API-ERROR-010] Error stopping background service",
            extra={"error": str(e)},
            exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to stop background token service"
        )


@router.get(
    "/debug/spotify-client-test",
    summary="Test Spotify Client Creation",
    description="Test creating a Spotify client for the current user (debug endpoint)",
    tags=["Debug", "Spotify"],
    responses={
        200: {
            "description": "Spotify client test results",
            "model": APIResponse
        }
    }
)
async def test_spotify_client(current_user: User = Depends(get_current_user)) -> APIResponse:
    """
    Test Spotify client creation for debugging purposes.

    This endpoint attempts to create a Spotify client for the current user
    and returns detailed information about the process for troubleshooting.
    """
    try:
        test_results = {
            "user_id": current_user.id,
            "spotify_id": current_user.spotify_id,
            "test_timestamp": datetime.now().isoformat()
        }

        # Test token validation
        validation = await spotify_token_manager.validate_token(current_user.id)
        test_results["token_validation"] = {
            "status": validation.status.value,
            "is_valid": validation.is_valid,
            "needs_refresh": validation.needs_refresh,
            "expires_in_seconds": validation.expires_in_seconds,
            "recommendations": validation.recommendations
        }

        # Test client creation
        try:
            spotify_client = await get_spotify_client_for_user(current_user.id)
            test_results["client_creation"] = {
                "success": True,
                "message": "Spotify client created successfully"
            }

            # Test a simple API call
            try:
                user_profile = spotify_client.current_user()
                test_results["api_test"] = {
                    "success": True,
                    "user_id": user_profile.get("id"),
                    "display_name": user_profile.get("display_name")
                }
            except Exception as e:
                test_results["api_test"] = {
                    "success": False,
                    "error": str(e)
                }

        except Exception as e:
            test_results["client_creation"] = {
                "success": False,
                "error": str(e)
            }

        logger.info(
            "[TOKEN-API-011] Spotify client test completed",
            extra={
                "user_id": current_user.id,
                "client_success": test_results.get("client_creation", {}).get("success"),
                "api_success": test_results.get("api_test", {}).get("success")
            }
        )

        return APIResponse(
            success=True,
            message="Spotify client test completed",
            data=test_results
        )

    except Exception as e:
        logger.error(
            "[TOKEN-API-ERROR-011] Error in Spotify client test",
            extra={"user_id": current_user.id, "error": str(e)},
            exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to test Spotify client"
        )