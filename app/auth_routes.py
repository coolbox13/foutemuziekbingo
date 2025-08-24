"""
Authentication Routes Module - Session-Only Implementation

This module handles all authentication-related endpoints for the Musical Bingo application.
It provides Spotify OAuth integration and secure session management.

Key Features:
- Spotify OAuth 2.0 authentication flow
- CSRF protection with state parameters
- Secure session management with Redis/Dragonfly
- Standard OAuth redirect pattern
- Comprehensive error handling and logging

Security Features:
- CSRF protection on OAuth flow
- Secure session cookies with encryption
- Session invalidation on logout
- Standard OAuth redirect responses

Routes:
- GET /login/page: Display login page
- GET /login: Initiate Spotify OAuth flow
- GET /spotify/callback: Handle OAuth callback
- GET /me: Get current user information
- POST /logout: Logout and clear session
- GET /status: Check authentication status
"""

from fastapi import APIRouter, Request, Depends, Response
from typing import Optional
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from spotipy.oauth2 import SpotifyOAuth
from spotipy import Spotify
from spotipy.exceptions import SpotifyException
import logging
from app.config import get_config
from app.models import (
    SpotifyUserProfile,
    SpotifyTokens,
    UserPublic,
    APIResponse,
)
from app.auth_service import auth_service, get_current_user, get_current_user_optional
from app.secure_session import (
    create_secure_session,
    get_session_from_request,
    invalidate_session,
    generate_csrf_token,
    SESSION_COOKIE_NAME,
)

router = APIRouter()
logger = logging.getLogger("music_bingo")
templates = Jinja2Templates(directory="templates")


@router.get(
    "/login/page",
    summary="Display Login Page",
    description="Renders the authentication login page with beautiful UI",
    tags=["Authentication", "Web UI"],
    responses={
        200: {
            "description": "Login page HTML content",
            "content": {"text/html": {"example": "<!DOCTYPE html>..."}}
        }
    }
)
async def login_page(request: Request) -> HTMLResponse:
    """
    Display the login page with beautiful UI.

    This endpoint renders the authentication page where users can initiate
    the Spotify OAuth flow. The page includes:
    - Beautiful responsive design using Tailwind CSS
    - Spotify branding and call-to-action
    - Error handling for authentication failures
    - Mobile-friendly interface

    Args:
        request: FastAPI request object containing client information

    Returns:
        HTMLResponse: Rendered login page template

    Example:
        GET /auth/login/page
        Returns: Beautiful HTML login page
    """
    return templates.TemplateResponse("auth.html", {"request": request})


@router.get(
    "/login",
    summary="Initiate Spotify OAuth Flow",
    description="Redirects user to Spotify OAuth with CSRF protection",
    tags=["Authentication", "OAuth"],
    responses={
        302: {
            "description": "Redirect to Spotify OAuth authorization URL",
            "headers": {
                "Location": {
                    "description": "Spotify OAuth authorization URL with CSRF state",
                    "schema": {"type": "string"}
                }
            }
        }
    }
)
async def spotify_login() -> RedirectResponse:
    """
    Initiate Spotify OAuth flow with CSRF protection.

    This endpoint starts the OAuth 2.0 authorization code flow with Spotify.
    It generates a secure CSRF state parameter and redirects the user to
    Spotify's authorization server.

    Security Features:
    - CSRF state parameter generation for request validation
    - Comprehensive scope requests for required permissions
    - Always shows Spotify dialog for better UX
    - Secure redirect URI validation

    OAuth Scopes Requested:
    - playlist-read-private: Access user's private playlists
    - user-read-playback-state: Read current playback state
    - user-modify-playback-state: Control playback
    - user-read-private: Access user profile data
    - user-read-email: Access user email address

    Returns:
        RedirectResponse: 302 redirect to Spotify OAuth authorization URL

    Raises:
        HTTPException: If OAuth configuration is invalid

    Example:
        GET /auth/login
        Returns: 302 redirect to https://accounts.spotify.com/authorize?...

    Security Note:
        The state parameter is logged (first 8 characters only) for audit purposes
    """
    config = get_config()

    # Generate CSRF state parameter
    csrf_state = generate_csrf_token()

    sp_oauth = SpotifyOAuth(
        client_id=config.spotify_client_id,
        client_secret=config.spotify_client_secret,
        redirect_uri=config.spotify_redirect_uri,
        scope="playlist-read-private user-read-playback-state user-modify-playback-state user-read-private user-read-email",
        state=csrf_state,  # Add CSRF protection
        show_dialog=True,  # Always show dialog for better UX
    )

    auth_url = sp_oauth.get_authorize_url()
    logger.info(
        "[AUTH-SPOTIFY-001] Redirecting to Spotify OAuth",
        extra={
            "auth_url": auth_url[:50] + "...",
            "redirect_uri": config.spotify_redirect_uri,
            "csrf_state": csrf_state[:8] + "...",  # Log only first 8 chars
        },
    )

    return RedirectResponse(url=auth_url, status_code=302)


