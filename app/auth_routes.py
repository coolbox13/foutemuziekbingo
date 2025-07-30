from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.security import HTTPBearer
from spotipy.oauth2 import SpotifyOAuth
from spotipy import Spotify
import os
import logging
from app.models import (
    AuthRequest, AuthResponse, TokenRefreshRequest, TokenRefreshResponse,
    SpotifyUserProfile, UserPublic, APIResponse
)
from app.auth_service import auth_service, get_current_user, get_current_user_optional
from app.database import database

router = APIRouter()
logger = logging.getLogger("music_bingo")
security = HTTPBearer()
templates = Jinja2Templates(directory="templates")

# Legacy session storage for backwards compatibility during migration
# TODO: Remove after full migration to JWT/Supabase
sessions = {}


@router.get("/login/page")
async def login_page(request: Request):
    """Show the login page with beautiful UI"""
    return templates.TemplateResponse("auth.html", {"request": request})


@router.get("/login")
async def spotify_login():
    """Initiate Spotify OAuth flow"""
    sp_oauth = SpotifyOAuth(
        client_id=os.getenv("SPOTIFY_CLIENT_ID"),
        client_secret=os.getenv("SPOTIFY_CLIENT_SECRET"),
        redirect_uri=os.getenv("SPOTIFY_REDIRECT_URI", "http://localhost:1313/auth/spotify/callback"),
        scope="playlist-read-private user-read-playback-state user-modify-playback-state user-read-private user-read-email",
        show_dialog=True  # Always show dialog for better UX
    )
    
    auth_url = sp_oauth.get_authorize_url()
    logger.info(f"[AUTH-SPOTIFY-001] Redirecting to Spotify OAuth", extra={
        "auth_url": auth_url[:50] + "...",
        "redirect_uri": os.getenv("SPOTIFY_REDIRECT_URI")
    })
    
    return RedirectResponse(url=auth_url, status_code=302)


