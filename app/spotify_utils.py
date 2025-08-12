"""
Spotify API utilities with proper error handling, rate limiting, and retry mechanisms.
This module provides a robust wrapper around spotipy with production-ready resilience.
"""

import asyncio
import random
import logging
from typing import Optional, Dict, Any, Callable, List
from datetime import datetime, timezone, timedelta
import spotipy
from spotipy.exceptions import SpotifyException
from fastapi import HTTPException

logger = logging.getLogger("music_bingo")

# Spotify error code mappings for user-friendly messages
SPOTIFY_ERROR_MESSAGES = {
    400: "Invalid request. Please check your input and try again.",
    401: "Please log in to Spotify again - your session has expired.",
    403: "You don't have permission to access this Spotify resource.",
    404: "The requested Spotify resource was not found.",
    429: "Too many requests to Spotify. Please wait a moment and try again.",
    500: "Spotify service is temporarily unavailable. Please try again later.",
    502: "Spotify service is temporarily unavailable. Please try again later.",
    503: "Spotify service is temporarily unavailable. Please try again later.",
}

# Device state cache
_device_cache = {
    "devices": [],
    "last_updated": None,
    "cache_duration": timedelta(minutes=2),  # Cache devices for 2 minutes
}


class SpotifyAPIError(Exception):
    """Custom exception for Spotify API errors with context."""

    def __init__(
        self,
        message: str,
        status_code: int = 500,
        original_error: Optional[Exception] = None,
    ):
        self.message = message
        self.status_code = status_code
        self.original_error = original_error
        super().__init__(message)