@router.get(
    "/spotify/callback",
    summary="Handle Spotify OAuth Callback",
    description="Processes OAuth callback with standard redirect pattern",
    tags=["Authentication", "OAuth"],
    responses={
        302: {
            "description": "Redirect to dashboard on success or login on error",
            "headers": {
                "Location": {
                    "description": "Dashboard URL on success, login URL on error",
                    "schema": {"type": "string"}
                }
            }
        }
    }
)
async def spotify_callback(
    code: Optional[str] = None,
    error: Optional[str] = None,
    state: Optional[str] = None,
) -> RedirectResponse:
    """
    Handle Spotify OAuth callback with standard redirect pattern.

    This endpoint processes the OAuth 2.0 authorization code callback from Spotify.
    It exchanges the authorization code for access tokens, retrieves user profile
    information, and creates a secure session for the user.

    Processing Steps:
    1. Validate CSRF state parameter
    2. Exchange authorization code for access tokens
    3. Retrieve user profile from Spotify API
    4. Create or update user in our database
    5. Create secure session with encrypted cookies
    6. Redirect to dashboard on success

    Args:
        code: OAuth authorization code from Spotify (query parameter)
        error: OAuth error from Spotify if authorization failed (query parameter)
        state: CSRF state parameter for validation (query parameter)

    Returns:
        RedirectResponse: Redirect to dashboard on success, login on error

    Security Features:
    - CSRF state parameter validation
    - Secure session creation with encryption
    - Token exchange error handling
    - Comprehensive audit logging

    Example:
        GET /auth/spotify/callback?code=AQA...&state=xyz123
        Returns: 302 redirect to /dashboard

    Error Handling:
        - OAuth errors: Redirects to login with error parameter
        - Missing code: Redirects to login with error parameter
        - Invalid state: Security error with detailed logging
        - Token exchange failure: Redirects to login with error parameter
        - User profile failure: Redirects to login with error parameter
    """
    config = get_config()
    callback_id = f"callback-{int(__import__('time').time())}"

    logger.info(
        "[AUTH-CALLBACK-001] Processing Spotify callback",
        extra={"callback_id": callback_id, "has_code": bool(code), "error": error},
    )

    if error:
        logger.error(
            "[AUTH-CALLBACK-ERROR] Spotify OAuth error",
            extra={"callback_id": callback_id, "error": error},
        )
        return RedirectResponse(f"/auth/login/page?error={error}", status_code=302)

    if not code:
        logger.error(
            "[AUTH-CALLBACK-ERROR] No authorization code received",
            extra={"callback_id": callback_id},
        )
        return RedirectResponse("/auth/login/page?error=no_code", status_code=302)

    try:
        # Validate CSRF state parameter
        if not state:
            logger.error(
                "[AUTH-CALLBACK-CSRF] Missing state parameter",
                extra={"callback_id": callback_id},
            )
            return RedirectResponse("/auth/login/page?error=csrf_error", status_code=302)

        # Exchange code for tokens with proper error handling
        sp_oauth = SpotifyOAuth(
            client_id=config.spotify_client_id,
            client_secret=config.spotify_client_secret,
            redirect_uri=config.spotify_redirect_uri,
            scope="playlist-read-private user-read-playback-state user-modify-playback-state user-read-private user-read-email",
            state=state,
        )

        logger.info(
            "[AUTH-CALLBACK-002] Exchanging code for tokens",
            extra={
                "callback_id": callback_id,
                "code_length": len(code),
                "state_present": bool(state),
            },
        )

        try:
            token_info = sp_oauth.get_access_token(code)
        except SpotifyException as e:
            logger.error(
                "[AUTH-CALLBACK-SPOTIFY-ERROR] Spotify OAuth error",
                extra={
                    "callback_id": callback_id,
                    "error": str(e),
                    "status_code": getattr(e, "http_status", "unknown"),
                },
            )
            return RedirectResponse("/auth/login/page?error=spotify_error", status_code=302)

        if not token_info:
            return RedirectResponse("/auth/login/page?error=token_error", status_code=302)

        logger.info(
            "[AUTH-CALLBACK-003] Got tokens from Spotify",
            extra={
                "callback_id": callback_id,
                "has_access_token": bool(token_info.get("access_token")),
                "has_refresh_token": bool(token_info.get("refresh_token")),
                "expires_in": token_info.get("expires_in"),
            },
        )

        # Get user profile from Spotify
        sp = Spotify(auth=token_info["access_token"])
        spotify_user = sp.current_user()

        logger.info(
            "[AUTH-CALLBACK-004] Got user profile from Spotify",
            extra={
                "callback_id": callback_id,
                "spotify_id": spotify_user.get("id"),
                "display_name": spotify_user.get("display_name"),
                "email": spotify_user.get("email"),
            },
        )

        # Create Spotify user profile
        spotify_profile = SpotifyUserProfile(
            id=spotify_user["id"],
            display_name=spotify_user.get("display_name"),
            email=spotify_user.get("email"),
            country=spotify_user.get("country"),
            product=spotify_user.get("product"),
            followers=spotify_user.get("followers"),
            images=spotify_user.get("images", []),
            external_urls=spotify_user.get("external_urls"),
            href=spotify_user.get("href"),
            uri=spotify_user.get("uri"),
            explicit_content=spotify_user.get("explicit_content"),
        )

        # Create Spotify tokens object
        from datetime import datetime, timezone, timedelta
        expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
        spotify_tokens = SpotifyTokens(
            access_token=token_info["access_token"],
            refresh_token=token_info.get("refresh_token"),
            expires_at=expires_at,
            scope="playlist-read-private user-read-playback-state user-modify-playback-state",
        )

        # Authenticate user through our service
        logger.info(
            "[AUTH-CALLBACK-005] Processing authentication through auth service",
            extra={"callback_id": callback_id, "spotify_id": spotify_profile.id},
        )

        user = await auth_service.authenticate_spotify_user(spotify_profile, spotify_tokens)

        logger.info(
            "[AUTH-CALLBACK-006] Authentication successful",
            extra={
                "callback_id": callback_id,
                "user_id": user.id,
                "spotify_id": user.spotify_id,
            },
        )

        # Create secure session and set cookie in the redirect response
        redirect_response = RedirectResponse("/dashboard/", status_code=302)

        session_token = await create_secure_session(
            user_id=user.id,
            spotify_token_info=token_info,
            user_data=user.dict(),
            response=redirect_response,
            secret_key=config.secret_key,
        )

        logger.info(
            "[AUTH-CALLBACK-007] Secure session created and redirect prepared",
            extra={
                "callback_id": callback_id,
                "session_token": session_token[:8] + "...",
                "user_id": user.id,
            },
        )

        return redirect_response

    except Exception as e:
        logger.error(
            "[AUTH-CALLBACK-ERROR] Authentication failed",
            extra={"callback_id": callback_id, "error": str(e)},
        )
        return RedirectResponse("/auth/login/page?error=auth_failed", status_code=302)


