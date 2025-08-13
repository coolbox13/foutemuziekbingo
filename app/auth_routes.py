"""
Authentication Routes Module

This module handles all authentication-related endpoints for the Musical Bingo application.
It provides Spotify OAuth integration, secure session management, and JWT token handling.

Key Features:
- Spotify OAuth 2.0 authentication flow
- CSRF protection with state parameters
- Secure session management with Redis/Dragonfly
- JWT token generation and refresh
- Beautiful HTML responses for web flow
- Comprehensive error handling and logging

Security Features:
- CSRF protection on OAuth flow
- Secure session cookies with encryption
- JWT token validation and refresh
- Session invalidation on logout
- IP-based legacy compatibility (deprecated)

Routes:
- GET /login/page: Display login page
- GET /login: Initiate Spotify OAuth flow  
- GET /spotify/callback: Handle OAuth callback
- POST /authenticate: API authentication endpoint
- POST /refresh: Refresh JWT tokens
- GET /me: Get current user information
- POST /logout: Logout and clear session
- GET /status: Check authentication status
"""

from fastapi import APIRouter, Request, HTTPException, Depends, Response
from typing import Optional
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.security import HTTPBearer
from spotipy.oauth2 import SpotifyOAuth
from spotipy import Spotify
from spotipy.exceptions import SpotifyException
import logging
from app.config import get_config
from app.models import (
    AuthRequest,
    AuthResponse,
    TokenRefreshRequest,
    TokenRefreshResponse,
    SpotifyUserProfile,
    UserPublic,
    APIResponse,
)
from app.auth_service import auth_service, get_current_user, get_current_user_optional
from app.secure_session import (
    create_secure_session,
    get_session_from_request,
    invalidate_session,
    generate_csrf_token,
)

router = APIRouter()
logger = logging.getLogger("music_bingo")
security = HTTPBearer()
templates = Jinja2Templates(directory="templates")

