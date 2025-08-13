"""
Redis Pub/Sub for WebSocket Scaling Module

This module implements Redis-based pub/sub messaging for horizontal scaling
of WebSocket connections across multiple application instances. It enables
real-time event broadcasting to all connected clients regardless of which
server instance they're connected to.

Key Features:
- Multi-instance WebSocket message broadcasting
- Redis/Dragonfly pub/sub pattern implementation
- Async event handling with proper error recovery
- Room-based message targeting
- Message serialization and deserialization
- Connection pooling and retry logic
- Health monitoring and diagnostics

Architecture:
- Publishers: Send events to Redis channels
- Subscribers: Listen for events and broadcast to WebSocket clients
- Channel Pattern: Uses structured channel names for routing
- Message Format: JSON serialized with metadata and payload

Channel Naming Convention:
- Global broadcasts: "musicbingo:broadcast:all"
- Game-specific: "musicbingo:game:{game_id}"
- User-specific: "musicbingo:user:{user_id}"
- Room-specific: "musicbingo:room:{room_code}"

Message Structure:
{
    "event": "event_name",
    "data": {...},
    "timestamp": "ISO timestamp",
    "source_instance": "instance_id",
    "target": "all|game|user|room",
    "target_id": "optional_target_identifier"
}
"""

import asyncio
import json
import logging
import uuid
from typing import Dict, Any, Optional, Callable
from datetime import datetime, timezone
from contextlib import asynccontextmanager

import redis.asyncio as redis
from app.config import get_config
from app.socket_handler import sio

logger = logging.getLogger("music_bingo")
config = get_config()