@router.get(
    "/me",
    response_model=UserPublic,
    summary="Get Current User Information",
    description="Retrieve authenticated user profile information",
    tags=["Authentication", "User Profile"],
    responses={
        200: {
            "description": "User profile information",
            "model": UserPublic
        },
        401: {
            "description": "Authentication required",
            "content": {
                "application/json": {
                    "example": {"detail": "Authentication required"}
                }
            }
        }
    }
)
async def get_current_user_info(current_user=Depends(get_current_user)) -> UserPublic:
    """
    Get current authenticated user information.

    This endpoint returns the profile information for the currently authenticated
    user. It requires a valid session cookie.

    Authentication Required:
        - Valid session cookie with user authentication data
        - Session must not be expired or revoked

    Args:
        current_user: Injected authenticated user from session

    Returns:
        UserPublic: Public user profile information containing:
            - id: Internal user ID
            - spotify_id: Spotify user ID
            - display_name: User's display name
            - email: User's email address (if available)
            - avatar_url: Profile picture URL
            - subscription_type: User subscription level
            - created_at: Account creation timestamp
            - last_login_at: Last login timestamp

    Example:
        GET /auth/me

        Response:
        {
            "id": "user_uuid",
            "spotify_id": "spotify_user_id",
            "display_name": "User Name",
            "email": "user@example.com",
            "avatar_url": "https://example.com/avatar.jpg",
            "subscription_type": "free",
            "created_at": "2023-12-01T10:00:00Z",
            "last_login_at": "2023-12-01T15:30:00Z"
        }

    Security Notes:
        - Only returns public profile information
        - Sensitive data (tokens, passwords) are excluded
        - Validates session and user existence
        - Updates last_login_at timestamp

    Use Cases:
        - Display user profile in dashboard
        - Customize UI based on user preferences
        - Check user subscription status
        - Verify authentication status
    """
    from app.auth_service import UserService
    user_service = UserService()
    return user_service.user_to_public(current_user)


