"""
CSRF Protection Middleware for FastAPI.
Automatically validates CSRF tokens on all state-changing operations (POST, PUT, DELETE, PATCH).
"""

import logging
from typing import Callable, Optional
from fastapi import Request, Response, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from app.config import get_config
from app.secure_session import verify_csrf_token

logger = logging.getLogger("music_bingo")


class CSRFMiddleware(BaseHTTPMiddleware):
    """
    CSRF protection middleware that validates tokens on state-changing requests.

    Automatically checks for CSRF tokens on POST, PUT, DELETE, and PATCH requests.
    Tokens can be provided via:
    - X-CSRF-Token header
    - X-CSRFToken header (Django compatibility)
    - csrf_token form field
    """

    def __init__(self, app, exempt_paths: Optional[list] = None):
        """
        Initialize CSRF middleware.

        Args:
            app: FastAPI application
            exempt_paths: List of paths to exempt from CSRF protection
        """
        super().__init__(app)
        self.exempt_paths = exempt_paths or [
            "/auth/login",  # Allow login without CSRF (chicken-and-egg problem)
            "/auth/spotify/callback",  # OAuth callback from external service
            "/health",  # Health checks don't need CSRF protection
            "/metrics",  # Metrics endpoints
        ]
        self.protected_methods = {"POST", "PUT", "DELETE", "PATCH"}
        self.config = get_config()

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request and validate CSRF token if needed."""

        # Skip CSRF protection for safe methods
        if request.method not in self.protected_methods:
            return await call_next(request)

        # Skip CSRF protection for exempt paths
        request_path = request.url.path
        if any(request_path.startswith(exempt_path) for exempt_path in self.exempt_paths):
            logger.debug(f"[CSRF-MIDDLEWARE] Skipping CSRF check for exempt path: {request_path}")
            return await call_next(request)

        # Get CSRF token from various sources
        csrf_token = await self._extract_csrf_token(request)

        if not csrf_token:
            logger.warning(
                "[CSRF-MIDDLEWARE] Missing CSRF token",
                extra={
                    "method": request.method,
                    "path": request_path,
                    "client_ip": request.client.host if request.client else "unknown",
                }
            )
            return self._create_csrf_error_response("CSRF token missing")

        # Verify CSRF token
        try:
            is_valid = await verify_csrf_token(request, csrf_token, self.config.secret_key)

            if not is_valid:
                logger.warning(
                    "[CSRF-MIDDLEWARE] Invalid CSRF token",
                    extra={
                        "method": request.method,
                        "path": request_path,
                        "token_preview": csrf_token[:8] + "..." if len(csrf_token) > 8 else csrf_token,
                        "client_ip": request.client.host if request.client else "unknown",
                    }
                )
                return self._create_csrf_error_response("Invalid CSRF token")

            logger.debug(f"[CSRF-MIDDLEWARE] CSRF token validated for {request.method} {request_path}")

        except Exception as e:
            logger.error(
                f"[CSRF-MIDDLEWARE] Error validating CSRF token: {e}",
                extra={
                    "method": request.method,
                    "path": request_path,
                    "error": str(e),
                }
            )
            return self._create_csrf_error_response("CSRF validation error")

        # CSRF token is valid, proceed with request
        return await call_next(request)

    async def _extract_csrf_token(self, request: Request) -> Optional[str]:
        """
        Extract CSRF token from request headers or form data.

        Priority:
        1. X-CSRF-Token header
        2. X-CSRFToken header (Django compatibility)
        3. csrf_token form field
        4. csrfmiddlewaretoken form field (Django compatibility)
        """
        # Check headers first (most common for AJAX requests)
        csrf_token = request.headers.get("X-CSRF-Token")
        if csrf_token:
            return csrf_token

        csrf_token = request.headers.get("X-CSRFToken")
        if csrf_token:
            return csrf_token

        # Check form data for traditional form submissions
        try:
            content_type = request.headers.get("content-type", "")

            if "application/x-www-form-urlencoded" in content_type:
                form_data = await request.form()
                csrf_token = form_data.get("csrf_token") or form_data.get("csrfmiddlewaretoken")
                if csrf_token:
                    return csrf_token

            elif "multipart/form-data" in content_type:
                form_data = await request.form()
                csrf_token = form_data.get("csrf_token") or form_data.get("csrfmiddlewaretoken")
                if csrf_token:
                    return csrf_token

            elif "application/json" in content_type:
                # For JSON requests, we expect the token in headers
                # Some frameworks allow tokens in JSON body, but headers are more secure
                pass

        except Exception as e:
            logger.debug(f"[CSRF-MIDDLEWARE] Error extracting CSRF from form data: {e}")

        return None

    def _create_csrf_error_response(self, message: str) -> JSONResponse:
        """Create a standardized CSRF error response."""
        return JSONResponse(
            status_code=403,
            content={
                "success": False,
                "error": "CSRF_ERROR",
                "message": message,
                "details": "CSRF token validation failed. Ensure you include a valid CSRF token with state-changing requests."
            },
            headers={
                "X-Content-Type-Options": "nosnif",
                "X-Frame-Options": "DENY",
            }
        )


class CSRFConfig:
    """Configuration for CSRF protection."""

    def __init__(
        self,
        exempt_paths: Optional[list] = None,
        cookie_name: str = "music_bingo_csr",
        header_name: str = "X-CSRF-Token",
        require_https: bool = None
    ):
        """
        Initialize CSRF configuration.

        Args:
            exempt_paths: Paths to exempt from CSRF protection
            cookie_name: Name of the CSRF cookie
            header_name: Expected CSRF header name
            require_https: Require HTTPS for CSRF cookies (defaults to production mode)
        """
        config = get_config()

        self.exempt_paths = exempt_paths or [
            "/auth/login",
            "/auth/spotify/callback",
            "/health",
            "/metrics",
            "/docs",  # Swagger UI
            "/redoc",  # ReDoc
            "/openapi.json",  # OpenAPI schema
        ]
        self.cookie_name = cookie_name
        self.header_name = header_name
        self.require_https = require_https if require_https is not None else (config.app_env == "production")


def add_csrf_protection(app, csrf_config: CSRFConfig = None):
    """
    Add CSRF protection to a FastAPI app.

    Args:
        app: FastAPI application
        csrf_config: CSRF configuration (uses defaults if None)
    """
    if csrf_config is None:
        csrf_config = CSRFConfig()

    # Add CSRF middleware
    app.add_middleware(CSRFMiddleware, exempt_paths=csrf_config.exempt_paths)

    # Add CSRF token endpoint
    @app.get("/csrf-token")
    async def get_csrf_token(request: Request):
        """
        Get CSRF token for the current session.
        Returns the CSRF token that should be included in state-changing requests.
        """
        from app.secure_session import get_session_from_request

        config = get_config()
        session_data = await get_session_from_request(request, config.secret_key)

        if not session_data:
            raise HTTPException(
                status_code=401,
                detail="Authentication required to get CSRF token"
            )

        csrf_token = session_data.get("csrf_token")
        if not csrf_token:
            raise HTTPException(
                status_code=500,
                detail="CSRF token not found in session"
            )

        return {
            "success": True,
            "csrf_token": csrf_token,
            "header_name": csrf_config.header_name,
            "cookie_name": csrf_config.cookie_name,
        }

    logger.info(
        "[CSRF-PROTECTION] CSRF middleware enabled",
        extra={
            "exempt_paths": csrf_config.exempt_paths,
            "cookie_name": csrf_config.cookie_name,
            "header_name": csrf_config.header_name,
            "require_https": csrf_config.require_https,
        }
    )


# Utility functions for manual CSRF validation (if needed)
async def require_csrf_token(request: Request, token: str = None) -> bool:
    """
    Manually require and validate CSRF token.

    Args:
        request: FastAPI request
        token: CSRF token (auto-extracted if None)

    Returns:
        True if token is valid

    Raises:
        HTTPException: If token is missing or invalid
    """
    config = get_config()

    if token is None:
        # Extract token from request
        middleware = CSRFMiddleware(None)
        token = await middleware._extract_csrf_token(request)

    if not token:
        raise HTTPException(
            status_code=403,
            detail="CSRF token required"
        )

    is_valid = await verify_csrf_token(request, token, config.secret_key)
    if not is_valid:
        raise HTTPException(
            status_code=403,
            detail="Invalid CSRF token"
        )

    return True


def csrf_exempt(func):
    """
    Decorator to mark a route as exempt from CSRF protection.
    Note: This should be used sparingly and only for routes that are inherently safe
    or have alternative protection mechanisms.
    """
    func.__csrf_exempt__ = True
    return func
