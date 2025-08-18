"""
User Notification Service for Token Management

This service provides user notifications for authentication issues,
particularly when Spotify tokens expire and users need to re-authenticate.

Key Features:
- In-app notification system
- WebSocket notifications for real-time updates
- Token expiry warnings
- Re-authentication prompts with clear instructions
- Notification history and management

Author: Claude Code Assistant
Date: 2025-01-18
Issue: CRIT-003 - User notification system for token management
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any, Set
from dataclasses import dataclass
from enum import Enum
import json

from app.database import database

logger = logging.getLogger("music_bingo")


class NotificationType(str, Enum):
    """Types of user notifications"""
    TOKEN_EXPIRY_WARNING = "token_expiry_warning"
    TOKEN_EXPIRED = "token_expired"
    REAUTH_REQUIRED = "reauth_required"
    REFRESH_FAILED = "refresh_failed"
    SERVICE_RESTORED = "service_restored"
    GENERAL_INFO = "general_info"


class NotificationPriority(str, Enum):
    """Notification priority levels"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class UserNotification:
    """User notification data structure"""
    id: str
    user_id: str
    notification_type: NotificationType
    priority: NotificationPriority
    title: str
    message: str
    action_url: Optional[str] = None
    action_text: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    created_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    read: bool = False
    dismissed: bool = False

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now(timezone.utc)
        if self.metadata is None:
            self.metadata = {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert notification to dictionary for API responses"""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "type": self.notification_type.value,
            "priority": self.priority.value,
            "title": self.title,
            "message": self.message,
            "action_url": self.action_url,
            "action_text": self.action_text,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "read": self.read,
            "dismissed": self.dismissed
        }


class UserNotificationService:
    """
    Service for managing user notifications related to token management
    and other system events.
    """

    def __init__(self):
        self._active_websockets: Dict[str, Set[Any]] = {}  # user_id -> set of websockets
        logger.info("[NOTIFICATION-SERVICE-INIT] User notification service initialized")

    async def notify_token_expiry_warning(self, user_id: str, expires_in_minutes: int) -> bool:
        """
        Notify user that their Spotify token will expire soon.
        
        Args:
            user_id: User to notify
            expires_in_minutes: Minutes until token expires
            
        Returns:
            True if notification sent successfully
        """
        try:
            notification_id = f"token-warn-{user_id}-{int(datetime.now().timestamp())}"
            
            notification = UserNotification(
                id=notification_id,
                user_id=user_id,
                notification_type=NotificationType.TOKEN_EXPIRY_WARNING,
                priority=NotificationPriority.MEDIUM,
                title="Spotify Session Expiring Soon",
                message=f"Your Spotify session will expire in {expires_in_minutes} minutes. "
                       f"Don't worry - we'll try to refresh it automatically.",
                metadata={"expires_in_minutes": expires_in_minutes},
                expires_at=datetime.now(timezone.utc) + timedelta(hours=1)
            )
            
            return await self._send_notification(notification)
            
        except Exception as e:
            logger.error(
                "[NOTIFICATION-ERROR-001] Failed to send token expiry warning",
                extra={"user_id": user_id, "error": str(e)},
                exc_info=True
            )
            return False

    async def notify_token_expired(self, user_id: str) -> bool:
        """
        Notify user that their Spotify token has expired.
        
        Args:
            user_id: User to notify
            
        Returns:
            True if notification sent successfully
        """
        try:
            notification_id = f"token-expired-{user_id}-{int(datetime.now().timestamp())}"
            
            notification = UserNotification(
                id=notification_id,
                user_id=user_id,
                notification_type=NotificationType.TOKEN_EXPIRED,
                priority=NotificationPriority.HIGH,
                title="Spotify Session Expired",
                message="Your Spotify session has expired. We're attempting to refresh it automatically.",
                expires_at=datetime.now(timezone.utc) + timedelta(hours=2)
            )
            
            return await self._send_notification(notification)
            
        except Exception as e:
            logger.error(
                "[NOTIFICATION-ERROR-002] Failed to send token expired notification",
                extra={"user_id": user_id, "error": str(e)},
                exc_info=True
            )
            return False

    async def notify_reauth_required(self, user_id: str, reason: str = None) -> bool:
        """
        Notify user that they need to re-authenticate with Spotify.
        
        Args:
            user_id: User to notify
            reason: Optional reason why re-authentication is needed
            
        Returns:
            True if notification sent successfully
        """
        try:
            notification_id = f"reauth-{user_id}-{int(datetime.now().timestamp())}"
            
            reason_text = f" Reason: {reason}" if reason else ""
            
            notification = UserNotification(
                id=notification_id,
                user_id=user_id,
                notification_type=NotificationType.REAUTH_REQUIRED,
                priority=NotificationPriority.CRITICAL,
                title="Spotify Re-Authentication Required",
                message=f"Please log in to Spotify again to continue using music features.{reason_text}",
                action_url="/auth/login",
                action_text="Log In to Spotify",
                metadata={"reason": reason} if reason else {},
                expires_at=datetime.now(timezone.utc) + timedelta(days=1)
            )
            
            return await self._send_notification(notification)
            
        except Exception as e:
            logger.error(
                "[NOTIFICATION-ERROR-003] Failed to send reauth required notification",
                extra={"user_id": user_id, "error": str(e)},
                exc_info=True
            )
            return False

    async def notify_refresh_failed(self, user_id: str, error_message: str) -> bool:
        """
        Notify user that token refresh failed.
        
        Args:
            user_id: User to notify
            error_message: Error message from refresh attempt
            
        Returns:
            True if notification sent successfully
        """
        try:
            notification_id = f"refresh-failed-{user_id}-{int(datetime.now().timestamp())}"
            
            notification = UserNotification(
                id=notification_id,
                user_id=user_id,
                notification_type=NotificationType.REFRESH_FAILED,
                priority=NotificationPriority.HIGH,
                title="Spotify Connection Issue",
                message="We couldn't refresh your Spotify connection. Please try logging in again.",
                action_url="/auth/login",
                action_text="Re-connect Spotify",
                metadata={"error_message": error_message},
                expires_at=datetime.now(timezone.utc) + timedelta(hours=6)
            )
            
            return await self._send_notification(notification)
            
        except Exception as e:
            logger.error(
                "[NOTIFICATION-ERROR-004] Failed to send refresh failed notification",
                extra={"user_id": user_id, "error": str(e)},
                exc_info=True
            )
            return False

    async def notify_service_restored(self, user_id: str) -> bool:
        """
        Notify user that Spotify service has been restored.
        
        Args:
            user_id: User to notify
            
        Returns:
            True if notification sent successfully
        """
        try:
            notification_id = f"service-restored-{user_id}-{int(datetime.now().timestamp())}"
            
            notification = UserNotification(
                id=notification_id,
                user_id=user_id,
                notification_type=NotificationType.SERVICE_RESTORED,
                priority=NotificationPriority.LOW,
                title="Spotify Connection Restored",
                message="Your Spotify connection has been successfully restored. All music features are now available.",
                expires_at=datetime.now(timezone.utc) + timedelta(hours=1)
            )
            
            return await self._send_notification(notification)
            
        except Exception as e:
            logger.error(
                "[NOTIFICATION-ERROR-005] Failed to send service restored notification",
                extra={"user_id": user_id, "error": str(e)},
                exc_info=True
            )
            return False

    async def _send_notification(self, notification: UserNotification) -> bool:
        """
        Send notification through all available channels.
        
        Args:
            notification: Notification to send
            
        Returns:
            True if sent successfully through at least one channel
        """
        success = False
        
        try:
            # Store notification in database
            db_success = await self._store_notification_in_db(notification)
            if db_success:
                success = True
                
            # Send via WebSocket if user has active connections
            ws_success = await self._send_websocket_notification(notification)
            if ws_success:
                success = True
                
            logger.info(
                "[NOTIFICATION-SEND-001] Notification sent",
                extra={
                    "notification_id": notification.id,
                    "user_id": notification.user_id,
                    "type": notification.notification_type.value,
                    "db_success": db_success,
                    "ws_success": ws_success
                }
            )
            
            return success
            
        except Exception as e:
            logger.error(
                "[NOTIFICATION-ERROR-006] Error sending notification",
                extra={
                    "notification_id": notification.id,
                    "user_id": notification.user_id,
                    "error": str(e)
                },
                exc_info=True
            )
            return False

    async def _store_notification_in_db(self, notification: UserNotification) -> bool:
        """Store notification in database for persistence"""
        try:
            notification_data = {
                "id": notification.id,
                "user_id": notification.user_id,
                "notification_type": notification.notification_type.value,
                "priority": notification.priority.value,
                "title": notification.title,
                "message": notification.message,
                "action_url": notification.action_url,
                "action_text": notification.action_text,
                "metadata": json.dumps(notification.metadata) if notification.metadata else None,
                "created_at": notification.created_at.isoformat(),
                "expires_at": notification.expires_at.isoformat() if notification.expires_at else None,
                "read": notification.read,
                "dismissed": notification.dismissed
            }
            
            await database.create_record("notifications", notification_data)
            return True
            
        except Exception as e:
            logger.error(
                "[NOTIFICATION-ERROR-007] Failed to store notification in database",
                extra={
                    "notification_id": notification.id,
                    "user_id": notification.user_id,
                    "error": str(e)
                },
                exc_info=True
            )
            return False

    async def _send_websocket_notification(self, notification: UserNotification) -> bool:
        """Send notification via WebSocket to active user sessions"""
        try:
            user_websockets = self._active_websockets.get(notification.user_id, set())
            
            if not user_websockets:
                logger.debug(
                    "[NOTIFICATION-WS-001] No active WebSocket connections for user",
                    extra={"user_id": notification.user_id}
                )
                return False
            
            # Prepare WebSocket message
            ws_message = {
                "type": "notification",
                "data": notification.to_dict()
            }
            
            # Send to all active connections for this user
            sent_count = 0
            failed_connections = []
            
            for websocket in list(user_websockets):  # Convert to list to avoid modification during iteration
                try:
                    await websocket.send_text(json.dumps(ws_message))
                    sent_count += 1
                except Exception as e:
                    logger.warning(
                        "[NOTIFICATION-WS-002] Failed to send to WebSocket connection",
                        extra={
                            "user_id": notification.user_id,
                            "error": str(e)
                        }
                    )
                    failed_connections.append(websocket)
            
            # Remove failed connections
            for failed_ws in failed_connections:
                user_websockets.discard(failed_ws)
            
            logger.debug(
                "[NOTIFICATION-WS-003] WebSocket notification sent",
                extra={
                    "notification_id": notification.id,
                    "user_id": notification.user_id,
                    "sent_count": sent_count,
                    "failed_count": len(failed_connections)
                }
            )
            
            return sent_count > 0
            
        except Exception as e:
            logger.error(
                "[NOTIFICATION-ERROR-008] Error sending WebSocket notification",
                extra={
                    "notification_id": notification.id,
                    "user_id": notification.user_id,
                    "error": str(e)
                },
                exc_info=True
            )
            return False

    async def get_user_notifications(self, user_id: str, 
                                   include_read: bool = False,
                                   limit: int = 50) -> List[UserNotification]:
        """
        Get notifications for a user.
        
        Args:
            user_id: User ID to get notifications for
            include_read: Whether to include read notifications
            limit: Maximum number of notifications to return
            
        Returns:
            List of user notifications
        """
        try:
            # Build query filters
            filters = {"user_id": user_id}
            if not include_read:
                filters["read"] = False
                
            # Query database
            notifications_data = await database.query_records(
                "notifications",
                filters=filters,
                order_by={"created_at": "DESC"},
                limit=limit
            )
            
            # Convert to notification objects
            notifications = []
            for data in notifications_data:
                try:
                    # Parse metadata JSON
                    metadata = json.loads(data.get("metadata", "{}")) if data.get("metadata") else {}
                    
                    # Parse datetime fields
                    created_at = None
                    if data.get("created_at"):
                        created_at = datetime.fromisoformat(data["created_at"].replace('Z', '+00:00'))
                    
                    expires_at = None
                    if data.get("expires_at"):
                        expires_at = datetime.fromisoformat(data["expires_at"].replace('Z', '+00:00'))
                    
                    notification = UserNotification(
                        id=data["id"],
                        user_id=data["user_id"],
                        notification_type=NotificationType(data["notification_type"]),
                        priority=NotificationPriority(data["priority"]),
                        title=data["title"],
                        message=data["message"],
                        action_url=data.get("action_url"),
                        action_text=data.get("action_text"),
                        metadata=metadata,
                        created_at=created_at,
                        expires_at=expires_at,
                        read=data.get("read", False),
                        dismissed=data.get("dismissed", False)
                    )
                    
                    notifications.append(notification)
                    
                except Exception as e:
                    logger.warning(
                        "[NOTIFICATION-ERROR-009] Failed to parse notification data",
                        extra={
                            "user_id": user_id,
                            "notification_id": data.get("id"),
                            "error": str(e)
                        }
                    )
            
            return notifications
            
        except Exception as e:
            logger.error(
                "[NOTIFICATION-ERROR-010] Failed to get user notifications",
                extra={"user_id": user_id, "error": str(e)},
                exc_info=True
            )
            return []

    async def mark_notification_read(self, notification_id: str, user_id: str) -> bool:
        """Mark a notification as read"""
        try:
            await database.update_record(
                "notifications",
                notification_id,
                {"read": True},
                additional_filters={"user_id": user_id}
            )
            
            logger.debug(
                "[NOTIFICATION-UPDATE-001] Notification marked as read",
                extra={"notification_id": notification_id, "user_id": user_id}
            )
            
            return True
            
        except Exception as e:
            logger.error(
                "[NOTIFICATION-ERROR-011] Failed to mark notification as read",
                extra={
                    "notification_id": notification_id,
                    "user_id": user_id,
                    "error": str(e)
                },
                exc_info=True
            )
            return False

    async def dismiss_notification(self, notification_id: str, user_id: str) -> bool:
        """Dismiss a notification"""
        try:
            await database.update_record(
                "notifications",
                notification_id,
                {"dismissed": True, "read": True},
                additional_filters={"user_id": user_id}
            )
            
            logger.debug(
                "[NOTIFICATION-UPDATE-002] Notification dismissed",
                extra={"notification_id": notification_id, "user_id": user_id}
            )
            
            return True
            
        except Exception as e:
            logger.error(
                "[NOTIFICATION-ERROR-012] Failed to dismiss notification",
                extra={
                    "notification_id": notification_id,
                    "user_id": user_id,
                    "error": str(e)
                },
                exc_info=True
            )
            return False

    def register_websocket(self, user_id: str, websocket: Any):
        """Register a WebSocket connection for a user"""
        if user_id not in self._active_websockets:
            self._active_websockets[user_id] = set()
        
        self._active_websockets[user_id].add(websocket)
        
        logger.debug(
            "[NOTIFICATION-WS-004] WebSocket registered",
            extra={
                "user_id": user_id,
                "active_connections": len(self._active_websockets[user_id])
            }
        )

    def unregister_websocket(self, user_id: str, websocket: Any):
        """Unregister a WebSocket connection for a user"""
        if user_id in self._active_websockets:
            self._active_websockets[user_id].discard(websocket)
            
            # Clean up empty sets
            if not self._active_websockets[user_id]:
                del self._active_websockets[user_id]
            
            logger.debug(
                "[NOTIFICATION-WS-005] WebSocket unregistered",
                extra={
                    "user_id": user_id,
                    "remaining_connections": len(self._active_websockets.get(user_id, []))
                }
            )


# Global notification service instance
user_notification_service = UserNotificationService()


# Convenience functions for easy integration
async def notify_user_token_expiry_warning(user_id: str, expires_in_minutes: int) -> bool:
    """Notify user that their token will expire soon"""
    return await user_notification_service.notify_token_expiry_warning(user_id, expires_in_minutes)


async def notify_user_reauth_required(user_id: str, reason: str = None) -> bool:
    """Notify user that re-authentication is required"""
    return await user_notification_service.notify_reauth_required(user_id, reason)


async def notify_user_refresh_failed(user_id: str, error_message: str) -> bool:
    """Notify user that token refresh failed"""
    return await user_notification_service.notify_refresh_failed(user_id, error_message)


async def get_user_notifications(user_id: str, include_read: bool = False) -> List[Dict[str, Any]]:
    """Get notifications for a user as dictionaries"""
    notifications = await user_notification_service.get_user_notifications(user_id, include_read)
    return [notification.to_dict() for notification in notifications]
