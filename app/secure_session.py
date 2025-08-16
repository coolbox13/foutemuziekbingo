"""
Secure session management with Redis/Dragonfly support and memory fallback.
Provides UUID-based session tokens and secure cookie handling with horizontal scaling.
"""

import uuid
import secrets
import logging
import asyncio
from typing import Optional, Dict, Any
from datetime import datetime, timezone, timedelta
from fastapi import Request, Response, HTTPException
import hashlib
import hmac

logger = logging.getLogger("music_bingo")

# Session configuration constants
SESSION_COOKIE_NAME = "music_bingo_session"

# Lazy import and initialization of Redis store
_redis_store = None
_redis_available = None


async def get_session_store():
    """
    Get the appropriate session store (Redis preferred, memory fallback).
    
    Returns:
        Session store instance (Redis or memory-based)
    """
    global _redis_store, _redis_available
    
    # Try Redis first if we haven't determined availability yet
    if _redis_available is None:
        try:
            from app.redis_session_store import get_redis_session_store, RedisConnectionError
            from app.config import get_config
            
            config = get_config()
            if config.app_env == "test":
                # Always use memory for tests
                _redis_available = False
            else:
                # Test Redis connectivity
                _redis_store = get_redis_session_store()
                health = await _redis_store.health_check()
                _redis_available = health.get("healthy", False)
                
                if _redis_available:
                    logger.info("[SESSION-STORE] Using Redis/Dragonfly session storage")
                else:
                    logger.warning(f"[SESSION-STORE] Redis unhealthy, using memory fallback: {health.get('error', 'unknown')}")
                    
        except Exception as e:
            logger.warning(f"[SESSION-STORE] Redis unavailable, using memory fallback: {e}")
            _redis_available = False
    
    if _redis_available and _redis_store:
        return _redis_store
    else:
        # Return memory-based store
        return MemorySessionStore()


def generate_session_token() -> str:
    """Generate a cryptographically secure session token."""
    return secrets.token_urlsafe(32)


def generate_csrf_token() -> str:
    """Generate a CSRF token for form protection."""
    return secrets.token_urlsafe(16)


def create_session_signature(session_id: str, secret_key: str) -> str:
    """Create a signature for session validation."""
    return hmac.new(
        secret_key.encode(), session_id.encode(), hashlib.sha256
    ).hexdigest()


def verify_session_signature(session_id: str, signature: str, secret_key: str) -> bool:
    """Verify a session signature."""
    expected_signature = create_session_signature(session_id, secret_key)
    return hmac.compare_digest(expected_signature, signature)


async def create_secure_session(
    user_id: str,
    spotify_token_info: Dict[str, Any],
    user_data: Dict[str, Any],
    response: Response,
    secret_key: str,
) -> str:
    """
    Create a secure session with proper token storage.

    Args:
        user_id: User identifier
        spotify_token_info: Spotify OAuth tokens
        user_data: User profile data
        response: FastAPI response object to set cookies
        secret_key: Secret key for signing

    Returns:
        Session token
    """
    session_store = await get_session_store()
    csrf_token = generate_csrf_token()
    
    # Create session using the appropriate store
    if hasattr(session_store, 'create_session'):
        # Redis store
        session_token = await session_store.create_session(
            user_id=user_id,
            spotify_token_info=spotify_token_info,
            user_data=user_data,
            csrf_token=csrf_token
        )
    else:
        # Memory store fallback
        session_token = session_store.create_session(
            user_id=user_id,
            spotify_token_info=spotify_token_info,
            user_data=user_data,
            csrf_token=csrf_token
        )

    # Create signed session cookie
    signature = create_session_signature(session_token, secret_key)
    cookie_value = f"{session_token}.{signature}"

    # Set secure HTTP-only cookie
    from app.config import get_config
    config = get_config()
    secure_cookie = config.app_env == "production"
    
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=cookie_value,
        max_age=config.session_lifetime_hours * 3600,  # Convert to seconds
        httponly=True,  # Prevent JavaScript access
        secure=secure_cookie,  # HTTPS only in production; allow HTTP in development
        samesite="lax",  # CSRF protection
        path="/",  # Available to all routes
    )

    # Expose CSRF token in a separate cookie (readable by JS)
    response.set_cookie(
        key="music_bingo_csrf",
        value=csrf_token,
        max_age=config.session_lifetime_hours * 3600,
        httponly=False,
        path="/",  # Available to all routes
        secure=secure_cookie,
        samesite="lax",
    )

    logger.info(
        "[SESSION-CREATE] Secure session created",
        extra={
            "user_id": user_id,
            "session_token": session_token[:8] + "...",  # Log only first 8 chars
            "store_type": "Redis" if _redis_available else "Memory",
        },
    )

    return session_token