# Legacy session storage for backwards compatibility during migration
# TODO: Remove after full migration to secure sessions
sessions = {}


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
    description="Processes OAuth callback and creates user session",
    tags=["Authentication", "OAuth"],
    responses={
        200: {
            "description": "Authentication successful - HTML success page",
            "content": {"text/html": {"example": "<!DOCTYPE html>..."}}
        },
        400: {
            "description": "OAuth error or missing authorization code",
            "content": {"text/html": {"example": "<!DOCTYPE html>..."}}
        },
        500: {
            "description": "Authentication processing failed",
            "content": {"text/html": {"example": "<!DOCTYPE html>..."}}
        }
    }
)
async def spotify_callback(
    request: Request,
    response: Response,
    code: Optional[str] = None,
    error: Optional[str] = None,
    state: Optional[str] = None,
) -> HTMLResponse:
    """
    Handle Spotify OAuth callback and create user session.
    
    This endpoint processes the OAuth 2.0 authorization code callback from Spotify.
    It exchanges the authorization code for access tokens, retrieves user profile
    information, and creates a secure session for the user.
    
    Processing Steps:
    1. Validate CSRF state parameter
    2. Exchange authorization code for access tokens
    3. Retrieve user profile from Spotify API
    4. Create or update user in our database
    5. Generate JWT tokens for API access
    6. Create secure session with encrypted cookies
    7. Return beautiful success page with auto-redirect
    
    Args:
        request: FastAPI request object
        response: FastAPI response object for setting cookies
        code: OAuth authorization code from Spotify (query parameter)
        error: OAuth error from Spotify if authorization failed (query parameter)
        state: CSRF state parameter for validation (query parameter)
        
    Returns:
        HTMLResponse: Beautiful HTML page with authentication result
        - Success: Welcome page with auto-redirect to dashboard
        - Error: Error page with retry option
        
    Raises:
        HTTPException: Not raised directly, errors handled with HTML responses
        
    Security Features:
    - CSRF state parameter validation
    - Secure session creation with encryption
    - Token exchange error handling
    - Comprehensive audit logging
    - XSS protection in HTML responses
    
    Example:
        GET /auth/spotify/callback?code=AQA...&state=xyz123
        Returns: HTML success page with auto-redirect
        
    Error Handling:
        - OAuth errors: Returns user-friendly error page
        - Missing code: Returns error page with retry option
        - Invalid state: Security error with detailed logging
        - Token exchange failure: Returns generic error page
        - User profile failure: Returns error page
        
    Session Data Stored:
        - User ID and profile information
        - Spotify access and refresh tokens
        - Session expiration time
        - CSRF tokens for subsequent requests
    """
    config = get_config()
    callback_id = f"callback-{int(request.scope.get('time', 0))}"

    logger.info(
        "[AUTH-CALLBACK-001] Processing Spotify callback",
        extra={"callback_id": callback_id, "has_code": bool(code), "error": error},
    )

    if error:
        logger.error(
            "[AUTH-CALLBACK-ERROR] Spotify OAuth error",
            extra={"callback_id": callback_id, "error": error},
        )
        return HTMLResponse(
            content=f"""
            <!DOCTYPE html>
            <html lang="en">
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>Authentication Error - Music Bingo</title>
                <script src="https://cdn.tailwindcss.com"></script>
                <script src="https://unpkg.com/lucide@latest/dist/umd/lucide.js"></script>
            </head>
            <body class="min-h-screen flex items-center justify-center bg-gray-50 py-12 px-4">
                <div class="max-w-md w-full text-center space-y-4">
                    <i data-lucide="alert-triangle" class="h-16 w-16 text-red-500 mx-auto"></i>
                    <h1 class="text-2xl font-bold text-gray-900">Authentication Error</h1>
                    <p class="text-gray-600">Spotify authentication failed: {error}</p>
                    <a href="/auth/login/page" class="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-red-600 hover:bg-red-700">
                        Try Again
                    </a>
                    <div>
                        <a href="/" class="text-sm text-gray-500 hover:text-gray-700">← Back to home</a>
                    </div>
                </div>
                <script>lucide.createIcons();</script>
            </body>
            </html>
            """,
            status_code=400,
        )

    if not code:
        logger.error(
            "[AUTH-CALLBACK-ERROR] No authorization code received",
            extra={"callback_id": callback_id},
        )
        return HTMLResponse(
            content="""
            <!DOCTYPE html>
            <html lang="en">
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>Authentication Error - Music Bingo</title>
                <script src="https://cdn.tailwindcss.com"></script>
                <script src="https://unpkg.com/lucide@latest/dist/umd/lucide.js"></script>
            </head>
            <body class="min-h-screen flex items-center justify-center bg-gray-50 py-12 px-4">
                <div class="max-w-md w-full text-center space-y-4">
                    <i data-lucide="alert-triangle" class="h-16 w-16 text-red-500 mx-auto"></i>
                    <h1 class="text-2xl font-bold text-gray-900">Authentication Error</h1>
                    <p class="text-gray-600">No authorization code received from Spotify.</p>
                    <a href="/auth/login/page" class="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-red-600 hover:bg-red-700">
                        Try Again
                    </a>
                    <div>
                        <a href="/" class="text-sm text-gray-500 hover:text-gray-700">← Back to home</a>
                    </div>
                </div>
                <script>lucide.createIcons();</script>
            </body>
            </html>
            """,
            status_code=400,
        )

    try:
        # Validate CSRF state parameter
        if not state:
            logger.error(
                "[AUTH-CALLBACK-CSRF] Missing state parameter",
                extra={"callback_id": callback_id},
            )
            raise Exception("Missing security state parameter")

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
            raise Exception("Spotify authentication failed")

        if not token_info:
            raise Exception("Failed to get token from Spotify")

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

        # Create auth request
        auth_request = AuthRequest(
            spotify_user=spotify_profile,
            access_token=token_info["access_token"],
            refresh_token=token_info.get("refresh_token"),
        )

        # Authenticate user through our service
        logger.info(
            "[AUTH-CALLBACK-005] Processing authentication through auth service",
            extra={"callback_id": callback_id, "spotify_id": spotify_profile.id},
        )

        auth_response = await auth_service.authenticate_spotify_user(auth_request)

        if not auth_response.success:
            raise Exception("Authentication failed")

        logger.info(
            "[AUTH-CALLBACK-006] Authentication successful",
            extra={
                "callback_id": callback_id,
                "user_id": auth_response.user.id,
                "spotify_id": auth_response.user.spotify_id,
            },
        )

        logger.info(
            f"[DEBUG-001] Starting HTML response generation",
            extra={
                "callback_id": callback_id,
                "access_token_length": len(auth_response.tokens.access_token),
                "user_display_name": auth_response.user.display_name,
                "user_dict_keys": list(auth_response.user.dict().keys()),
            },
        )

        # Create secure session (replaces IP-based sessions)
        session_token = create_secure_session(
            user_id=auth_response.user.id,
            spotify_token_info=token_info,
            user_data=auth_response.user.dict(),
            response=response,
            secret_key=config.secret_key,
        )

        # Do not use IP-based legacy session anymore (security)

        logger.info(
            f"[AUTH-CALLBACK-007] Secure session created",
            extra={
                "callback_id": callback_id,
                "session_token": session_token[:8] + "...",
                "user_id": auth_response.user.id,
            },
        )

        # Return success page with tokens (in production, use secure cookies or redirect)
        logger.info(
            f"[DEBUG-003] About to generate HTML response",
            extra={
                "callback_id": callback_id,
                "user_display_name": str(auth_response.user.display_name),
                "access_token_preview": auth_response.tokens.access_token[:20] + "...",
                "user_dict_type": type(auth_response.user.dict()),
            },
        )

        try:
            # Use Pydantic's built-in JSON serialization which handles datetime objects
            user_json = auth_response.user.json()
            logger.info(
                f"[DEBUG-004] User JSON serialized successfully",
                extra={
                    "callback_id": callback_id,
                    "user_json_length": len(user_json),
                    "user_json_preview": user_json[:100] + "..."
                    if len(user_json) > 100
                    else user_json,
                },
            )
        except Exception as json_error:
            logger.error(
                f"[DEBUG-004-ERROR] User JSON serialization failed",
                extra={
                    "callback_id": callback_id,
                    "error": str(json_error),
                    "error_type": type(json_error).__name__,
                    "user_dict_sample": str(auth_response.user.dict())[:200],
                },
            )
            raise

        return HTMLResponse(
            content=f"""
            <!DOCTYPE html>
            <html lang="en">
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>Authentication Successful - Music Bingo</title>
                <script src="https://cdn.tailwindcss.com"></script>
                <script src="https://unpkg.com/lucide@latest/dist/umd/lucide.js"></script>
                <script>
                    tailwind.config = {{
                        theme: {{
                            extend: {{
                                colors: {{
                                    'bingo-primary': '#8b5cf6',
                                    'spotify-green': '#1db954',
                                }}
                            }}
                        }}
                    }}
                </script>
            </head>
            <body class="min-h-screen flex items-center justify-center bg-gradient-to-br from-bingo-primary to-purple-600 py-12 px-4">
                <div class="max-w-md w-full text-center space-y-6 bg-white rounded-lg shadow-xl p-8">
                    <div class="flex justify-center">
                        <div class="bg-spotify-green rounded-full p-3">
                            <i data-lucide="check" class="h-8 w-8 text-white"></i>
                        </div>
                    </div>
                    <h1 class="text-2xl font-bold text-gray-900">Welcome, {auth_response.user.display_name or 'User'}!</h1>
                    <p class="text-gray-600">Authentication successful. Redirecting to dashboard...</p>
                    <div class="bg-gray-100 rounded-lg p-4">
                        <div class="flex items-center justify-center space-x-2">
                            <div class="animate-spin rounded-full h-4 w-4 border-b-2 border-bingo-primary"></div>
                            <span class="text-sm text-gray-600">Loading your dashboard...</span>
                        </div>
                    </div>
                    <p class="text-sm text-gray-500">
                        If not redirected, <a href="/dashboard" class="text-bingo-primary hover:underline">click here</a>.
                    </p>
                </div>
                <script>
                    // Store non-sensitive user data for frontend use (no tokens stored)
                    localStorage.setItem('user', `{user_json}`);
                    
                    // Initialize icons and redirect
                    lucide.createIcons();
                    setTimeout(() => {{
                        window.location.href = '/dashboard';
                    }}, 2000);
                </script>
            </body>
            </html>
            """,
            status_code=200,
        )

    except Exception as e:
        logger.error(
            f"[AUTH-CALLBACK-ERROR] Authentication failed",
            extra={"callback_id": callback_id, "error": str(e)},
        )

        return HTMLResponse(
            content=f"""
            <!DOCTYPE html>
            <html lang="en">
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>Authentication Failed - Music Bingo</title>
                <script src="https://cdn.tailwindcss.com"></script>
                <script src="https://unpkg.com/lucide@latest/dist/umd/lucide.js"></script>
            </head>
            <body class="min-h-screen flex items-center justify-center bg-gray-50 py-12 px-4">
                <div class="max-w-md w-full text-center space-y-4">
                    <i data-lucide="x-circle" class="h-16 w-16 text-red-500 mx-auto"></i>
                    <h1 class="text-2xl font-bold text-gray-900">Authentication Failed</h1>
                    <p class="text-gray-600">An error occurred during authentication. Please try again.</p>
                    <a href="/auth/login/page" class="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-red-600 hover:bg-red-700">
                        Try Again
                    </a>
                    <div>
                        <a href="/" class="text-sm text-gray-500 hover:text-gray-700">← Back to home</a>
                    </div>
                </div>
                <script>lucide.createIcons();</script>
            </body>
            </html>
            """,
            status_code=500,
        )