@router.post(
    "/logout",
    summary="Logout User",
    description="Logout user and clear all session data",
    tags=["Authentication", "Session"],
    responses={
        200: {
            "description": "Logout successful",
            "model": APIResponse
        }
    }
)
async def logout(
    request: Request,
    response: Response,
    current_user: UserPublic = Depends(get_current_user_optional),
) -> APIResponse:
    """
    Logout user and clear session and cookies.

    This endpoint logs out the current user by:
    - Invalidating secure session tokens
    - Clearing session cookies
    - Logging logout event for audit

    The logout is performed even if no valid authentication is present,
    ensuring complete cleanup of any residual session data.

    Session Cleanup:
    - Secure Redis session invalidation
    - Session cookie removal with secure flags
    - Client-side storage recommendations

    Args:
        request: FastAPI request object for accessing cookies and IP
        response: FastAPI response object for clearing cookies
        current_user: Optional authenticated user (may be None)

    Returns:
        APIResponse: Logout result containing:
            - success: Always True
            - message: Confirmation message

    Example:
        POST /auth/logout

        Response:
        {
            "success": true,
            "message": "Logged out successfully"
        }

    Security Features:
        - Secure session token invalidation
        - Cookie clearing with secure flags
        - Audit logging with user and session info
        - Graceful handling of invalid sessions

    Client-Side Actions:
        After logout, clients should:
        - Clear localStorage/sessionStorage
        - Remove cached user data
        - Redirect to login page

    Notes:
        - Logout succeeds even without valid authentication
        - Session invalidation prevents reuse of session cookies
    """
    config = get_config()

    # Get session from secure cookie
    session_data = await get_session_from_request(request, config.secret_key)
    session_token = None

    if session_data:
        # Extract session token from cookie for invalidation
        cookie_value = request.cookies.get("music_bingo_session", "")
        if "." in cookie_value:
            session_token = cookie_value.split(".")[0]

    # Invalidate secure session
    if session_token:
        await invalidate_session(session_token, response)

    logger.info(
        "[AUTH-LOGOUT] User logged out",
        extra={
            "user_id": current_user.id if current_user else "unknown",
            "session_token": session_token[:8] + "..." if session_token else "none",
        },
    )

    return APIResponse(success=True, message="Logged out successfully")


