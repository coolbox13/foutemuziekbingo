"""
Redis/Dragonfly-based session storage for production scalability.
Replaces in-memory session storage with distributed session management.
"""

import json
import logging
import asyncio
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone, timedelta
import redis.asyncio as redis
from app.config import get_config

logger = logging.getLogger("music_bingo")


class RedisSessionStore:
    """
    Async Redis/Dragonfly session store with TTL and cleanup functionality.
    Thread-safe and horizontally scalable.
    """
    
    def __init__(self, redis_url: str = None, redis_password: str = None):
        """
        Initialize Redis session store.
        
        Args:
            redis_url: Redis connection URL (defaults to config)
            redis_password: Redis password (defaults to config)
        """
        config = get_config()
        self.redis_url = redis_url or config.redis_url
        self.redis_password = redis_password or config.redis_password
        self.session_lifetime_hours = config.session_lifetime_hours
        self.max_sessions_per_user = config.max_sessions_per_user
        
        # Redis client (will be initialized on first use)
        self._redis_client: Optional[redis.Redis] = None
        self._connection_lock = asyncio.Lock()
        
        # Session key prefixes for organization
        self.session_prefix = "session:"
        self.user_sessions_prefix = "user_sessions:"
        self.session_stats_key = "session_stats"
        
    async def _get_redis(self) -> redis.Redis:
        """Get or create Redis connection with error handling."""
        if self._redis_client is None:
            async with self._connection_lock:
                if self._redis_client is None:
                    try:
                        # Parse Redis URL and create connection
                        connection_kwargs = {"decode_responses": True}
                        if self.redis_password:
                            connection_kwargs["password"] = self.redis_password
                        
                        self._redis_client = redis.from_url(
                            self.redis_url, 
                            **connection_kwargs,
                            socket_connect_timeout=5,
                            socket_timeout=5,
                            retry_on_timeout=True,
                            health_check_interval=30
                        )
                        
                        # Test connection
                        await self._redis_client.ping()
                        logger.info(f"Redis session store connected to {self.redis_url}")
                        
                    except Exception as e:
                        logger.error(f"Failed to connect to Redis: {e}")
                        # In development, we can fallback to memory, but log a warning
                        config = get_config()
                        if config.app_env == "development":
                            logger.warning("Redis connection failed, using in-memory fallback for development")
                            raise RedisConnectionError(f"Redis unavailable: {e}")
                        else:
                            # In production, Redis is required
                            raise RedisConnectionError(f"Redis connection failed in production: {e}")
        
        return self._redis_client
    
    async def create_session(
        self, 
        user_id: str,
        spotify_token_info: Dict[str, Any],
        user_data: Dict[str, Any],
        csrf_token: str
    ) -> str:
        """
        Create a new session with TTL.
        
        Args:
            user_id: User identifier
            spotify_token_info: Spotify OAuth tokens
            user_data: User profile data
            csrf_token: CSRF protection token
            
        Returns:
            Session token
        """
        from app.secure_session import generate_session_token
        
        session_token = generate_session_token()
        
        # Clean up old sessions for this user first
        await self.cleanup_user_sessions(user_id)
        
        # Create session data
        session_data = {
            "user_id": user_id,
            "token_info": spotify_token_info,
            "user": user_data,
            "csrf_token": csrf_token,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "expires_at": (
                datetime.now(timezone.utc) + timedelta(hours=self.session_lifetime_hours)
            ).isoformat(),
            "last_activity": datetime.now(timezone.utc).isoformat(),
        }
        
        try:
            redis_client = await self._get_redis()
            
            # Store session with TTL (convert hours to seconds)
            ttl_seconds = self.session_lifetime_hours * 3600
            session_key = f"{self.session_prefix}{session_token}"
            
            await redis_client.setex(
                session_key,
                ttl_seconds,
                json.dumps(session_data, default=str)
            )
            
            # Add to user's session list for cleanup tracking
            user_sessions_key = f"{self.user_sessions_prefix}{user_id}"
            await redis_client.lpush(user_sessions_key, session_token)
            await redis_client.expire(user_sessions_key, ttl_seconds)
            
            # Update session stats
            await redis_client.hincrby(self.session_stats_key, "total_created", 1)
            
            logger.info(
                "[REDIS-SESSION-CREATE] Session created",
                extra={
                    "user_id": user_id,
                    "session_token": session_token[:8] + "...",
                    "ttl_hours": self.session_lifetime_hours,
                }
            )
            
            return session_token
            
        except Exception as e:
            logger.error(f"[REDIS-SESSION-CREATE] Failed to create session: {e}")
            raise SessionStorageError(f"Failed to create session: {e}")
    
    async def get_session(self, session_token: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve session data and update last activity.
        
        Args:
            session_token: Session token to retrieve
            
        Returns:
            Session data if valid, None if expired/not found
        """
        if not session_token:
            return None
        
        try:
            redis_client = await self._get_redis()
            session_key = f"{self.session_prefix}{session_token}"
            
            # Get session data
            session_json = await redis_client.get(session_key)
            if not session_json:
                logger.info(
                    "[REDIS-SESSION-GET] Session not found",
                    extra={"session_token": session_token[:8] + "..."}
                )
                return None
            
            session_data = json.loads(session_json)
            
            # Check expiration (double-check even with Redis TTL)
            expires_at = datetime.fromisoformat(session_data["expires_at"])
            if datetime.now(timezone.utc) > expires_at:
                logger.info(
                    "[REDIS-SESSION-GET] Session expired",
                    extra={
                        "session_token": session_token[:8] + "...",
                        "expires_at": session_data["expires_at"],
                    }
                )
                # Clean up expired session
                await self.invalidate_session(session_token)
                return None
            
            # Update last activity and extend TTL
            session_data["last_activity"] = datetime.now(timezone.utc).isoformat()
            ttl_seconds = self.session_lifetime_hours * 3600
            
            await redis_client.setex(
                session_key,
                ttl_seconds,
                json.dumps(session_data, default=str)
            )
            
            return session_data
            
        except json.JSONDecodeError as e:
            logger.warning(f"[REDIS-SESSION-GET] Invalid session JSON: {e}")
            await self.invalidate_session(session_token)
            return None
        except Exception as e:
            logger.error(f"[REDIS-SESSION-GET] Error retrieving session: {e}")
            return None
    
    async def invalidate_session(self, session_token: str) -> bool:
        """
        Invalidate a session.
        
        Args:
            session_token: Session token to invalidate
            
        Returns:
            True if session was found and invalidated
        """
        if not session_token:
            return False
        
        try:
            redis_client = await self._get_redis()
            session_key = f"{self.session_prefix}{session_token}"
            
            # Get user_id before deletion for cleanup
            session_json = await redis_client.get(session_key)
            user_id = None
            if session_json:
                try:
                    session_data = json.loads(session_json)
                    user_id = session_data.get("user_id")
                except json.JSONDecodeError:
                    pass
            
            # Delete session
            deleted = await redis_client.delete(session_key)
            
            # Remove from user's session list
            if user_id:
                user_sessions_key = f"{self.user_sessions_prefix}{user_id}"
                await redis_client.lrem(user_sessions_key, 1, session_token)
            
            if deleted:
                logger.info(
                    "[REDIS-SESSION-INVALIDATE] Session invalidated",
                    extra={"session_token": session_token[:8] + "...", "user_id": user_id}
                )
                
            return bool(deleted)
            
        except Exception as e:
            logger.error(f"[REDIS-SESSION-INVALIDATE] Error invalidating session: {e}")
            return False
    
    async def update_session_token_info(
        self, 
        session_token: str, 
        new_token_info: Dict[str, Any]
    ) -> bool:
        """
        Update token info for a session (e.g., after Spotify token refresh).
        
        Args:
            session_token: Session token to update
            new_token_info: New Spotify token information
            
        Returns:
            True if update was successful
        """
        if not session_token:
            return False
        
        try:
            redis_client = await self._get_redis()
            session_key = f"{self.session_prefix}{session_token}"
            
            # Get existing session
            session_json = await redis_client.get(session_key)
            if not session_json:
                return False
            
            session_data = json.loads(session_json)
            session_data["token_info"] = new_token_info
            session_data["last_activity"] = datetime.now(timezone.utc).isoformat()
            
            # Update with existing TTL
            ttl = await redis_client.ttl(session_key)
            if ttl > 0:
                await redis_client.setex(
                    session_key,
                    ttl,
                    json.dumps(session_data, default=str)
                )
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"[REDIS-SESSION-UPDATE] Error updating session token info: {e}")
            return False
    
    async def cleanup_user_sessions(
        self, 
        user_id: str, 
        keep_latest: int = None
    ) -> int:
        """
        Clean up old sessions for a user, keeping only the most recent ones.
        
        Args:
            user_id: User identifier
            keep_latest: Number of recent sessions to keep (defaults to config)
            
        Returns:
            Number of sessions cleaned up
        """
        if keep_latest is None:
            keep_latest = self.max_sessions_per_user - 1
        
        try:
            redis_client = await self._get_redis()
            user_sessions_key = f"{self.user_sessions_prefix}{user_id}"
            
            # Get all session tokens for this user
            session_tokens = await redis_client.lrange(user_sessions_key, 0, -1)
            
            if len(session_tokens) <= keep_latest:
                return 0
            
            # Get session creation times to sort by age
            session_times = []
            for token in session_tokens:
                session_key = f"{self.session_prefix}{token}"
                session_json = await redis_client.get(session_key)
                if session_json:
                    try:
                        session_data = json.loads(session_json)
                        created_at = datetime.fromisoformat(session_data["created_at"])
                        session_times.append((token, created_at))
                    except (json.JSONDecodeError, KeyError, ValueError):
                        # Invalid session, mark for removal
                        session_times.append((token, datetime.min.replace(tzinfo=timezone.utc)))
            
            # Sort by creation time (newest first)
            session_times.sort(key=lambda x: x[1], reverse=True)
            
            # Remove old sessions
            sessions_to_remove = session_times[keep_latest:]
            removed_count = 0
            
            for token, _ in sessions_to_remove:
                if await self.invalidate_session(token):
                    removed_count += 1
            
            if removed_count > 0:
                logger.info(
                    "[REDIS-SESSION-CLEANUP] User sessions cleaned up",
                    extra={"user_id": user_id, "removed_count": removed_count}
                )
            
            return removed_count
            
        except Exception as e:
            logger.error(f"[REDIS-SESSION-CLEANUP] Error cleaning up user sessions: {e}")
            return 0
    
    async def cleanup_expired_sessions(self) -> int:
        """
        Clean up expired sessions (Redis TTL should handle this, but this provides stats).
        
        Returns:
            Number of sessions cleaned up
        """
        try:
            redis_client = await self._get_redis()
            
            # Scan for all session keys
            cleaned_count = 0
            async for key in redis_client.scan_iter(match=f"{self.session_prefix}*"):
                session_json = await redis_client.get(key)
                if not session_json:
                    continue
                
                try:
                    session_data = json.loads(session_json)
                    expires_at = datetime.fromisoformat(session_data["expires_at"])
                    
                    if datetime.now(timezone.utc) > expires_at:
                        session_token = key[len(self.session_prefix):]
                        if await self.invalidate_session(session_token):
                            cleaned_count += 1
                        
                except (json.JSONDecodeError, KeyError, ValueError):
                    # Invalid session data, remove it
                    await redis_client.delete(key)
                    cleaned_count += 1
            
            if cleaned_count > 0:
                logger.info(f"[REDIS-SESSION-CLEANUP] Cleaned up {cleaned_count} expired sessions")
                
            return cleaned_count
            
        except Exception as e:
            logger.error(f"[REDIS-SESSION-CLEANUP] Error cleaning up expired sessions: {e}")
            return 0
    
    async def get_session_stats(self) -> Dict[str, Any]:
        """Get statistics about active sessions."""
        try:
            redis_client = await self._get_redis()
            
            # Count active sessions
            active_count = 0
            unique_users = set()
            
            async for key in redis_client.scan_iter(match=f"{self.session_prefix}*"):
                session_json = await redis_client.get(key)
                if session_json:
                    try:
                        session_data = json.loads(session_json)
                        expires_at = datetime.fromisoformat(session_data["expires_at"])
                        
                        if datetime.now(timezone.utc) <= expires_at:
                            active_count += 1
                            user_id = session_data.get("user_id")
                            if user_id:
                                unique_users.add(user_id)
                    except (json.JSONDecodeError, KeyError, ValueError):
                        continue
            
            # Get additional stats from Redis
            stats_data = await redis_client.hgetall(self.session_stats_key)
            total_created = int(stats_data.get("total_created", 0))
            
            return {
                "active_sessions": active_count,
                "unique_users": len(unique_users),
                "total_sessions_created": total_created,
                "storage_type": "Redis/Dragonfly",
                "redis_url": self.redis_url,
            }
            
        except Exception as e:
            logger.error(f"[REDIS-SESSION-STATS] Error getting session stats: {e}")
            return {
                "active_sessions": 0,
                "unique_users": 0,
                "total_sessions_created": 0,
                "storage_type": "Redis/Dragonfly (error)",
                "error": str(e)
            }
    
    async def health_check(self) -> Dict[str, Any]:
        """
        Perform health check on Redis session store.
        
        Returns:
            Health check results
        """
        try:
            redis_client = await self._get_redis()
            
            # Test basic Redis operations
            test_key = "health_check_test"
            await redis_client.set(test_key, "test_value", ex=5)  # 5 second TTL
            test_value = await redis_client.get(test_key)
            await redis_client.delete(test_key)
            
            if test_value != "test_value":
                raise Exception("Redis read/write test failed")
            
            # Get Redis info
            info = await redis_client.info()
            connected_clients = info.get("connected_clients", 0)
            used_memory = info.get("used_memory_human", "unknown")
            
            return {
                "healthy": True,
                "redis_connected": True,
                "connected_clients": connected_clients,
                "used_memory": used_memory,
                "session_prefix": self.session_prefix,
            }
            
        except Exception as e:
            logger.error(f"[REDIS-SESSION-HEALTH] Health check failed: {e}")
            return {
                "healthy": False,
                "redis_connected": False,
                "error": str(e)
            }
    
    async def close(self):
        """Close Redis connection."""
        if self._redis_client:
            await self._redis_client.close()
            self._redis_client = None
            logger.info("Redis session store connection closed")


class RedisConnectionError(Exception):
    """Raised when Redis connection fails."""
    pass


class SessionStorageError(Exception):
    """Raised when session storage operations fail."""
    pass


# Global Redis session store instance
_redis_session_store: Optional[RedisSessionStore] = None


def get_redis_session_store() -> RedisSessionStore:
    """Get the global Redis session store instance."""
    global _redis_session_store
    if _redis_session_store is None:
        _redis_session_store = RedisSessionStore()
    return _redis_session_store


async def cleanup_redis_session_store():
    """Cleanup the global Redis session store."""
    global _redis_session_store
    if _redis_session_store:
        await _redis_session_store.close()
        _redis_session_store = None