async def spotify_api_call_with_retry(
    api_call: Callable,
    max_retries: int = 3,
    base_delay: float = 1.0,
    operation_name: str = "Spotify API call",
) -> Any:
    """
    Execute a Spotify API call with exponential backoff retry logic.

    Args:
        api_call: Function to call (should be a lambda or function that makes the API call)
        max_retries: Maximum number of retry attempts
        base_delay: Base delay in seconds for exponential backoff
        operation_name: Descriptive name for logging

    Returns:
        Result of the API call

    Raises:
        SpotifyAPIError: For all Spotify-related errors with user-friendly messages
    """
    last_exception = None

    for attempt in range(max_retries + 1):
        try:
            logger.debug(
                f"[SPOTIFY-API] Attempting {operation_name}",
                extra={"attempt": attempt + 1, "max_retries": max_retries + 1},
            )

            result = api_call()

            if attempt > 0:
                logger.info(
                    f"[SPOTIFY-API] {operation_name} succeeded after {attempt} retries"
                )

            return result

        except SpotifyException as e:
            last_exception = e
            status_code = getattr(e, "http_status", 500)

            logger.warning(
                f"[SPOTIFY-API] {operation_name} failed",
                extra={
                    "attempt": attempt + 1,
                    "status_code": status_code,
                    "error": str(e),
                },
            )

            # Handle rate limiting with exponential backoff
            if status_code == 429 and attempt < max_retries:
                retry_after = getattr(e, "retry_after", None)
                if retry_after:
                    wait_time = int(retry_after)
                    logger.info(
                        f"[SPOTIFY-API] Rate limited, waiting {wait_time}s as suggested by Spotify"
                    )
                else:
                    wait_time = base_delay * (2**attempt) + random.uniform(0, 1)
                    logger.info(
                        f"[SPOTIFY-API] Rate limited, waiting {wait_time:.2f}s (exponential backoff)"
                    )

                await asyncio.sleep(wait_time)
                continue

            # Handle other retryable errors (5xx server errors)
            elif status_code >= 500 and attempt < max_retries:
                wait_time = base_delay * (2**attempt) + random.uniform(0, 1)
                logger.info(f"[SPOTIFY-API] Server error, retrying in {wait_time:.2f}s")
                await asyncio.sleep(wait_time)
                continue

            # Non-retryable error or max retries reached
            user_message = SPOTIFY_ERROR_MESSAGES.get(
                status_code, "An error occurred with Spotify."
            )
            logger.error(
                f"[SPOTIFY-API] {operation_name} failed permanently",
                extra={
                    "status_code": status_code,
                    "error": str(e),
                    "user_message": user_message,
                },
            )

            raise SpotifyAPIError(user_message, status_code, e)

        except Exception as e:
            last_exception = e
            logger.error(
                f"[SPOTIFY-API] Unexpected error in {operation_name}",
                extra={
                    "attempt": attempt + 1,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )

            # For non-Spotify exceptions, only retry server-like errors
            if attempt < max_retries and "timeout" in str(e).lower():
                wait_time = base_delay * (2**attempt)
                await asyncio.sleep(wait_time)
                continue

            # Don't expose internal errors to users
            raise SpotifyAPIError(
                "A technical error occurred. Please try again.", 500, e
            )

    # This should never be reached, but just in case
    if last_exception:
        raise SpotifyAPIError("Maximum retries exceeded", 500, last_exception)


async def get_devices_with_cache(
    sp: spotipy.Spotify, force_refresh: bool = False
) -> List[Dict[str, Any]]:
    """
    Get available Spotify devices with caching to reduce API calls.

    Args:
        sp: Spotify client instance
        force_refresh: Force refresh of device cache

    Returns:
        List of device dictionaries
    """
    now = datetime.now(timezone.utc)

    # Check if cache is valid and not forcing refresh
    if (
        not force_refresh
        and _device_cache["last_updated"]
        and now - _device_cache["last_updated"] < _device_cache["cache_duration"]
    ):
        logger.debug("[SPOTIFY-DEVICES] Using cached device list")
        return _device_cache["devices"]

    # Refresh device list from API
    try:
        devices_info = await spotify_api_call_with_retry(
            lambda: sp.devices(), operation_name="get devices"
        )

        devices = devices_info.get("devices", [])

        # Update cache
        _device_cache["devices"] = devices
        _device_cache["last_updated"] = now

        logger.info(
            f"[SPOTIFY-DEVICES] Device cache updated",
            extra={
                "device_count": len(devices),
                "active_devices": len([d for d in devices if d.get("is_active")]),
            },
        )

        return devices

    except SpotifyAPIError as e:
        # If API fails but we have cached data, return it with a warning
        if _device_cache["devices"]:
            logger.warning(
                f"[SPOTIFY-DEVICES] API failed, using stale cache",
                extra={
                    "error": e.message,
                    "cache_age_minutes": (
                        now - _device_cache["last_updated"]
                    ).total_seconds()
                    / 60,
                },
            )
            return _device_cache["devices"]

        # No cache available, re-raise the error
        raise


async def find_active_device_with_fallback(
    sp: spotipy.Spotify,
) -> Optional[Dict[str, Any]]:
    """
    Find an active Spotify device with intelligent fallback strategies.

    Args:
        sp: Spotify client instance

    Returns:
        Active device dictionary or None if no suitable device found
    """
    devices = await get_devices_with_cache(sp)

    if not devices:
        logger.warning("[SPOTIFY-DEVICE] No Spotify devices found")
        return None

    # First, look for actively playing devices
    active_devices = [d for d in devices if d.get("is_active")]
    if active_devices:
        device = active_devices[0]
        logger.info(f"[SPOTIFY-DEVICE] Found active device: {device.get('name')}")
        return device

    # Fallback 1: Look for available devices (not restricted)
    available_devices = [d for d in devices if not d.get("is_restricted")]
    if available_devices:
        # Prefer computer/web players over mobile devices for better control
        preferred_types = ["Computer", "Smartphone", "Tablet"]
        for device_type in preferred_types:
            for device in available_devices:
                if device.get("type") == device_type:
                    logger.info(
                        f"[SPOTIFY-DEVICE] Using fallback device: {device.get('name')} ({device_type})"
                    )
                    return device

        # If no preferred type found, use the first available
        device = available_devices[0]
        logger.info(
            f"[SPOTIFY-DEVICE] Using first available device: {device.get('name')}"
        )
        return device

    # Fallback 2: Try to activate the first device we can find
    if devices:
        device = devices[0]
        logger.info(
            f"[SPOTIFY-DEVICE] Attempting to activate device: {device.get('name')}"
        )

        try:
            await spotify_api_call_with_retry(
                lambda: sp.transfer_playback(device_id=device["id"], force_play=False),
                operation_name="transfer playback to activate device",
            )
            return device
        except SpotifyAPIError as e:
            logger.warning(
                f"[SPOTIFY-DEVICE] Failed to activate device",
                extra={"device_name": device.get("name"), "error": e.message},
            )

    logger.warning("[SPOTIFY-DEVICE] No suitable Spotify device found")
    return None


async def play_track_with_fallback(
    sp: spotipy.Spotify, track_uri: str, device_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Play a track with device fallback handling.

    Args:
        sp: Spotify client instance
        track_uri: Spotify track URI
        device_id: Optional specific device ID to use

    Returns:
        Dictionary with playback information

    Raises:
        SpotifyAPIError: If playback fails after all fallback attempts
    """
    target_device = None

    if device_id:
        # Try to use specified device
        devices = await get_devices_with_cache(sp)
        target_device = next((d for d in devices if d["id"] == device_id), None)

        if not target_device:
            logger.warning(
                f"[SPOTIFY-PLAYBACK] Specified device not found: {device_id}"
            )

    if not target_device:
        # Find an active device with fallback
        target_device = await find_active_device_with_fallback(sp)

        if not target_device:
            raise SpotifyAPIError(
                "No active Spotify device found. Please open Spotify on any device and try again.",
                400,
            )

    # Attempt to play the track
    try:
        await spotify_api_call_with_retry(
            lambda: sp.start_playback(device_id=target_device["id"], uris=[track_uri]),
            operation_name="start playback",
        )

        logger.info(
            f"[SPOTIFY-PLAYBACK] Track playing successfully",
            extra={
                "track_uri": track_uri,
                "device": target_device.get("name"),
                "device_id": target_device["id"],
            },
        )

        return {
            "device_id": target_device["id"],
            "device_name": target_device.get("name"),
            "device_type": target_device.get("type"),
        }

    except SpotifyAPIError as e:
        # If playback fails, try to refresh devices and retry once
        if "device" in e.message.lower():
            logger.info(
                "[SPOTIFY-PLAYBACK] Device error, refreshing device list and retrying"
            )

            backup_device = await find_active_device_with_fallback(sp)
            if backup_device and backup_device["id"] != target_device["id"]:
                try:
                    await spotify_api_call_with_retry(
                        lambda: sp.start_playback(
                            device_id=backup_device["id"], uris=[track_uri]
                        ),
                        operation_name="start playback (retry with backup device)",
                    )

                    logger.info(
                        f"[SPOTIFY-PLAYBACK] Retry successful with backup device",
                        extra={"backup_device": backup_device.get("name")},
                    )

                    return {
                        "device_id": backup_device["id"],
                        "device_name": backup_device.get("name"),
                        "device_type": backup_device.get("type"),
                    }
                except SpotifyAPIError:
                    pass  # Fall through to original error

        # Re-raise the original error
        raise


async def pause_playback_safe(
    sp: spotipy.Spotify, device_id: Optional[str] = None
) -> bool:
    """
    Safely pause Spotify playback with error handling.

    Args:
        sp: Spotify client instance
        device_id: Optional device ID to pause

    Returns:
        True if pause was successful, False otherwise
    """
    try:
        if device_id:
            await spotify_api_call_with_retry(
                lambda: sp.pause_playback(device_id=device_id),
                operation_name="pause playback",
            )
        else:
            await spotify_api_call_with_retry(
                lambda: sp.pause_playback(), operation_name="pause playback"
            )

        logger.info("[SPOTIFY-PLAYBACK] Playback paused successfully")
        return True

    except SpotifyAPIError as e:
        logger.warning(f"[SPOTIFY-PLAYBACK] Failed to pause playback: {e.message}")
        return False


def convert_spotify_exception_to_http(
    e: Exception, operation: str = "Spotify operation"
) -> HTTPException:
    """
    Convert Spotify exceptions to appropriate HTTP exceptions with sanitized messages.

    Args:
        e: The original exception
        operation: Description of the operation for logging

    Returns:
        HTTPException with appropriate status code and user-safe message
    """
    if isinstance(e, SpotifyAPIError):
        return HTTPException(status_code=e.status_code, detail=e.message)

    elif isinstance(e, SpotifyException):
        status_code = getattr(e, "http_status", 500)
        user_message = SPOTIFY_ERROR_MESSAGES.get(
            status_code, "An error occurred with Spotify."
        )

        logger.error(
            f"[SPOTIFY-ERROR] {operation} failed",
            extra={"status_code": status_code, "error": str(e)},
        )

        return HTTPException(
            status_code=400 if status_code < 500 else 500, detail=user_message
        )

    else:
        # Generic error - don't expose internal details
        logger.error(
            f"[SPOTIFY-ERROR] Unexpected error in {operation}",
            extra={"error": str(e), "error_type": type(e).__name__},
        )

        return HTTPException(
            status_code=500,
            detail="A technical error occurred. Please try again later.",
        )


# Cache invalidation helper
def invalidate_device_cache():
    """Invalidate the device cache to force refresh on next access."""
    _device_cache["last_updated"] = None
    _device_cache["devices"] = []
    logger.debug("[SPOTIFY-CACHE] Device cache invalidated")