class RedisPubSubManager:
    """
    Manages Redis pub/sub connections for WebSocket scaling.

    This class handles the Redis pub/sub infrastructure needed to scale
    WebSocket connections across multiple application instances.
    """

    def __init__(self):
        self.redis_client: Optional[redis.Redis] = None
        self.pubsub: Optional[redis.client.PubSub] = None
        self.instance_id = str(uuid.uuid4())[:8]
        self.subscriptions: Dict[str, Callable] = {}
        self.is_running = False
        self._listener_task: Optional[asyncio.Task] = None

        # Channel patterns
        self.BROADCAST_CHANNEL = "musicbingo:broadcast:all"
        self.GAME_CHANNEL_PATTERN = "musicbingo:game:{}"
        self.USER_CHANNEL_PATTERN = "musicbingo:user:{}"
        self.ROOM_CHANNEL_PATTERN = "musicbingo:room:{}"

    async def connect(self) -> bool:
        """
        Establish connection to Redis and set up pub/sub.

        Returns:
            bool: True if connection successful, False otherwise
        """
        try:
            # Create Redis connection using existing config
            self.redis_client = redis.Redis(
                host=config.redis_host,
                port=config.redis_port,
                password=config.redis_password,
                db=config.redis_db,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_keepalive=True,
                socket_keepalive_options={},
                health_check_interval=30,
                retry_on_timeout=True,
                max_connections=20
            )

            # Test connection
            await self.redis_client.ping()

            # Create pub/sub instance
            self.pubsub = self.redis_client.pubsub()

            logger.info(
                f"[REDIS-PUBSUB] Connected to Redis pub/sub on {config.redis_host}:{config.redis_port}",
                extra={"instance_id": self.instance_id}
            )

            return True

        except Exception as e:
            logger.error(
                f"[REDIS-PUBSUB] Failed to connect to Redis: {e}",
                extra={"instance_id": self.instance_id}
            )
            return False

    async def disconnect(self):
        """Clean up Redis connections."""
        try:
            self.is_running = False

            # Cancel listener task
            if self._listener_task and not self._listener_task.done():
                self._listener_task.cancel()
                try:
                    await self._listener_task
                except asyncio.CancelledError:
                    pass

            # Close pub/sub
            if self.pubsub:
                await self.pubsub.unsubscribe()
                await self.pubsub.close()

            # Close Redis connection
            if self.redis_client:
                await self.redis_client.close()

            logger.info(
                "[REDIS-PUBSUB] Disconnected from Redis pub/sub",
                extra={"instance_id": self.instance_id}
            )

        except Exception as e:
            logger.error(
                f"[REDIS-PUBSUB] Error during disconnect: {e}",
                extra={"instance_id": self.instance_id}
            )

    async def subscribe_to_channels(self):
        """Subscribe to necessary Redis channels."""
        if not self.pubsub:
            raise RuntimeError("Pub/sub not initialized")

        try:
            # Subscribe to global broadcast channel
            await self.pubsub.subscribe(self.BROADCAST_CHANNEL)

            # Subscribe to pattern-based channels for dynamic routing
            await self.pubsub.psubscribe("musicbingo:game:*")
            await self.pubsub.psubscribe("musicbingo:user:*")
            await self.pubsub.psubscribe("musicbingo:room:*")

            logger.info(
                "[REDIS-PUBSUB] Subscribed to channels",
                extra={"instance_id": self.instance_id}
            )

        except Exception as e:
            logger.error(
                f"[REDIS-PUBSUB] Failed to subscribe to channels: {e}",
                extra={"instance_id": self.instance_id}
            )
            raise

    async def start_listener(self):
        """Start the Redis message listener."""
        if not self.pubsub:
            raise RuntimeError("Pub/sub not initialized")

        self.is_running = True
        self._listener_task = asyncio.create_task(self._message_listener())

        logger.info(
            "[REDIS-PUBSUB] Started message listener",
            extra={"instance_id": self.instance_id}
        )

    async def _message_listener(self):
        """Main message listening loop."""
        try:
            while self.is_running:
                try:
                    # Get message with timeout
                    message = await asyncio.wait_for(
                        self.pubsub.get_message(ignore_subscribe_messages=True),
                        timeout=1.0
                    )

                    if message:
                        await self._handle_message(message)

                except asyncio.TimeoutError:
                    # Normal timeout, continue loop
                    continue

                except Exception as e:
                    logger.error(
                        f"[REDIS-PUBSUB] Error in message listener: {e}",
                        extra={"instance_id": self.instance_id}
                    )
                    # Brief pause before continuing
                    await asyncio.sleep(1)

        except asyncio.CancelledError:
            logger.info(
                "[REDIS-PUBSUB] Message listener cancelled",
                extra={"instance_id": self.instance_id}
            )
            raise
        except Exception as e:
            logger.error(
                f"[REDIS-PUBSUB] Fatal error in message listener: {e}",
                extra={"instance_id": self.instance_id}
            )

    async def _handle_message(self, message: Dict[str, Any]):
        """
        Handle incoming Redis message and broadcast to WebSocket clients.

        Args:
            message: Redis pub/sub message
        """
        try:
            # Parse message data
            channel = message['channel']
            data = message['data']

            if not isinstance(data, str):
                return

            # Deserialize JSON message
            try:
                event_data = json.loads(data)
            except json.JSONDecodeError:
                logger.warning(
                    f"[REDIS-PUBSUB] Invalid JSON message: {data}",
                    extra={"instance_id": self.instance_id}
                )
                return

            # Skip messages from this instance to avoid loops
            if event_data.get('source_instance') == self.instance_id:
                return

            # Extract event details
            event_name = event_data.get('event')
            payload = event_data.get('data', {})
            target = event_data.get('target', 'all')
            target_id = event_data.get('target_id')

            if not event_name:
                logger.warning(
                    "[REDIS-PUBSUB] Message missing event name",
                    extra={"instance_id": self.instance_id}
                )
                return

            # Route message to appropriate WebSocket clients
            await self._route_to_websockets(
                event_name, payload, channel, target, target_id
            )

            logger.debug(
                f"[REDIS-PUBSUB] Handled message: {event_name}",
                extra={
                    "instance_id": self.instance_id,
                    "channel": channel,
                    "target": target
                }
            )

        except Exception as e:
            logger.error(
                f"[REDIS-PUBSUB] Error handling message: {e}",
                extra={"instance_id": self.instance_id}
            )

    async def _route_to_websockets(
        self,
        event_name: str,
        payload: Dict[str, Any],
        channel: str,
        target: str,
        target_id: Optional[str]
    ):
        """
        Route message to appropriate WebSocket clients.

        Args:
            event_name: Name of the event to emit
            payload: Event data payload
            channel: Redis channel name
            target: Target type (all, game, user, room)
            target_id: Optional target identifier
        """
        try:
            if target == 'all' or channel == self.BROADCAST_CHANNEL:
                # Broadcast to all connected clients
                await sio.emit(event_name, payload)

            elif target == 'game' and target_id:
                # Send to specific game room
                await sio.emit(event_name, payload, room=f"game_{target_id}")

            elif target == 'user' and target_id:
                # Send to specific user
                await sio.emit(event_name, payload, room=f"user_{target_id}")

            elif target == 'room' and target_id:
                # Send to specific room code
                await sio.emit(event_name, payload, room=f"room_{target_id}")

            else:
                logger.warning(
                    f"[REDIS-PUBSUB] Unknown target type: {target}",
                    extra={"instance_id": self.instance_id}
                )

        except Exception as e:
            logger.error(
                f"[REDIS-PUBSUB] Error routing to WebSockets: {e}",
                extra={"instance_id": self.instance_id}
            )

    async def publish_event(
        self,
        event_name: str,
        data: Dict[str, Any],
        target: str = 'all',
        target_id: Optional[str] = None
    ):
        """
        Publish event to Redis for broadcasting to all instances.

        Args:
            event_name: Name of the event
            data: Event data
            target: Target type (all, game, user, room)
            target_id: Optional target identifier
        """
        if not self.redis_client:
            logger.error(
                "[REDIS-PUBSUB] Cannot publish - Redis client not connected",
                extra={"instance_id": self.instance_id}
            )
            return

        try:
            # Determine channel based on target
            if target == 'all':
                channel = self.BROADCAST_CHANNEL
            elif target == 'game' and target_id:
                channel = self.GAME_CHANNEL_PATTERN.format(target_id)
            elif target == 'user' and target_id:
                channel = self.USER_CHANNEL_PATTERN.format(target_id)
            elif target == 'room' and target_id:
                channel = self.ROOM_CHANNEL_PATTERN.format(target_id)
            else:
                logger.error(
                    f"[REDIS-PUBSUB] Invalid target: {target}",
                    extra={"instance_id": self.instance_id}
                )
                return

            # Create message payload
            message = {
                'event': event_name,
                'data': data,
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'source_instance': self.instance_id,
                'target': target,
                'target_id': target_id
            }

            # Publish to Redis
            await self.redis_client.publish(channel, json.dumps(message))

            logger.debug(
                f"[REDIS-PUBSUB] Published event: {event_name}",
                extra={
                    "instance_id": self.instance_id,
                    "channel": channel,
                    "target": target
                }
            )

        except Exception as e:
            logger.error(
                f"[REDIS-PUBSUB] Error publishing event: {e}",
                extra={"instance_id": self.instance_id}
            )

    async def health_check(self) -> Dict[str, Any]:
        """
        Perform health check of Redis pub/sub system.

        Returns:
            Dict containing health status and metrics
        """
        health_data = {
            'status': 'healthy',
            'instance_id': self.instance_id,
            'connected': False,
            'listener_running': self.is_running,
            'subscriptions': 0,
            'errors': []
        }

        try:
            if self.redis_client:
                # Test Redis connection
                await self.redis_client.ping()
                health_data['connected'] = True

                # Get subscription count
                if self.pubsub:
                    health_data['subscriptions'] = len(self.pubsub.channels) + len(self.pubsub.patterns)

        except Exception as e:
            health_data['status'] = 'unhealthy'
            health_data['errors'].append(f"Redis connection error: {str(e)}")

        # Check listener task
        if self._listener_task and self._listener_task.done() and not self._listener_task.cancelled():
            try:
                # Check if task completed with exception
                self._listener_task.result()
            except Exception as e:
                health_data['status'] = 'unhealthy'
                health_data['errors'].append(f"Listener task error: {str(e)}")

        return health_data