async def get_session_from_request(
    request: Request, secret_key: str
) -> Optional[Dict[str, Any]]:
    """
    Retrieve and validate session from request cookies.

    Args:
        request: FastAPI request object
        secret_key: Secret key for verification

    Returns:
        Session data if valid, None otherwise
    """
    cookie_value = request.cookies.get(SESSION_COOKIE_NAME)
    return await get_session_from_cookie_value(cookie_value, secret_key)


async def get_session_from_cookie_value(
    cookie_value: str, secret_key: str
) -> Optional[Dict[str, Any]]:
    """
    Retrieve and validate session from a raw cookie value.
    Useful for non-FastAPI contexts (e.g., Socket.IO connect handshake).
    """
    if not cookie_value:
        return None

    try:
        # Parse signed cookie
        if "." not in cookie_value:
            logger.warning("[SESSION-GET] Invalid cookie format")
            return None

        session_token, signature = cookie_value.rsplit(".", 1)

        # Verify signature
        if not verify_session_signature(session_token, signature, secret_key):
            logger.warning("[SESSION-GET] Invalid session signature")
            return None

        # Get session data from appropriate store
        session_store = await get_session_store()
        
        if hasattr(session_store, 'get_session'):
            # Redis store
            session_data = await session_store.get_session(session_token)
        else:
            # Memory store fallback
            session_data = session_store.get_session(session_token)
            
        return session_data

    except Exception as e:
        logger.warning(
            "[SESSION-GET] Error retrieving session",
            extra={"error": str(e), "error_type": type(e).__name__},
        )
        return None


async def invalidate_session(session_token: str, response: Response) -> bool:
    """
    Invalidate a session and clear the cookie.

    Args:
        session_token: Session token to invalidate
        response: FastAPI response object to clear cookie

    Returns:
        True if session was found and invalidated
    """
    session_store = await get_session_store()
    
    if hasattr(session_store, 'invalidate_session'):
        # Redis store
        session_found = await session_store.invalidate_session(session_token)
    else:
        # Memory store fallback
        session_found = session_store.invalidate_session(session_token)

    # Clear cookie regardless
    from app.config import get_config
    config = get_config()
    secure_cookie = config.app_env == "production"
    
    response.delete_cookie(
        key=SESSION_COOKIE_NAME, 
        httponly=True, 
        secure=secure_cookie, 
        samesite="lax"
    )
    
    response.delete_cookie(
        key="music_bingo_csrf",
        httponly=False,
        secure=secure_cookie,
        samesite="lax"
    )

    return session_found


async def cleanup_user_sessions(user_id: str, keep_latest: int = None):
    """
    Clean up old sessions for a user, keeping only the most recent ones.

    Args:
        user_id: User identifier
        keep_latest: Number of recent sessions to keep
    """
    session_store = await get_session_store()
    
    if hasattr(session_store, 'cleanup_user_sessions'):
        # Redis store
        await session_store.cleanup_user_sessions(user_id, keep_latest)
    else:
        # Memory store fallback
        session_store.cleanup_user_sessions(user_id, keep_latest)


async def cleanup_expired_sessions():
    """Clean up all expired sessions."""
    session_store = await get_session_store()
    
    if hasattr(session_store, 'cleanup_expired_sessions'):
        # Redis store
        return await session_store.cleanup_expired_sessions()
    else:
        # Memory store fallback
        return session_store.cleanup_expired_sessions()


async def get_session_stats() -> Dict[str, Any]:
    """Get statistics about active sessions."""
    session_store = await get_session_store()
    
    if hasattr(session_store, 'get_session_stats'):
        # Redis store
        return await session_store.get_session_stats()
    else:
        # Memory store fallback
        return session_store.get_session_stats()


def get_sessions_snapshot() -> Dict[str, Dict[str, Any]]:
    """
    Return a shallow snapshot of current sessions for safe iteration.
    Note: This is synchronous for backward compatibility with token maintenance.
    """
    # For backward compatibility, we use the memory store for this operation
    # In production, this should be replaced with proper Redis-based token maintenance
    return MemorySessionStore().get_sessions_snapshot()


def update_session_token_info(
    session_token: str, new_token_info: Dict[str, Any]
) -> None:
    """
    Update the token_info for a given session token if it exists.
    Note: This is synchronous for backward compatibility.
    """
    # For backward compatibility, we try both stores
    # In production, this should be replaced with proper async Redis operations
    try:
        # Try memory store first for backward compatibility
        MemorySessionStore().update_session_token_info(session_token, new_token_info)
        
        # Also update Redis if available (fire and forget)
        async def _update_redis():
            try:
                if _redis_available and _redis_store:
                    await _redis_store.update_session_token_info(session_token, new_token_info)
            except:
                pass
        
        # Run async update in background
        try:
            loop = asyncio.get_event_loop()
            loop.create_task(_update_redis())
        except:
            pass  # Ignore if no event loop
            
    except Exception:
        pass  # Fail silently for backward compatibility


