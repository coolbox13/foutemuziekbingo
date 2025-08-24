"""
FastAPI application factory with comprehensive middleware stack.
Includes security, rate limiting, CORS, and monitoring.
"""

from fastapi import HTTPException, FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.responses import Response
from fastapi.templating import Jinja2Templates
import os
import logging
import asyncio
from logging.handlers import RotatingFileHandler
from datetime import datetime, timezone

from app.config import get_config
from app.routes import register_routes
from app.database import database
from app.csrf_middleware import add_csrf_protection, CSRFConfig
from app.cors_config import get_cors_config, get_cors_security_report
from app.cache_manager import get_cache_manager
from app.rate_limiter import (
    RateLimitMiddleware,
    create_default_rate_limiter,
    RateLimitRule,
    RateLimitAlgorithm,
    RateLimitScope
)


def create_app() -> FastAPI:
    """Create and configure the FastAPI application with modern middleware stack."""
    # Get configuration (handles .env loading internally)
    config = get_config()

    app = FastAPI(
        title="Foute Muziek Bingo",
        description="Modern musical bingo application with real-time gameplay",
        version="2.0.0",
        docs_url="/docs" if config.app_env != "production" else None,
        redoc_url="/redoc" if config.app_env != "production" else None,
    )

    # =============================================
    # MIDDLEWARE CONFIGURATION (order matters!)
    # =============================================

    # 1. CORS middleware (must be first for preflight requests)
    cors_config = get_cors_config()
    cors_settings = cors_config.get_cors_config()

    app.add_middleware(
        CORSMiddleware,
        **cors_settings
    )

    # 2. Rate limiting middleware (before authentication)
    rate_limiter = create_default_rate_limiter()

    # Add specialized rate limit rules
    if config.app_env == "production":
        # Stricter production limits
        rate_limiter.add_rule("api_strict", RateLimitRule(
            requests=30,
            window_seconds=60,
            algorithm=RateLimitAlgorithm.SLIDING_WINDOW,
            scope=RateLimitScope.IP,
            paths={"/api/"},
            block_duration_seconds=120,
            warning_threshold=0.7
        ))

        # Very strict for critical operations
        rate_limiter.add_rule("critical", RateLimitRule(
            requests=3,
            window_seconds=300,  # 5 minutes
            algorithm=RateLimitAlgorithm.SLIDING_WINDOW,
            scope=RateLimitScope.IP,
            paths={"/api/games/create", "/api/cards/generate"},
            block_duration_seconds=900,  # 15 minutes
            warning_threshold=0.3
        ))

    app.add_middleware(
        RateLimitMiddleware,
        limiter=rate_limiter,
        default_rule="default",
        exempt_paths={
            "/health",
            "/ready",
            "/metrics",
            "/docs",
            "/redoc",
            "/openapi.json",
            "/static/",
            "/favicon.ico"
        }
    )

    # 3. CSRF protection middleware (after rate limiting, before routes)
    csrf_config = CSRFConfig(
        exempt_paths=[
            "/auth/login",
            "/auth/spotify/callback",
            "/health",
            "/ready",
            "/metrics",
            "/docs",
            "/redoc",
            "/openapi.json",
            "/static/",
            "/favicon.ico"
        ],
        require_https=(config.app_env == "production")
    )
    add_csrf_protection(app, csrf_config)

    # =============================================
    # STATIC FILES AND TEMPLATES
    # =============================================

    # Mount static files
    app.mount("/static", StaticFiles(directory="static"), name="static")

    # Configure Jinja2 templates
    templates = Jinja2Templates(directory="templates")

    # =============================================
    # LOGGING CONFIGURATION
    # =============================================

    if not os.path.exists("logs"):
        os.makedirs("logs")

    # Enhanced logging format
    log_format = (
        "%(asctime)s [%(process)d] [%(levelname)s] "
        "%(name)s: %(message)s [%(pathname)s:%(lineno)d]"
    )

    file_handler = RotatingFileHandler(
        "logs/music_bingo.log",
        maxBytes=50 * 1024 * 1024,  # 50MB
        backupCount=10
    )
    file_handler.setFormatter(logging.Formatter(log_format))
    file_handler.setLevel(logging.INFO)

    logger = logging.getLogger("music_bingo")
    logger.addHandler(file_handler)
    logger.setLevel(logging.INFO if config.app_env != "development" else logging.DEBUG)
    logger.info(f"Music Bingo startup - Environment: {config.app_env}")

    # =============================================
    # APPLICATION LIFECYCLE EVENTS
    # =============================================

    @app.on_event("startup")
    async def startup_event():
        """Initialize application dependencies on startup."""
        logger.info("Initializing application dependencies...")

        # 1. Initialize database connection
        try:
            await database.initialize()
            logger.info("Database connection initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            if config.app_env == "production":
                raise  # Fail fast in production

        # 2. Initialize Redis session store
        try:
            from app.redis_session_store import get_redis_session_store
            store = get_redis_session_store()
            health = await store.health_check()
            if health["healthy"]:
                logger.info("Redis session store initialized successfully")
            else:
                logger.warning(f"Redis session store health check failed: {health}")
        except Exception as e:
            logger.error(f"Failed to initialize Redis session store: {e}")
            if config.app_env == "production":
                raise

        # 3. Start Spotify token maintenance task
        await _start_token_maintenance_task()

        # 4. Log startup completion
        logger.info(
            f"Application startup complete - Environment: {config.app_env}, "
            "Rate limiting: enabled, CSRF: enabled, Redis: enabled"
        )

    @app.on_event("shutdown")
    async def shutdown_event():
        """Cleanup resources on shutdown."""
        logger.info("Application shutting down...")

        try:
            # Close Redis connections
            from app.redis_session_store import cleanup_redis_session_store
            await cleanup_redis_session_store()
            logger.info("Redis connections closed")
        except Exception as e:
            logger.error(f"Error closing Redis connections: {e}")

        try:
            # Close database connections
            await database.disconnect()
            logger.info("Database connections closed")
        except Exception as e:
            logger.error(f"Error closing database connections: {e}")

        logger.info("Application shutdown complete")

    async def _start_token_maintenance_task():
        """Start background task for Spotify token maintenance."""
        async def _token_maintenance_loop():
            """Background loop for proactive Spotify token refresh."""
            from app.secure_session import get_sessions_snapshot, update_session_token_info
            from app.spotify import get_spotify_oauth
            from spotipy.oauth2 import SpotifyOAuth
            import time

            sp_oauth: SpotifyOAuth = get_spotify_oauth()
            check_interval = config.spotify_token_maintenance_interval
            safety_window = config.spotify_token_safety_window

            logger.info(
                "[SPOTIFY-MAINT] Starting token maintenance loop "
                f"(interval: {check_interval}s, safety: {safety_window}s)"
            )

            while True:
                try:
                    snapshot = get_sessions_snapshot()
                    now_epoch = time.time()
                    refreshed_count = 0

                    for token, data in snapshot.items():
                        token_info = data.get("token_info") or {}
                        refresh_token = token_info.get("refresh_token")
                        expires_at = token_info.get("expires_at")

                        if not refresh_token:
                            continue

                        # Check if token needs refresh
                        needs_refresh = False
                        try:
                            needs_refresh = (not expires_at) or (
                                now_epoch > float(expires_at) - safety_window
                            )
                        except (ValueError, TypeError):
                            needs_refresh = True

                        if not needs_refresh:
                            continue

                        try:
                            refreshed = sp_oauth.refresh_access_token(refresh_token)
                            update_session_token_info(token, refreshed)
                            refreshed_count += 1
                            logger.debug(f"[SPOTIFY-MAINT] Token refreshed for session {token[:8]}...")
                        except Exception as e:
                            logger.warning(
                                f"[SPOTIFY-MAINT] Failed to refresh token for session {token[:8]}...: {e}"
                            )

                    if refreshed_count > 0:
                        logger.info(f"[SPOTIFY-MAINT] Refreshed {refreshed_count} tokens")

                except Exception as loop_err:
                    logger.error(f"[SPOTIFY-MAINT] Maintenance loop error: {loop_err}")
                finally:
                    await asyncio.sleep(check_interval)

        try:
            asyncio.create_task(_token_maintenance_loop())
            logger.info("[SPOTIFY-MAINT] Token maintenance task started successfully")
        except Exception as e:
            logger.error(f"[SPOTIFY-MAINT] Failed to start maintenance task: {e}")

    # =============================================
    # ROUTE REGISTRATION
    # =============================================

    register_routes(app)

    # =============================================
    # CORE APPLICATION ROUTES
    # =============================================

    @app.get("/", response_class=HTMLResponse)
    async def root(request: Request):
        """Root endpoint - show login page for unauthenticated users, proper home for authenticated."""
        try:
            from app.secure_session import get_session_from_request

            session_data = await get_session_from_request(request, config.secret_key)
            if session_data and session_data.get("user"):
                # Show proper authenticated home page (not redirect loop)
                return templates.TemplateResponse("homepage.html", {
                    "request": request,
                    "authenticated": True,
                    "user": session_data.get("user")
                })
        except Exception as e:
            logger.debug(f"Session check failed in root route: {e}")

        # Show login/welcome page for unauthenticated users
        return templates.TemplateResponse("homepage.html", {
            "request": request,
            "authenticated": False
        })

    # =============================================
    # HEALTH AND MONITORING ENDPOINTS
    # =============================================

    @app.get("/health")
    async def health_check():
        """Comprehensive health check endpoint for monitoring."""
        from app.config import validate_config_health
        from app.redis_session_store import get_redis_session_store

        try:
            # Check configuration health
            config_health = validate_config_health()

            # Check session store health
            session_store = get_redis_session_store()
            session_health = await session_store.health_check()
            session_stats = await session_store.get_session_stats()

            # Check cache manager health
            cache_manager = get_cache_manager()
            cache_health = await cache_manager.health_check()
            cache_stats = await cache_manager.get_cache_stats()

            # Check CORS security configuration
            cors_security = get_cors_security_report()

            # Check rate limiter health
            rate_limiter_stats = rate_limiter.get_statistics()
            rate_limiter_backend_stats = await rate_limiter.backend.get_statistics()

            # Overall health assessment
            is_healthy = (
                config_health["healthy"] and
                session_health.get("healthy", False)
            )

            return {
                "status": "healthy" if is_healthy else "unhealthy",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "environment": config.app_env,
                "version": "2.0.0",
                "checks": {
                    "configuration": config_health,
                    "session_store": session_health,
                    "cache_manager": cache_health,
                    "cors_security": cors_security,
                    "rate_limiter": {
                        **rate_limiter_stats,
                        "backend": rate_limiter_backend_stats
                    }
                },
                "statistics": {
                    "sessions": session_stats,
                    "cache": cache_stats,
                    "uptime_hours": None,  # Could add application uptime tracking
                }
            }

        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return {
                "status": "unhealthy",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "error": str(e)
            }

    @app.get("/ready")
    async def readiness_check():
        """Kubernetes-style readiness check for deployment orchestration."""
        try:
            ready = True
            services = {}
            checks = []

            # Check session store readiness
            try:
                from app.redis_session_store import get_redis_session_store
                store = get_redis_session_store()
                health = await store.health_check()

                if health.get("healthy"):
                    services["session_store"] = "ready"
                    checks.append("session_store: ready")
                else:
                    services["session_store"] = "not_ready"
                    checks.append(f"session_store: not_ready - {health.get('error', 'unknown')}")
                    ready = False
            except Exception as e:
                services["session_store"] = "error"
                checks.append(f"session_store: error - {e}")
                ready = False

            # Check database readiness (if needed)
            try:
                # Add database check if required
                services["database"] = "ready"  # Placeholder
                checks.append("database: ready")
            except Exception as e:
                services["database"] = "not_ready"
                checks.append(f"database: not_ready - {e}")
                ready = False

            return {
                "ready": ready,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "services": services,
                "checks": checks
            }

        except Exception as e:
            logger.error(f"Readiness check failed: {e}")
            return {
                "ready": False,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "error": str(e),
                "services": {"global": "error"}
            }

    @app.get("/metrics")
    async def metrics_endpoint():
        """Basic metrics endpoint for monitoring (Prometheus-compatible format available)."""
        try:
            from app.redis_session_store import get_redis_session_store

            # Gather metrics from various components
            session_store = get_redis_session_store()
            session_stats = await session_store.get_session_stats()

            rate_limiter_stats = rate_limiter.get_statistics()

            # Format as Prometheus-style metrics
            metrics_lines = []

            # Session metrics
            metrics_lines.extend([
                "# HELP sessions_active Number of active sessions",
                "# TYPE sessions_active gauge",
                f"sessions_active {session_stats.get('active_sessions', 0)}",
                "# HELP sessions_total Total sessions created",
                "# TYPE sessions_total counter",
                f"sessions_total {session_stats.get('total_sessions_created', 0)}",
            ])

            # Enhanced Rate limiting metrics from analytics
            rate_prometheus_metrics = rate_limiter.get_prometheus_metrics()
            metrics_lines.extend(rate_prometheus_metrics)

            # Additional security metrics
            abuse_patterns = rate_limiter.get_abuse_patterns()
            metrics_lines.extend([
                "# HELP rate_limit_abuse_patterns_detected Security abuse patterns detected",
                "# TYPE rate_limit_abuse_patterns_detected gauge",
                f"rate_limit_abuse_patterns_detected {len(abuse_patterns)}",
            ])


            # Cache metrics
            metrics_lines.extend([
                "# HELP cache_keys_total Total number of cache keys",
                "# TYPE cache_keys_total gauge",
                f"cache_keys_total {cache_stats.total_keys}",
                "# HELP cache_memory_bytes Memory used by cache",
                "# TYPE cache_memory_bytes gauge",
                f"cache_memory_bytes {cache_stats.total_memory}",
                "# HELP cache_hit_rate_percent Cache hit rate percentage",
                "# TYPE cache_hit_rate_percent gauge",
                f"cache_hit_rate_percent {cache_stats.hit_rate}",
            ])

            return Response(
                content="\n".join(metrics_lines) + "\n",
                media_type="text/plain"
            )

        except Exception as e:
            logger.error(f"Metrics endpoint failed: {e}")
            return {
                "error": "Metrics collection failed",
                "message": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

    # ===== GLOBAL EXCEPTION HANDLERS =====
    from app.error_handlers import ErrorResponse, ErrorMessages
    from fastapi.responses import JSONResponse

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        """Handle HTTP exceptions with standardized format."""
        logger.warning(
            f"HTTP exception: {exc.status_code} - {exc.detail}",
            extra={
                "path": request.url.path,
                "method": request.method,
                "status_code": exc.status_code
            }
        )

        # If detail is already structured (from our ErrorResponse), return as-is
        if isinstance(exc.detail, dict) and "error" in exc.detail:
            return JSONResponse(
                status_code=exc.status_code,
                content=exc.detail
            )

        # Convert simple string details to standardized format
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": "http_error",
                "message": str(exc.detail),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        """Handle unexpected exceptions with standardized error response."""
        error_id = f"err_{datetime.now().timestamp()}"

        logger.error(
            f"Unhandled exception [{error_id}]: {str(exc)}",
            extra={
                "path": request.url.path,
                "method": request.method,
                "error_id": error_id,
                "exception_type": type(exc).__name__
            },
            exc_info=True
        )

        # Use standardized internal server error response
        error_response = ErrorResponse.internal_server_error(
            "An unexpected error occurred",
            error=exc,
            operation=f"{request.method} {request.url.path}"
        )

        return JSONResponse(
            status_code=500,
            content=error_response.detail
        )

    return app

    # =============================================
    # GLOBAL EXCEPTION HANDLERS
    # =============================================

    from app.error_handlers import ErrorResponse, ErrorMessages
    from fastapi.responses import JSONResponse

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        """Handle HTTP exceptions with standardized format."""
        logger.warning(
            f"HTTP exception: {exc.status_code} - {exc.detail}",
            extra={
                "path": request.url.path,
                "method": request.method,
                "status_code": exc.status_code
            }
        )

        # If detail is already structured (from our ErrorResponse), return as-is
        if isinstance(exc.detail, dict) and "error" in exc.detail:
            return JSONResponse(
                status_code=exc.status_code,
                content=exc.detail
            )

        # Convert simple string details to standardized format
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": "http_error",
                "message": str(exc.detail),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        """Handle unexpected exceptions with standardized error response."""
        error_id = f"err_{datetime.now().timestamp()}"

        logger.error(
            f"Unhandled exception [{error_id}]: {str(exc)}",
            extra={
                "path": request.url.path,
                "method": request.method,
                "error_id": error_id,
                "exception_type": type(exc).__name__
            },
            exc_info=True
        )

        # Use standardized internal server error response
        error_response = ErrorResponse.internal_server_error(
            "An unexpected error occurred",
            error=exc,
            operation=f"{request.method} {request.url.path}"
        )

        return JSONResponse(
            status_code=500,
            content=error_response.detail
        )

    @app.exception_handler(ValueError)
    async def value_error_handler(request: Request, exc: ValueError):
        """Handle ValueError with bad request response."""
        logger.warning(
            f"ValueError: {str(exc)}",
            extra={
                "path": request.url.path,
                "method": request.method,
                "exception_type": "ValueError"
            }
        )

        error_response = ErrorResponse.bad_request(
            "Invalid input provided",
            details=str(exc)
        )

        return JSONResponse(
            status_code=400,
            content=error_response.detail
        )

    return app
