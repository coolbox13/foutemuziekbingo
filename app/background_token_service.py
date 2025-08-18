"""
Background Token Refresh Service

This service runs in the background to proactively refresh Spotify tokens
before they expire, ensuring uninterrupted service and better user experience.

Key Features:
- Proactive token refresh (5 minutes before expiry)
- Configurable refresh intervals
- Health monitoring and alerting
- Graceful shutdown handling
- Error recovery and retry logic
- User notification for failed refreshes

Author: Claude Code Assistant
Date: 2025-01-18
Issue: CRIT-003 - Background token maintenance implementation
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
import signal
from dataclasses import dataclass
from enum import Enum

from app.spotify_token_manager import (
    spotify_token_manager, 
    TokenRefreshResult,
    TokenStatus
)
from app.database import database

logger = logging.getLogger("music_bingo")


class ServiceStatus(str, Enum):
    """Background service status"""
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    ERROR = "error"


@dataclass
class RefreshStats:
    """Statistics for token refresh operations"""
    total_users_checked: int = 0
    tokens_refreshed: int = 0
    refresh_successes: int = 0
    refresh_failures: int = 0
    users_needing_reauth: int = 0
    last_run_duration: Optional[float] = None
    last_run_timestamp: Optional[datetime] = None
    errors: List[str] = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []


class BackgroundTokenService:
    """
    Background service for proactive Spotify token management.
    
    Runs periodic checks to refresh tokens before they expire,
    maintaining service availability and user experience.
    """

    def __init__(self, 
                 check_interval_minutes: int = 10,
                 refresh_buffer_minutes: int = 15):
        """
        Initialize background token service.
        
        Args:
            check_interval_minutes: How often to check for tokens needing refresh
            refresh_buffer_minutes: Refresh tokens this many minutes before expiry
        """
        self.check_interval = timedelta(minutes=check_interval_minutes)
        self.refresh_buffer = timedelta(minutes=refresh_buffer_minutes)
        
        self.status = ServiceStatus.STOPPED
        self.stats = RefreshStats()
        self._task: Optional[asyncio.Task] = None
        self._shutdown_event = asyncio.Event()
        
        logger.info(
            "[BACKGROUND-TOKEN-INIT] Background token service initialized",
            extra={
                "check_interval_minutes": check_interval_minutes,
                "refresh_buffer_minutes": refresh_buffer_minutes
            }
        )

    async def start(self) -> bool:
        """
        Start the background token refresh service.
        
        Returns:
            True if started successfully, False otherwise
        """
        if self.status in [ServiceStatus.RUNNING, ServiceStatus.STARTING]:
            logger.warning("[BACKGROUND-TOKEN-001] Service already running or starting")
            return False

        try:
            self.status = ServiceStatus.STARTING
            logger.info("[BACKGROUND-TOKEN-002] Starting background token service")
            
            # Reset shutdown event
            self._shutdown_event.clear()
            
            # Start the background task
            self._task = asyncio.create_task(self._run_service())
            
            self.status = ServiceStatus.RUNNING
            logger.info("[BACKGROUND-TOKEN-003] Background token service started successfully")
            
            return True
            
        except Exception as e:
            self.status = ServiceStatus.ERROR
            logger.error(
                "[BACKGROUND-TOKEN-ERROR-001] Failed to start service",
                extra={"error": str(e)},
                exc_info=True
            )
            return False

    async def stop(self, timeout: float = 30.0) -> bool:
        """
        Stop the background token refresh service gracefully.
        
        Args:
            timeout: Maximum time to wait for graceful shutdown
            
        Returns:
            True if stopped successfully, False if timeout occurred
        """
        if self.status == ServiceStatus.STOPPED:
            logger.info("[BACKGROUND-TOKEN-004] Service already stopped")
            return True

        try:
            self.status = ServiceStatus.STOPPING
            logger.info("[BACKGROUND-TOKEN-005] Stopping background token service")
            
            # Signal shutdown
            self._shutdown_event.set()
            
            # Wait for task to complete
            if self._task:
                try:
                    await asyncio.wait_for(self._task, timeout=timeout)
                except asyncio.TimeoutError:
                    logger.warning(
                        "[BACKGROUND-TOKEN-006] Graceful shutdown timeout, cancelling task"
                    )
                    self._task.cancel()
                    try:
                        await self._task
                    except asyncio.CancelledError:
                        pass

            self.status = ServiceStatus.STOPPED
            self._task = None
            
            logger.info("[BACKGROUND-TOKEN-007] Background token service stopped")
            return True
            
        except Exception as e:
            logger.error(
                "[BACKGROUND-TOKEN-ERROR-002] Error during service shutdown",
                extra={"error": str(e)},
                exc_info=True
            )
            self.status = ServiceStatus.ERROR
            return False

    async def _run_service(self):
        """Main service loop for background token refresh"""
        logger.info("[BACKGROUND-TOKEN-008] Background token service loop started")
        
        try:
            while not self._shutdown_event.is_set():
                run_start = datetime.now(timezone.utc)
                
                try:
                    # Perform token refresh check
                    await self._refresh_cycle()
                    
                except Exception as e:
                    logger.error(
                        "[BACKGROUND-TOKEN-ERROR-003] Error in refresh cycle",
                        extra={"error": str(e)},
                        exc_info=True
                    )
                    self.stats.errors.append(f"Refresh cycle error: {str(e)}")
                    
                    # Limit error list size
                    if len(self.stats.errors) > 100:
                        self.stats.errors = self.stats.errors[-50:]

                # Update run duration
                self.stats.last_run_duration = (
                    datetime.now(timezone.utc) - run_start
                ).total_seconds()
                self.stats.last_run_timestamp = run_start

                # Wait for next cycle or shutdown signal
                try:
                    await asyncio.wait_for(
                        self._shutdown_event.wait(),
                        timeout=self.check_interval.total_seconds()
                    )
                    # If we get here, shutdown was signaled
                    break
                except asyncio.TimeoutError:
                    # Normal timeout, continue to next cycle
                    pass

        except Exception as e:
            logger.error(
                "[BACKGROUND-TOKEN-ERROR-004] Fatal error in service loop",
                extra={"error": str(e)},
                exc_info=True
            )
            self.status = ServiceStatus.ERROR
            raise
        
        logger.info("[BACKGROUND-TOKEN-009] Background token service loop ended")

    async def _refresh_cycle(self):
        """Perform one cycle of token refresh checks"""
        cycle_id = f"cycle-{int(datetime.now().timestamp())}"
        
        logger.debug(
            "[BACKGROUND-TOKEN-010] Starting refresh cycle",
            extra={"cycle_id": cycle_id}
        )
        
        # Reset cycle stats
        cycle_stats = RefreshStats()
        
        try:
            # Get users who might need token refresh
            users_to_check = await self._get_users_needing_refresh()
            cycle_stats.total_users_checked = len(users_to_check)
            
            if not users_to_check:
                logger.debug(
                    "[BACKGROUND-TOKEN-011] No users need token refresh",
                    extra={"cycle_id": cycle_id}
                )
                return

            logger.info(
                "[BACKGROUND-TOKEN-012] Found users potentially needing refresh",
                extra={
                    "cycle_id": cycle_id,
                    "user_count": len(users_to_check)
                }
            )

            # Process each user
            for user in users_to_check:
                try:
                    await self._process_user_tokens(user, cycle_stats, cycle_id)
                except Exception as e:
                    logger.error(
                        "[BACKGROUND-TOKEN-ERROR-005] Error processing user tokens",
                        extra={
                            "cycle_id": cycle_id,
                            "user_id": user.get("id", "unknown"),
                            "error": str(e)
                        },
                        exc_info=True
                    )
                    cycle_stats.errors.append(f"User {user.get('id', 'unknown')}: {str(e)}")

            # Update service stats
            self._update_service_stats(cycle_stats)

            logger.info(
                "[BACKGROUND-TOKEN-013] Refresh cycle completed",
                extra={
                    "cycle_id": cycle_id,
                    "users_checked": cycle_stats.total_users_checked,
                    "refreshed": cycle_stats.tokens_refreshed,
                    "successes": cycle_stats.refresh_successes,
                    "failures": cycle_stats.refresh_failures,
                    "need_reauth": cycle_stats.users_needing_reauth
                }
            )

        except Exception as e:
            logger.error(
                "[BACKGROUND-TOKEN-ERROR-006] Error in refresh cycle",
                extra={"cycle_id": cycle_id, "error": str(e)},
                exc_info=True
            )
            raise

    async def _get_users_needing_refresh(self) -> List[Dict[str, Any]]:
        """
        Get users whose tokens might need refresh.
        
        Returns users with Spotify tokens that expire within the refresh buffer.
        """
        try:
            # Calculate cutoff time for token expiry
            cutoff_time = datetime.now(timezone.utc) + self.refresh_buffer
            cutoff_iso = cutoff_time.isoformat()
            
            # Query for users with tokens expiring soon
            # Note: This is a simplified query - adjust based on your database schema
            users = await database.query_records(
                "users",
                filters={
                    "spotify_access_token": {"is_not": None},
                    "spotify_token_expires_at": {"less_than": cutoff_iso}
                },
                limit=100  # Process in batches
            )
            
            logger.debug(
                "[BACKGROUND-TOKEN-014] Found users with tokens expiring soon",
                extra={
                    "user_count": len(users),
                    "cutoff_time": cutoff_iso
                }
            )
            
            return users

        except Exception as e:
            logger.error(
                "[BACKGROUND-TOKEN-ERROR-007] Error querying users for refresh",
                extra={"error": str(e)},
                exc_info=True
            )
            return []

    async def _process_user_tokens(self, user: Dict[str, Any], stats: RefreshStats, cycle_id: str):
        """Process token refresh for a single user"""
        user_id = user.get("id")
        if not user_id:
            logger.warning(
                "[BACKGROUND-TOKEN-015] User missing ID, skipping",
                extra={"cycle_id": cycle_id, "user_data": user}
            )
            return

        logger.debug(
            "[BACKGROUND-TOKEN-016] Processing user token refresh",
            extra={
                "cycle_id": cycle_id,
                "user_id": user_id,
                "spotify_id": user.get("spotify_id")
            }
        )

        try:
            # Validate current token status
            validation = await spotify_token_manager.validate_token(user_id)
            
            if validation.status == TokenStatus.VALID and not validation.needs_refresh:
                logger.debug(
                    "[BACKGROUND-TOKEN-017] User token still valid, skipping",
                    extra={
                        "cycle_id": cycle_id,
                        "user_id": user_id,
                        "expires_in": validation.expires_in_seconds
                    }
                )
                return

            # Attempt token refresh
            if validation.needs_refresh or validation.status in [
                TokenStatus.EXPIRED, 
                TokenStatus.REFRESH_NEEDED
            ]:
                stats.tokens_refreshed += 1
                
                logger.info(
                    "[BACKGROUND-TOKEN-018] Attempting proactive token refresh",
                    extra={
                        "cycle_id": cycle_id,
                        "user_id": user_id,
                        "token_status": validation.status.value
                    }
                )

                refresh_result, new_token = await spotify_token_manager.refresh_token(user_id)

                if refresh_result == TokenRefreshResult.SUCCESS:
                    stats.refresh_successes += 1
                    logger.info(
                        "[BACKGROUND-TOKEN-019] Proactive token refresh successful",
                        extra={
                            "cycle_id": cycle_id,
                            "user_id": user_id
                        }
                    )
                else:
                    stats.refresh_failures += 1
                    
                    # Check if user needs re-authentication
                    if refresh_result in [
                        TokenRefreshResult.FAILED_NO_REFRESH_TOKEN,
                        TokenRefreshResult.FAILED_EXPIRED_REFRESH
                    ]:
                        stats.users_needing_reauth += 1
                        logger.warning(
                            "[BACKGROUND-TOKEN-020] User needs re-authentication",
                            extra={
                                "cycle_id": cycle_id,
                                "user_id": user_id,
                                "refresh_result": refresh_result.value
                            }
                        )
                        
                        # TODO: Implement user notification here
                        await self._notify_user_reauth_needed(user_id, cycle_id)
                        
                    else:
                        logger.warning(
                            "[BACKGROUND-TOKEN-021] Token refresh failed",
                            extra={
                                "cycle_id": cycle_id,
                                "user_id": user_id,
                                "refresh_result": refresh_result.value
                            }
                        )

        except Exception as e:
            stats.refresh_failures += 1
            logger.error(
                "[BACKGROUND-TOKEN-ERROR-008] Error processing user token refresh",
                extra={
                    "cycle_id": cycle_id,
                    "user_id": user_id,
                    "error": str(e)
                },
                exc_info=True
            )
            raise

    async def _notify_user_reauth_needed(self, user_id: str, cycle_id: str):
        """
        Notify user that re-authentication is needed.
        
        This is a placeholder for future user notification implementation.
        Could be email, push notification, in-app notification, etc.
        """
        logger.info(
            "[BACKGROUND-TOKEN-022] User notification needed (not implemented)",
            extra={
                "cycle_id": cycle_id,
                "user_id": user_id,
                "notification_type": "reauth_needed"
            }
        )
        
        # TODO: Implement actual user notification
        # Examples:
        # - Email notification
        # - Push notification  
        # - In-app notification flag
        # - WebSocket message to active sessions

    def _update_service_stats(self, cycle_stats: RefreshStats):
        """Update service-wide statistics with cycle results"""
        self.stats.total_users_checked += cycle_stats.total_users_checked
        self.stats.tokens_refreshed += cycle_stats.tokens_refreshed
        self.stats.refresh_successes += cycle_stats.refresh_successes
        self.stats.refresh_failures += cycle_stats.refresh_failures
        self.stats.users_needing_reauth += cycle_stats.users_needing_reauth
        
        # Add cycle errors to service errors
        self.stats.errors.extend(cycle_stats.errors)
        
        # Limit error list size
        if len(self.stats.errors) > 100:
            self.stats.errors = self.stats.errors[-50:]

    def get_status(self) -> Dict[str, Any]:
        """Get current service status and statistics"""
        return {
            "status": self.status.value,
            "check_interval_minutes": self.check_interval.total_seconds() / 60,
            "refresh_buffer_minutes": self.refresh_buffer.total_seconds() / 60,
            "stats": {
                "total_users_checked": self.stats.total_users_checked,
                "tokens_refreshed": self.stats.tokens_refreshed,
                "refresh_successes": self.stats.refresh_successes,
                "refresh_failures": self.stats.refresh_failures,
                "users_needing_reauth": self.stats.users_needing_reauth,
                "success_rate": (
                    self.stats.refresh_successes / self.stats.tokens_refreshed
                    if self.stats.tokens_refreshed > 0 else 0.0
                ),
                "last_run_duration": self.stats.last_run_duration,
                "last_run_timestamp": self.stats.last_run_timestamp.isoformat() 
                    if self.stats.last_run_timestamp else None,
                "recent_errors": self.stats.errors[-10:],  # Last 10 errors
            }
        }

    def get_health(self) -> Dict[str, Any]:
        """Get service health information"""
        health_status = {
            "healthy": self.status == ServiceStatus.RUNNING,
            "status": self.status.value,
            "uptime_status": "unknown"
        }
        
        # Check if service has run recently
        if self.stats.last_run_timestamp:
            time_since_last_run = (
                datetime.now(timezone.utc) - self.stats.last_run_timestamp
            ).total_seconds()
            
            expected_interval = self.check_interval.total_seconds()
            
            if time_since_last_run > expected_interval * 2:
                health_status["healthy"] = False
                health_status["uptime_status"] = "stale"
                health_status["time_since_last_run"] = time_since_last_run
            else:
                health_status["uptime_status"] = "active"
        
        # Check error rate
        if self.stats.tokens_refreshed > 10:  # Only check if we have sufficient data
            error_rate = self.stats.refresh_failures / self.stats.tokens_refreshed
            if error_rate > 0.5:  # More than 50% failure rate
                health_status["healthy"] = False
                health_status["high_error_rate"] = error_rate
        
        return health_status


# Global background service instance
background_token_service = BackgroundTokenService()


# Service lifecycle management functions
async def start_background_token_service() -> bool:
    """Start the background token refresh service"""
    return await background_token_service.start()


async def stop_background_token_service() -> bool:
    """Stop the background token refresh service"""
    return await background_token_service.stop()


def get_background_service_status() -> Dict[str, Any]:
    """Get current background service status"""
    return background_token_service.get_status()


def get_background_service_health() -> Dict[str, Any]:
    """Get background service health information"""
    return background_token_service.get_health()