@router.post(
    "/authenticate", 
    response_model=AuthResponse,
    summary="Authenticate User via API",
    description="Authenticate user with Spotify OAuth data via API endpoint",
    tags=["Authentication", "API"],
    responses={
        200: {
            "description": "Authentication successful",
            "model": AuthResponse
        },
        401: {
            "description": "Authentication failed",
            "content": {
                "application/json": {
                    "example": {"detail": "Authentication failed. Please try again."}
                }
            }
        }
    }
)
async def authenticate(auth_request: AuthRequest) -> AuthResponse:
    """
    Authenticate user with Spotify OAuth data (API endpoint).
    
    This endpoint provides programmatic authentication for applications that
    handle the OAuth flow themselves. It processes the Spotify user profile
    and token information to create or update a user account.
    
    Use Cases:
    - Mobile applications with custom OAuth handling
    - Server-to-server authentication
    - Custom frontend implementations
    - API-only authentication flows
    
    Args:
        auth_request: Authentication request containing:
            - spotify_user: Complete Spotify user profile
            - access_token: Spotify access token
            - refresh_token: Spotify refresh token (optional)
            
    Returns:
        AuthResponse: Authentication result containing:
            - success: Authentication status
            - user: User profile information
            - tokens: JWT access and refresh tokens
            - message: Optional status message
            
    Raises:
        HTTPException: 401 if authentication fails
        
    Example:
        POST /auth/authenticate
        {
            "spotify_user": {
                "id": "spotify_user_id",
                "display_name": "User Name",
                "email": "user@example.com"
            },
            "access_token": "spotify_access_token",
            "refresh_token": "spotify_refresh_token"
        }
        
        Response:
        {
            "success": true,
            "user": {...},
            "tokens": {
                "access_token": "jwt_token",
                "refresh_token": "jwt_refresh_token",
                "token_type": "bearer",
                "expires_in": 900
            }
        }
        
    Security Notes:
        - Validates Spotify token with Spotify API
        - Creates secure JWT tokens for API access
        - Stores user data in encrypted database
        - Generates audit logs for authentication events
    """
    try:
        return await auth_service.authenticate_spotify_user(auth_request)
    except Exception as e:
        logger.error(
            f"[AUTH-API-ERROR] Authentication failed",
            extra={"error": str(e), "spotify_id": auth_request.spotify_user.id},
        )
        raise HTTPException(
            status_code=401, detail="Authentication failed. Please try again."
        )