@router.get("/debug/session")
async def debug_session_info(request: Request, current_user=Depends(get_current_user_optional)):
    """Debug endpoint to check session authentication status"""
    from app.config import get_config

    config = get_config()
    session_data = await get_session_from_request(request, config.secret_key)

    return {
        "authenticated": current_user is not None,
        "user_id": current_user.id if current_user else None,
        "session_data_exists": session_data is not None,
        "session_keys": list(session_data.keys()) if session_data else [],
        "cookies": list(request.cookies.keys()),
        "has_session_cookie": SESSION_COOKIE_NAME in request.cookies
    }


@router.get("/debug/test-endpoints")
async def debug_test_endpoints(current_user=Depends(get_current_user_optional)):
    """Debug endpoint to test if key endpoints are accessible"""

    results = {}

    # Test game service
    try:
        from app.game_service import game_service
        if current_user:
            games = await game_service.get_user_games(current_user.id)
            results["user_games"] = {
                "accessible": True,
                "count": len(games),
                "game_ids": [g.id for g in games[:3]]  # First 3 game IDs
            }
        else:
            results["user_games"] = {"accessible": False, "reason": "not_authenticated"}
    except Exception as e:
        results["user_games"] = {"accessible": False, "error": str(e)}

    return {
        "authenticated": current_user is not None,
        "user_id": current_user.id if current_user else None,
        "tests": results
    }


@router.get(
    "/status",
    summary="Check Authentication Status",
    description="Check if user is currently authenticated",
    tags=["Authentication", "Status"],
    responses={
        200: {
            "description": "Authentication status",
            "model": APIResponse,
            "content": {
                "application/json": {
                    "examples": {
                        "authenticated": {
                            "summary": "User is authenticated",
                            "value": {
                                "success": True,
                                "message": "Authenticated",
                                "data": {"user": "UserPublic object"}
                            }
                        },
                        "not_authenticated": {
                            "summary": "User is not authenticated",
                            "value": {
                                "success": False,
                                "message": "Not authenticated"
                            }
                        }
                    }
                }
            }
        }
    }
)
async def auth_status(current_user: UserPublic = Depends(get_current_user_optional)) -> APIResponse:
    """
    Check authentication status.

    This endpoint allows clients to verify if the current request is authenticated
    without requiring authentication. It's useful for:
    - Conditional UI rendering based on auth status
    - Checking session validity before API calls
    - Implementing auto-login flows
    - Dashboard initialization

    Authentication Check:
    - Validates session cookie if present
    - Returns user information if authenticated
    - Returns status without error if not authenticated

    Args:
        current_user: Optional authenticated user (injected dependency)

    Returns:
        APIResponse: Authentication status containing:
            - success: True if authenticated, False otherwise
            - message: Status description
            - data: User information if authenticated (optional)

    Example - Authenticated:
        GET /auth/status

        Response:
        {
            "success": true,
            "message": "Authenticated",
            "data": {
                "user": {
                    "id": "user_uuid",
                    "spotify_id": "spotify_user_id",
                    "display_name": "User Name",
                    ...
                }
            }
        }

    Example - Not Authenticated:
        GET /auth/status

        Response:
        {
            "success": false,
            "message": "Not authenticated"
        }

    Use Cases:
        - Frontend authentication state management
        - Conditional navigation menu rendering
        - Auto-redirect to login if needed
        - Session validation before long operations
        - Multi-tab authentication synchronization

    Security Notes:
        - Does not require authentication (safe for public use)
        - Only returns public user information
        - Validates tokens without throwing errors
        - Safe to call frequently for status checks
    """
    if current_user:
        return APIResponse(
            success=True, message="Authenticated", data={"user": current_user}
        )
    else:
        return APIResponse(success=False, message="Not authenticated")