# Utility function for CSRF protection
async def verify_csrf_token(request: Request, provided_token: str, secret_key: str) -> bool:
    """
    Verify CSRF token against the session.

    Args:
        request: FastAPI request object
        provided_token: CSRF token from form/header
        secret_key: Secret key for session verification

    Returns:
        True if CSRF token is valid
    """
    session_data = await get_session_from_request(request, secret_key)
    if not session_data:
        return False

    expected_token = session_data.get("csrf_token")
    if not expected_token:
        return False

    return hmac.compare_digest(expected_token, provided_token)


class MemorySessionStore:
    """
    In-memory session store for development/testing and Redis fallback.
    """
    
    def __init__(self):
        self._sessions: Dict[str, Dict[str, Any]] = {}
        from app.config import get_config
        config = get_config()
        self.session_lifetime_hours = config.session_lifetime_hours
        self.max_sessions_per_user = config.max_sessions_per_user
    
    def create_session(
        self,
        user_id: str,
        spotify_token_info: Dict[str, Any],
        user_data: Dict[str, Any],
        csrf_token: str
    ) -> str:
        """Create a session in memory."""
        session_token = generate_session_token()
        
        # Clean up old sessions for this user first
        self.cleanup_user_sessions(user_id)
        
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
        
        # Store session
        self._sessions[session_token] = session_data
        
        logger.info(
            "[MEMORY-SESSION-CREATE] Session created",
            extra={
                "user_id": user_id,
                "session_token": session_token[:8] + "...",
            }
        )
        
        return session_token
    
    def get_session(self, session_token: str) -> Optional[Dict[str, Any]]:
        """Get session from memory."""
        if not session_token:
            return None
        
        session_data = self._sessions.get(session_token)
        if not session_data:
            return None
        
        # Check expiration
        expires_at = datetime.fromisoformat(session_data["expires_at"])
        if datetime.now(timezone.utc) > expires_at:
            # Clean up expired session
            del self._sessions[session_token]
            return None
        
        # Update last activity
        session_data["last_activity"] = datetime.now(timezone.utc).isoformat()
        return session_data
    
    def invalidate_session(self, session_token: str) -> bool:
        """Invalidate session in memory."""
        if session_token in self._sessions:
            del self._sessions[session_token]
            return True
        return False
    
    def cleanup_user_sessions(self, user_id: str, keep_latest: int = None):
        """Clean up old sessions for a user."""
        if keep_latest is None:
            keep_latest = self.max_sessions_per_user - 1
        
        user_sessions = []
        
        # Find all sessions for this user
        for token, data in self._sessions.items():
            if data.get("user_id") == user_id:
                user_sessions.append((token, data))
        
        if len(user_sessions) <= keep_latest:
            return
        
        # Sort by creation time (newest first)
        user_sessions.sort(key=lambda x: x[1]["created_at"], reverse=True)
        
        # Remove old sessions
        sessions_to_remove = user_sessions[keep_latest:]
        for token, _ in sessions_to_remove:
            del self._sessions[token]
    
    def cleanup_expired_sessions(self) -> int:
        """Clean up expired sessions."""
        now = datetime.now(timezone.utc)
        expired_tokens = []
        
        for token, data in self._sessions.items():
            expires_at = datetime.fromisoformat(data["expires_at"])
            if now > expires_at:
                expired_tokens.append(token)
        
        for token in expired_tokens:
            del self._sessions[token]
        
        return len(expired_tokens)
    
    def get_session_stats(self) -> Dict[str, Any]:
        """Get session statistics."""
        now = datetime.now(timezone.utc)
        active_sessions = 0
        unique_users = set()
        
        for data in self._sessions.values():
            expires_at = datetime.fromisoformat(data["expires_at"])
            if now <= expires_at:
                active_sessions += 1
                unique_users.add(data.get("user_id"))
        
        return {
            "total_sessions": len(self._sessions),
            "active_sessions": active_sessions,
            "unique_users": len(unique_users),
            "storage_type": "Memory",
        }
    
    def get_sessions_snapshot(self) -> Dict[str, Dict[str, Any]]:
        """Return snapshot of sessions."""
        return dict(self._sessions)
    
    def update_session_token_info(self, session_token: str, new_token_info: Dict[str, Any]):
        """Update token info for a session."""
        if session_token in self._sessions:
            self._sessions[session_token]["token_info"] = new_token_info