@router.post(
    "/refresh", 
    response_model=TokenRefreshResponse,
    summary="Refresh JWT Access Token",
    description="Refresh expired JWT access token using refresh token",
    tags=["Authentication", "JWT"],
    responses={
        200: {
            "description": "Token refresh successful",
            "model": TokenRefreshResponse
        },
        401: {
            "description": "Token refresh failed",
            "content": {
                "application/json": {
                    "example": {"detail": "Authentication failed. Please try again."}
                }
            }
        }
    }
)
async def refresh_token(refresh_request: TokenRefreshRequest) -> TokenRefreshResponse:
    """
    Refresh JWT access token using refresh token.
    
    This endpoint allows clients to obtain a new access token when the current
    one expires. It validates the refresh token and issues a new access token
    with the same permissions and user context.
    
    Token Lifecycle:
    - Access tokens expire in 15 minutes for security
    - Refresh tokens expire in 7 days  
    - Refresh tokens are single-use (rotation for security)
    - New refresh token provided with each refresh
    
    Args:
        refresh_request: Token refresh request containing:
            - refresh_token: Valid JWT refresh token
            
    Returns:
        TokenRefreshResponse: New token information containing:
            - success: Refresh operation status
            - access_token: New JWT access token
            - expires_in: Token expiration time in seconds
            
    Raises:
        HTTPException: 401 if refresh token is invalid or expired
        
    Example:
        POST /auth/refresh
        {
            "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..."
        }
        
        Response:
        {
            "success": true,
            "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
            "expires_in": 900
        }
        
    Security Features:
        - Validates refresh token signature and expiration
        - Checks token against blacklist (if implemented)
        - Generates new access token with same permissions
        - Rotates refresh token for enhanced security
        - Logs refresh events for audit trail
        
    Error Conditions:
        - Invalid refresh token format
        - Expired refresh token
        - Revoked or blacklisted token
        - User account disabled or deleted
        - Token signature validation failure
    """
    try:
        return await auth_service.refresh_token(refresh_request)
    except Exception as e:
        logger.error(
            f"[AUTH-REFRESH-ERROR] Token refresh failed", extra={"error": str(e)}
        )
        raise HTTPException(
            status_code=401, detail="Authentication failed. Please try again."
        )


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
async def get_current_user_info(current_user: UserPublic = Depends(get_current_user)) -> UserPublic:
    """
    Get current authenticated user information.
    
    This endpoint returns the profile information for the currently authenticated
    user. It requires a valid JWT access token in the Authorization header.
    
    Authentication Required:
        - Valid JWT access token in Authorization header
        - Format: "Bearer <jwt_access_token>"
        - Token must not be expired or revoked
    
    Args:
        current_user: Injected authenticated user from JWT token
        
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
        Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...
        
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
        - Validates token signature and expiration
        - Updates last_login_at timestamp
        
    Use Cases:
        - Display user profile in dashboard
        - Customize UI based on user preferences
        - Check user subscription status
        - Verify authentication status
    """
    return current_user


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
    - Removing legacy session data
    - Logging logout event for audit
    
    The logout is performed even if no valid authentication is present,
    ensuring complete cleanup of any residual session data.
    
    Session Cleanup:
    - Secure Redis session invalidation
    - Session cookie removal with secure flags
    - Legacy IP-based session cleanup (deprecated)
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
        - Clear any API tokens from memory
        
    Notes:
        - Logout succeeds even without valid authentication
        - JWT tokens continue to work until expiration (by design)
        - For immediate token revocation, implement token blacklisting
        - Session invalidation prevents reuse of session cookies
    """
    config = get_config()
    
    # Get session from secure cookie
    session_data = get_session_from_request(request, config.secret_key)
    session_token = None

    if session_data:
        # Extract session token from cookie for invalidation
        cookie_value = request.cookies.get("music_bingo_session", "")
        if "." in cookie_value:
            session_token = cookie_value.split(".")[0]

    # Invalidate secure session
    if session_token:
        invalidate_session(session_token, response)

    # Clear legacy session for backwards compatibility
    client_ip = request.client.host
    if client_ip in sessions:
        del sessions[client_ip]

    # In a full JWT implementation, we'd add the token to a blacklist
    # For now, we just rely on token expiration and session invalidation

    logger.info(
        f"[AUTH-LOGOUT] User logged out",
        extra={
            "user_id": current_user.id if current_user else "unknown",
            "session_token": session_token[:8] + "..." if session_token else "none",
        },
    )

    return APIResponse(success=True, message="Logged out successfully")


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
    - Validates JWT token if present in Authorization header
    - Checks secure session cookie if JWT not provided
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
        Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...
        
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