@router.get("/spotify/callback")
async def spotify_callback(request: Request, code: str = None, error: str = None):
    """Handle Spotify OAuth callback and create user session"""
    callback_id = f"callback-{int(request.scope.get('time', 0))}"
    
    logger.info(f"[AUTH-CALLBACK-001] Processing Spotify callback", extra={
        "callback_id": callback_id,
        "has_code": bool(code),
        "error": error
    })

    if error:
        logger.error(f"[AUTH-CALLBACK-ERROR] Spotify OAuth error", extra={
            "callback_id": callback_id,
            "error": error
        })
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
            status_code=400
        )

    if not code:
        logger.error(f"[AUTH-CALLBACK-ERROR] No authorization code received", extra={
            "callback_id": callback_id
        })
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
            status_code=400
        )

    try:
        # Exchange code for tokens
        sp_oauth = SpotifyOAuth(
            client_id=os.getenv("SPOTIFY_CLIENT_ID"),
            client_secret=os.getenv("SPOTIFY_CLIENT_SECRET"),
            redirect_uri=os.getenv("SPOTIFY_REDIRECT_URI", "http://localhost:1313/auth/spotify/callback"),
            scope="playlist-read-private user-read-playback-state user-modify-playback-state user-read-private user-read-email"
        )
        
        logger.info(f"[AUTH-CALLBACK-002] Exchanging code for tokens", extra={
            "callback_id": callback_id,
            "code_length": len(code)
        })
        
        token_info = sp_oauth.get_access_token(code)
        
        if not token_info:
            raise Exception("Failed to get token from Spotify")
            
        logger.info(f"[AUTH-CALLBACK-003] Got tokens from Spotify", extra={
            "callback_id": callback_id,
            "has_access_token": bool(token_info.get("access_token")),
            "has_refresh_token": bool(token_info.get("refresh_token")),
            "expires_in": token_info.get("expires_in")
        })

        # Get user profile from Spotify
        sp = Spotify(auth=token_info["access_token"])
        spotify_user = sp.current_user()
        
        logger.info(f"[AUTH-CALLBACK-004] Got user profile from Spotify", extra={
            "callback_id": callback_id,
            "spotify_id": spotify_user.get("id"),
            "display_name": spotify_user.get("display_name"),
            "email": spotify_user.get("email")
        })
        
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
            explicit_content=spotify_user.get("explicit_content")
        )
        
        # Create auth request
        auth_request = AuthRequest(
            spotify_user=spotify_profile,
            access_token=token_info["access_token"],
            refresh_token=token_info.get("refresh_token")
        )
        
        # Authenticate user through our service
        logger.info(f"[AUTH-CALLBACK-005] Processing authentication through auth service", extra={
            "callback_id": callback_id,
            "spotify_id": spotify_profile.id
        })
        
        auth_response = await auth_service.authenticate_spotify_user(auth_request)
        
        if not auth_response.success:
            raise Exception("Authentication failed")
            
        logger.info(f"[AUTH-CALLBACK-006] Authentication successful", extra={
            "callback_id": callback_id,
            "user_id": auth_response.user.id,
            "spotify_id": auth_response.user.spotify_id
        })
        
        # Store tokens in session for legacy compatibility
        client_ip = request.client.host
        if client_ip not in sessions:
            sessions[client_ip] = {}
        sessions[client_ip]["token_info"] = token_info
        sessions[client_ip]["user"] = auth_response.user.dict()
        sessions[client_ip]["jwt_tokens"] = auth_response.tokens.dict()
        
        # Return success page with tokens (in production, use secure cookies or redirect)
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
                    // Store tokens for frontend use
                    localStorage.setItem('access_token', '{auth_response.tokens.access_token}');
                    localStorage.setItem('refresh_token', '{auth_response.tokens.refresh_token}');
                    localStorage.setItem('user', JSON.stringify({auth_response.user.json()}));
                    
                    // Initialize icons and redirect
                    lucide.createIcons();
                    setTimeout(() => {{
                        window.location.href = '/dashboard';
                    }}, 2000);
                </script>
            </body>
            </html>
            """,
            status_code=200
        )

    except Exception as e:
        logger.error(f"[AUTH-CALLBACK-ERROR] Authentication failed", extra={
            "callback_id": callback_id,
            "error": str(e)
        })
        
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
                    <p class="text-gray-600">An error occurred during authentication: {str(e)}</p>
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
            status_code=500
        )


@router.post("/authenticate", response_model=AuthResponse)
async def authenticate(auth_request: AuthRequest):
    """Authenticate user with Spotify OAuth data (API endpoint)"""
    try:
        return await auth_service.authenticate_spotify_user(auth_request)
    except Exception as e:
        logger.error(f"[AUTH-API-ERROR] Authentication failed", extra={
            "error": str(e),
            "spotify_id": auth_request.spotify_user.id
        })
        raise HTTPException(status_code=401, detail=str(e))


@router.post("/refresh", response_model=TokenRefreshResponse)
async def refresh_token(refresh_request: TokenRefreshRequest):
    """Refresh JWT access token"""
    try:
        return await auth_service.refresh_token(refresh_request)
    except Exception as e:
        logger.error(f"[AUTH-REFRESH-ERROR] Token refresh failed", extra={
            "error": str(e)
        })
        raise HTTPException(status_code=401, detail=str(e))


@router.get("/me", response_model=UserPublic)
async def get_current_user_info(current_user: UserPublic = Depends(get_current_user)):
    """Get current authenticated user information"""
    return current_user


@router.post("/logout")
async def logout(request: Request, current_user: UserPublic = Depends(get_current_user_optional)):
    """Logout user (clear session)"""
    # Clear legacy session
    client_ip = request.client.host
    if client_ip in sessions:
        del sessions[client_ip]
    
    # In a full JWT implementation, we'd add the token to a blacklist
    # For now, we just rely on token expiration
    
    logger.info(f"[AUTH-LOGOUT] User logged out", extra={
        "user_id": current_user.id if current_user else "unknown",
        "client_ip": client_ip
    })
    
    return APIResponse(
        success=True,
        message="Logged out successfully"
    )


@router.get("/status")
async def auth_status(current_user: UserPublic = Depends(get_current_user_optional)):
    """Check authentication status"""
    if current_user:
        return APIResponse(
            success=True,
            message="Authenticated",
            data={"user": current_user}
        )
    else:
        return APIResponse(
            success=False,
            message="Not authenticated"
        )