# Global pub/sub manager instance
pubsub_manager = RedisPubSubManager()


@asynccontextmanager
async def redis_pubsub_lifespan():
    """Context manager for Redis pub/sub lifecycle management."""
    try:
        # Connect and start
        if await pubsub_manager.connect():
            await pubsub_manager.subscribe_to_channels()
            await pubsub_manager.start_listener()
            logger.info("[REDIS-PUBSUB] System started successfully")
        else:
            logger.error("[REDIS-PUBSUB] Failed to start system")

        yield pubsub_manager

    finally:
        # Cleanup
        await pubsub_manager.disconnect()
        logger.info("[REDIS-PUBSUB] System stopped")


# Convenience functions for common operations
async def broadcast_to_all(event_name: str, data: Dict[str, Any]):
    """Broadcast event to all connected clients across all instances."""
    await pubsub_manager.publish_event(event_name, data, target='all')


async def broadcast_to_game(game_id: str, event_name: str, data: Dict[str, Any]):
    """Broadcast event to all clients in a specific game."""
    await pubsub_manager.publish_event(event_name, data, target='game', target_id=game_id)


async def send_to_user(user_id: str, event_name: str, data: Dict[str, Any]):
    """Send event to a specific user across all instances."""
    await pubsub_manager.publish_event(event_name, data, target='user', target_id=user_id)


async def broadcast_to_room(room_code: str, event_name: str, data: Dict[str, Any]):
    """Broadcast event to all clients in a room."""
    await pubsub_manager.publish_event(event_name, data, target='room', target_id=room_code)
