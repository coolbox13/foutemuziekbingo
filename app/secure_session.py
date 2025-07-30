"""
Secure session management utilities to replace IP-based session keys.
Provides UUID-based session tokens and secure cookie handling.
"""

import uuid
import secrets
import logging
from typing import Optional, Dict, Any
from datetime import datetime, timezone, timedelta
from fastapi import Request, Response, HTTPException
import hashlib
import hmac

logger = logging.getLogger("music_bingo")

# In-memory session store (in production, use Redis or database)
_sessions: Dict[str, Dict[str, Any]] = {}

# Session configuration
SESSION_COOKIE_NAME = "music_bingo_session"
SESSION_LIFETIME_HOURS = 24
MAX_SESSIONS_PER_USER = 5


def generate_session_token() -> str:
    """Generate a cryptographically secure session token."""
    return secrets.token_urlsafe(32)


def generate_csrf_token() -> str:
    """Generate a CSRF token for form protection."""
    return secrets.token_urlsafe(16)


def create_session_signature(session_id: str, secret_key: str) -> str:
    """Create a signature for session validation."""
    return hmac.new(
        secret_key.encode(),
        session_id.encode(),
        hashlib.sha256
    ).hexdigest()


def verify_session_signature(session_id: str, signature: str, secret_key: str) -> bool:
    """Verify a session signature."""
    expected_signature = create_session_signature(session_id, secret_key)
    return hmac.compare_digest(expected_signature, signature)


def create_secure_session(
    user_id: str,
    spotify_token_info: Dict[str, Any],
    user_data: Dict[str, Any],
    response: Response,
    secret_key: str
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
    session_token = generate_session_token()
    csrf_token = generate_csrf_token()
    
    # Clean up old sessions for this user (prevent session accumulation)
    cleanup_user_sessions(user_id)
    
    # Create session data
    session_data = {
        "user_id": user_id,
        "token_info": spotify_token_info,
        "user": user_data,
        "csrf_token": csrf_token,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": (datetime.now(timezone.utc) + timedelta(hours=SESSION_LIFETIME_HOURS)).isoformat(),
        "last_activity": datetime.now(timezone.utc).isoformat()
    }
    
    # Store session
    _sessions[session_token] = session_data
    
    # Create signed session cookie
    signature = create_session_signature(session_token, secret_key)
    cookie_value = f"{session_token}.{signature}"
    
    # Set secure HTTP-only cookie
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=cookie_value,
        max_age=SESSION_LIFETIME_HOURS * 3600,  # Convert to seconds
        httponly=True,  # Prevent JavaScript access
        secure=True,    # HTTPS only (set to False for development)
        samesite="lax"  # CSRF protection
    )
    
    logger.info("[SESSION-CREATE] Secure session created", extra={
        "user_id": user_id,
        "session_token": session_token[:8] + "...",  # Log only first 8 chars
        "expires_at": session_data["expires_at"]
    })
    
    return session_token


def get_session_from_request(request: Request, secret_key: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve and validate session from request cookies.
    
    Args:
        request: FastAPI request object
        secret_key: Secret key for verification
        
    Returns:
        Session data if valid, None otherwise
    """
    cookie_value = request.cookies.get(SESSION_COOKIE_NAME)
    
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
        
        # Get session data
        session_data = _sessions.get(session_token)
        if not session_data:
            logger.info("[SESSION-GET] Session not found", extra={
                "session_token": session_token[:8] + "..."
            })
            return None
        
        # Check expiration
        expires_at = datetime.fromisoformat(session_data["expires_at"])
        if datetime.now(timezone.utc) > expires_at:
            logger.info("[SESSION-GET] Session expired", extra={
                "session_token": session_token[:8] + "...",
                "expires_at": session_data["expires_at"]
            })
            # Clean up expired session
            del _sessions[session_token]
            return None
        
        # Update last activity
        session_data["last_activity"] = datetime.now(timezone.utc).isoformat()
        
        return session_data
        
    except Exception as e:
        logger.warning("[SESSION-GET] Error retrieving session", extra={
            "error": str(e),
            "error_type": type(e).__name__
        })
        return None


def invalidate_session(session_token: str, response: Response) -> bool:
    """
    Invalidate a session and clear the cookie.
    
    Args:
        session_token: Session token to invalidate
        response: FastAPI response object to clear cookie
        
    Returns:
        True if session was found and invalidated
    """
    session_found = session_token in _sessions
    
    if session_found:
        user_id = _sessions[session_token].get("user_id", "unknown")
        del _sessions[session_token]
        
        logger.info("[SESSION-INVALIDATE] Session invalidated", extra={
            "session_token": session_token[:8] + "...",
            "user_id": user_id
        })
    
    # Clear cookie regardless
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        httponly=True,
        secure=True,
        samesite="lax"
    )
    
    return session_found


def cleanup_user_sessions(user_id: str, keep_latest: int = MAX_SESSIONS_PER_USER - 1):
    """
    Clean up old sessions for a user, keeping only the most recent ones.
    
    Args:
        user_id: User identifier
        keep_latest: Number of recent sessions to keep
    """
    user_sessions = []
    
    # Find all sessions for this user
    for token, data in _sessions.items():
        if data.get("user_id") == user_id:
            user_sessions.append((token, data))
    
    # Sort by creation time (newest first)
    user_sessions.sort(key=lambda x: x[1]["created_at"], reverse=True)
    
    # Remove old sessions
    sessions_to_remove = user_sessions[keep_latest:]
    for token, _ in sessions_to_remove:
        del _sessions[token]
        logger.info("[SESSION-CLEANUP] Old session removed", extra={
            "user_id": user_id,
            "session_token": token[:8] + "..."
        })


def cleanup_expired_sessions():
    """Clean up all expired sessions."""
    now = datetime.now(timezone.utc)
    expired_tokens = []
    
    for token, data in _sessions.items():
        expires_at = datetime.fromisoformat(data["expires_at"])
        if now > expires_at:
            expired_tokens.append(token)
    
    for token in expired_tokens:
        user_id = _sessions[token].get("user_id", "unknown")
        del _sessions[token]
        logger.info("[SESSION-CLEANUP] Expired session removed", extra={
            "session_token": token[:8] + "...",
            "user_id": user_id
        })
    
    if expired_tokens:
        logger.info(f"[SESSION-CLEANUP] Cleaned up {len(expired_tokens)} expired sessions")


def get_session_stats() -> Dict[str, Any]:
    """Get statistics about active sessions."""
    now = datetime.now(timezone.utc)
    active_sessions = 0
    expired_sessions = 0
    users_with_sessions = set()
    
    for data in _sessions.values():
        expires_at = datetime.fromisoformat(data["expires_at"])
        if now <= expires_at:
            active_sessions += 1
            users_with_sessions.add(data.get("user_id"))
        else:
            expired_sessions += 1
    
    return {
        "total_sessions": len(_sessions),
        "active_sessions": active_sessions,
        "expired_sessions": expired_sessions,
        "unique_users": len(users_with_sessions)
    }


# Utility function for CSRF protection
def verify_csrf_token(request: Request, provided_token: str, secret_key: str) -> bool:
    """
    Verify CSRF token against the session.
    
    Args:
        request: FastAPI request object
        provided_token: CSRF token from form/header
        secret_key: Secret key for session verification
        
    Returns:
        True if CSRF token is valid
    """
    session_data = get_session_from_request(request, secret_key)
    if not session_data:
        return False
    
    expected_token = session_data.get("csrf_token")
    if not expected_token:
        return False
    
    return hmac.compare_digest(expected_token, provided_token)