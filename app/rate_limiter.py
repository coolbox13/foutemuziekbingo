"""
State-of-the-art async rate limiting middleware using Redis/Dragonfly.
Implements token bucket and sliding window algorithms with advanced features.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Dict, Optional, Set, Any, Protocol, TypeVar
from datetime import datetime, timezone, timedelta
from enum import Enum, auto
from contextlib import asynccontextmanager

import redis.asyncio as redis
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import get_config

logger = logging.getLogger("music_bingo")

T = TypeVar('T')


class RateLimitAlgorithm(Enum):
    """Rate limiting algorithms."""
    TOKEN_BUCKET = auto()
    SLIDING_WINDOW = auto()
    FIXED_WINDOW = auto()
    SLIDING_LOG = auto()


class RateLimitScope(Enum):
    """Rate limiting scopes."""
    GLOBAL = auto()         # Global rate limit
    IP = auto()            # Per IP address
    USER = auto()          # Per authenticated user
    SESSION = auto()       # Per session
    ENDPOINT = auto()      # Per endpoint


@dataclass(frozen=True)
class RateLimitRule:
    """Configuration for a rate limit rule."""

    # Core configuration
    requests: int                           # Number of requests allowed
    window_seconds: int                     # Time window in seconds
    algorithm: RateLimitAlgorithm          # Rate limiting algorithm
    scope: RateLimitScope                  # Scope of the rate limit

    # Advanced configuration
    burst_requests: Optional[int] = None    # Additional burst capacity
    burst_window_seconds: Optional[int] = None  # Burst window duration

    # Targeting
    paths: Optional[Set[str]] = None        # Specific paths (None = all paths)
    methods: Optional[Set[str]] = None      # HTTP methods (None = all methods)
    user_agents: Optional[Set[str]] = None  # Specific user agents

    # Behavior
    block_duration_seconds: int = field(default=60)  # How long to block after limit
    warning_threshold: float = field(default=0.8)    # Warn at 80% of limit
    exempt_ips: Set[str] = field(default_factory=set)  # IPs exempt from limits

    # Response customization
    custom_headers: Dict[str, str] = field(default_factory=dict)
    custom_error_message: Optional[str] = None


@dataclass
class RateLimitStatus:
    """Current rate limit status for a key."""

    remaining: int                          # Requests remaining
    limit: int                              # Total requests allowed
    reset_at: datetime                      # When the limit resets
    retry_after: Optional[int] = None       # Seconds until retry allowed
    blocked_until: Optional[datetime] = None  # When block expires
    algorithm: RateLimitAlgorithm = RateLimitAlgorithm.TOKEN_BUCKET

    @property
    def is_blocked(self) -> bool:
        """Check if currently blocked."""
        if self.blocked_until is None:
            return False
        return datetime.now(timezone.utc) < self.blocked_until

    @property
    def is_warning(self) -> bool:
        """Check if approaching limit."""
        return self.remaining / self.limit < 0.2  # Warn at 20% remaining


class RateLimitBackend(Protocol):
    """Protocol for rate limit storage backends."""

    async def check_rate_limit(
        self,
        key: str,
        rule: RateLimitRule
    ) -> RateLimitStatus:
        """Check if request is allowed under rate limit."""
        ...

    async def increment_counter(
        self,
        key: str,
        rule: RateLimitRule
    ) -> RateLimitStatus:
        """Increment counter and return updated status."""
        ...

    async def reset_rate_limit(self, key: str) -> bool:
        """Reset rate limit for a key."""
        ...

    async def get_statistics(self) -> Dict[str, Any]:
        """Get rate limiting statistics."""
        ...


class RedisRateLimitBackend:
    """Redis-based rate limiting backend with Lua scripts for atomicity."""

    def __init__(self, redis_client: redis.Redis = None):
        """Initialize Redis backend."""
        self.redis = redis_client
        self._connection_lock = asyncio.Lock()
        self._lua_scripts: Dict[str, Any] = {}

    async def _get_redis(self) -> redis.Redis:
        """Get Redis connection."""
        if self.redis is None:
            async with self._connection_lock:
                if self.redis is None:
                    config = get_config()
                    connection_kwargs = {"decode_responses": True}
                    if config.redis_password:
                        connection_kwargs["password"] = config.redis_password

                    self.redis = redis.from_url(
                        config.dragonfly_url,
                        **connection_kwargs,
                        socket_connect_timeout=5,
                        socket_timeout=5,
                        retry_on_timeout=True,
                        health_check_interval=30
                    )

                    await self.redis.ping()
                    await self._load_lua_scripts()
                    logger.info("Redis rate limiter backend connected")

        return self.redis

    async def _load_lua_scripts(self):
        """Load Lua scripts for atomic operations."""
        redis_client = await self._get_redis()

        # Token bucket algorithm script
        token_bucket_script = """
        local key = KEYS[1]
        local capacity = tonumber(ARGV[1])
        local tokens = tonumber(ARGV[2])
        local window = tonumber(ARGV[3])
        local now = tonumber(ARGV[4])

        local bucket = redis.call('HMGET', key, 'tokens', 'last_refill')
        local current_tokens = tonumber(bucket[1]) or capacity
        local last_refill = tonumber(bucket[2]) or now

        -- Calculate tokens to add based on time passed
        local elapsed = math.max(0, now - last_refill)
        local tokens_to_add = math.floor((elapsed / window) * capacity)
        current_tokens = math.min(capacity, current_tokens + tokens_to_add)

        local allowed = current_tokens >= tokens
        if allowed then
            current_tokens = current_tokens - tokens
        end

        -- Update bucket state
        redis.call('HMSET', key, 'tokens', current_tokens, 'last_refill', now)
        redis.call('EXPIRE', key, window * 2)

        return {allowed and 1 or 0, current_tokens, capacity}
        """

        # Sliding window algorithm script
        sliding_window_script = """
        local key = KEYS[1]
        local window = tonumber(ARGV[1])
        local limit = tonumber(ARGV[2])
        local now = tonumber(ARGV[3])
        local identifier = ARGV[4]

        -- Remove old entries
        redis.call('ZREMRANGEBYSCORE', key, 0, now - window)

        -- Count current entries
        local current = redis.call('ZCARD', key)

        local allowed = current < limit
        if allowed then
            -- Add new entry
            redis.call('ZADD', key, now, identifier)
            redis.call('EXPIRE', key, window)
        end

        return {allowed and 1 or 0, limit - current - (allowed and 1 or 0), limit}
        """

        self._lua_scripts = {
            'token_bucket': await redis_client.script_load(token_bucket_script),
            'sliding_window': await redis_client.script_load(sliding_window_script)
        }

        logger.debug("Rate limiting Lua scripts loaded")

    async def check_rate_limit(
        self,
        key: str,
        rule: RateLimitRule
    ) -> RateLimitStatus:
        """Check rate limit without incrementing."""
        redis_client = await self._get_redis()
        now = time.time()

        try:
            if rule.algorithm == RateLimitAlgorithm.TOKEN_BUCKET:
                # Check token bucket status
                bucket = await redis_client.hmget(
                    f"rate_limit:{key}",
                    'tokens', 'last_refill'
                )
                current_tokens = int(bucket[0] or rule.requests)
                last_refill = float(bucket[1] or now)

                # Calculate available tokens
                elapsed = max(0, now - last_refill)
                tokens_to_add = int((elapsed / rule.window_seconds) * rule.requests)
                available_tokens = min(rule.requests, current_tokens + tokens_to_add)

                reset_at = datetime.fromtimestamp(
                    now + (rule.requests - available_tokens) * (rule.window_seconds / rule.requests),
                    timezone.utc
                )

                return RateLimitStatus(
                    remaining=available_tokens,
                    limit=rule.requests,
                    reset_at=reset_at,
                    algorithm=rule.algorithm
                )

            elif rule.algorithm == RateLimitAlgorithm.SLIDING_WINDOW:
                # Check sliding window status
                window_key = f"rate_limit_window:{key}"
                await redis_client.zremrangebyscore(
                    window_key, 0, now - rule.window_seconds
                )
                current_count = await redis_client.zcard(window_key)

                reset_at = datetime.fromtimestamp(now + rule.window_seconds, timezone.utc)

                return RateLimitStatus(
                    remaining=max(0, rule.requests - current_count),
                    limit=rule.requests,
                    reset_at=reset_at,
                    algorithm=rule.algorithm
                )

            else:
                # Default fallback
                return RateLimitStatus(
                    remaining=rule.requests,
                    limit=rule.requests,
                    reset_at=datetime.fromtimestamp(now + rule.window_seconds, timezone.utc),
                    algorithm=rule.algorithm
                )

        except Exception as e:
            logger.error(f"Error checking rate limit: {e}")
            # Fail open - allow request if Redis fails
            return RateLimitStatus(
                remaining=rule.requests,
                limit=rule.requests,
                reset_at=datetime.fromtimestamp(now + rule.window_seconds, timezone.utc),
                algorithm=rule.algorithm
            )

    async def increment_counter(
        self,
        key: str,
        rule: RateLimitRule
    ) -> RateLimitStatus:
        """Increment rate limit counter."""
        redis_client = await self._get_redis()
        now = time.time()

        try:
            if rule.algorithm == RateLimitAlgorithm.TOKEN_BUCKET:
                result = await redis_client.evalsha(
                    self._lua_scripts['token_bucket'],
                    1,  # Number of keys
                    f"rate_limit:{key}",  # Key
                    rule.requests,        # Capacity
                    1,                    # Tokens requested
                    rule.window_seconds,  # Window
                    now                   # Current time
                )

                allowed, remaining, limit = result
                reset_at = datetime.fromtimestamp(
                    now + (rule.requests - remaining) * (rule.window_seconds / rule.requests),
                    timezone.utc
                )

                status = RateLimitStatus(
                    remaining=remaining,
                    limit=limit,
                    reset_at=reset_at,
                    algorithm=rule.algorithm
                )

                if not allowed:
                    status.retry_after = int(rule.window_seconds / rule.requests)
                    status.blocked_until = datetime.fromtimestamp(
                        now + rule.block_duration_seconds, timezone.utc
                    )

                return status

            elif rule.algorithm == RateLimitAlgorithm.SLIDING_WINDOW:
                result = await redis_client.evalsha(
                    self._lua_scripts['sliding_window'],
                    1,  # Number of keys
                    f"rate_limit_window:{key}",  # Key
                    rule.window_seconds,         # Window
                    rule.requests,               # Limit
                    now,                         # Current time
                    f"{now}:{id(self)}"         # Unique identifier
                )

                allowed, remaining, limit = result
                reset_at = datetime.fromtimestamp(now + rule.window_seconds, timezone.utc)

                status = RateLimitStatus(
                    remaining=remaining,
                    limit=limit,
                    reset_at=reset_at,
                    algorithm=rule.algorithm
                )

                if not allowed:
                    status.retry_after = rule.window_seconds
                    status.blocked_until = datetime.fromtimestamp(
                        now + rule.block_duration_seconds, timezone.utc
                    )

                return status

        except Exception as e:
            logger.error(f"Error incrementing rate limit counter: {e}")
            # Fail open - allow request if Redis fails
            return RateLimitStatus(
                remaining=rule.requests - 1,
                limit=rule.requests,
                reset_at=datetime.fromtimestamp(now + rule.window_seconds, timezone.utc),
                algorithm=rule.algorithm
            )

    async def reset_rate_limit(self, key: str) -> bool:
        """Reset rate limit for a key."""
        try:
            redis_client = await self._get_redis()
            deleted = await redis_client.delete(
                f"rate_limit:{key}",
                f"rate_limit_window:{key}"
            )
            return deleted > 0
        except Exception as e:
            logger.error(f"Error resetting rate limit: {e}")
            return False

    async def get_statistics(self) -> Dict[str, Any]:
        """Get rate limiting statistics."""
        try:
            redis_client = await self._get_redis()

            # Count rate limit keys
            rate_limit_keys = 0
            async for _ in redis_client.scan_iter(match="rate_limit:*"):
                rate_limit_keys += 1

            window_keys = 0
            async for _ in redis_client.scan_iter(match="rate_limit_window:*"):
                window_keys += 1

            return {
                "backend": "Redis",
                "token_bucket_keys": rate_limit_keys,
                "sliding_window_keys": window_keys,
                "total_keys": rate_limit_keys + window_keys,
                "scripts_loaded": len(self._lua_scripts)
            }
        except Exception as e:
            logger.error(f"Error getting rate limit statistics: {e}")
            return {"backend": "Redis", "error": str(e)}


class AsyncRateLimiter:
    """Advanced async rate limiter with multiple algorithms and scopes."""

    def __init__(
        self,
        backend: RateLimitBackend = None,
        default_rules: Optional[Dict[str, RateLimitRule]] = None
    ):
        """Initialize rate limiter."""
        self.backend = backend or RedisRateLimitBackend()
        self.rules: Dict[str, RateLimitRule] = default_rules or {}
        self._stats = {
            "requests_checked": 0,
            "requests_blocked": 0,
            "requests_warned": 0,
        }

    def add_rule(self, name: str, rule: RateLimitRule) -> None:
        """Add a rate limiting rule."""
        self.rules[name] = rule
        logger.info(f"Added rate limit rule: {name} - {rule.requests} requests per {rule.window_seconds}s")

    async def is_allowed(
        self,
        request: Request,
        rule_name: str = "default"
    ) -> tuple[bool, RateLimitStatus]:
        """Check if request is allowed."""
        self._stats["requests_checked"] += 1

        rule = self.rules.get(rule_name)
        if not rule:
            logger.warning(f"Rate limit rule '{rule_name}' not found")
            # Default permissive status
            return True, RateLimitStatus(
                remaining=1000,
                limit=1000,
                reset_at=datetime.now(timezone.utc) + timedelta(hours=1)
            )

        # Generate rate limit key based on scope
        key = await self._generate_key(request, rule)

        # Check if IP is exempt
        client_ip = self._get_client_ip(request)
        if client_ip in rule.exempt_ips:
            return True, RateLimitStatus(
                remaining=rule.requests,
                limit=rule.requests,
                reset_at=datetime.now(timezone.utc) + timedelta(seconds=rule.window_seconds)
            )

        # Check if request matches rule criteria
        if not self._matches_rule(request, rule):
            return True, RateLimitStatus(
                remaining=rule.requests,
                limit=rule.requests,
                reset_at=datetime.now(timezone.utc) + timedelta(seconds=rule.window_seconds)
            )

        # Check rate limit
        status = await self.backend.increment_counter(key, rule)

        # Update statistics
        if status.is_blocked:
            self._stats["requests_blocked"] += 1
        elif status.is_warning:
            self._stats["requests_warned"] += 1

        return status.remaining > 0, status

    async def _generate_key(self, request: Request, rule: RateLimitRule) -> str:
        """Generate rate limit key based on scope."""
        base_key = "rate_limit"

        if rule.scope == RateLimitScope.GLOBAL:
            return f"{base_key}:global"

        elif rule.scope == RateLimitScope.IP:
            client_ip = self._get_client_ip(request)
            return f"{base_key}:ip:{client_ip}"

        elif rule.scope == RateLimitScope.USER:
            # Try to get user ID from session
            user_id = await self._get_user_id(request)
            if user_id:
                return f"{base_key}:user:{user_id}"
            else:
                # Fallback to IP if no user
                client_ip = self._get_client_ip(request)
                return f"{base_key}:ip:{client_ip}"

        elif rule.scope == RateLimitScope.SESSION:
            session_id = await self._get_session_id(request)
            if session_id:
                return f"{base_key}:session:{session_id}"
            else:
                # Fallback to IP if no session
                client_ip = self._get_client_ip(request)
                return f"{base_key}:ip:{client_ip}"

        elif rule.scope == RateLimitScope.ENDPOINT:
            endpoint = f"{request.method}:{request.url.path}"
            client_ip = self._get_client_ip(request)
            return f"{base_key}:endpoint:{endpoint}:ip:{client_ip}"

        else:
            # Default to IP-based
            client_ip = self._get_client_ip(request)
            return f"{base_key}:ip:{client_ip}"

    def _get_client_ip(self, request: Request) -> str:
        """Get client IP address with proxy support."""
        # Check X-Forwarded-For header (most common)
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            # Take the first IP in the chain
            return forwarded.split(",")[0].strip()

        # Check X-Real-IP header
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip.strip()

        # Fallback to direct connection
        return request.client.host if request.client else "unknown"

    async def _get_user_id(self, request: Request) -> Optional[str]:
        """Extract user ID from session."""
        try:
            from app.secure_session import get_session_from_request
            from app.config import get_config

            config = get_config()
            session_data = await get_session_from_request(request, config.secret_key)
            return session_data.get("user_id") if session_data else None
        except Exception:
            return None

    async def _get_session_id(self, request: Request) -> Optional[str]:
        """Extract session ID from request."""
        try:
            from app.secure_session import get_session_token_from_request
            return await get_session_token_from_request(request)
        except Exception:
            return None

    def _matches_rule(self, request: Request, rule: RateLimitRule) -> bool:
        """Check if request matches rule criteria."""
        # Check paths
        if rule.paths:
            if not any(request.url.path.startswith(path) for path in rule.paths):
                return False

        # Check methods
        if rule.methods:
            if request.method not in rule.methods:
                return False

        # Check user agents
        if rule.user_agents:
            user_agent = request.headers.get("User-Agent", "")
            if not any(ua in user_agent for ua in rule.user_agents):
                return False

        return True

    async def reset_limit(self, request: Request, rule_name: str = "default") -> bool:
        """Reset rate limit for a request."""
        rule = self.rules.get(rule_name)
        if not rule:
            return False

        key = await self._generate_key(request, rule)
        return await self.backend.reset_rate_limit(key)

    def get_statistics(self) -> Dict[str, Any]:
        """Get rate limiter statistics."""
        return {
            **self._stats,
            "rules_configured": len(self.rules),
            "rule_names": list(self.rules.keys())
        }


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limiting middleware for FastAPI."""

    def __init__(
        self,
        app,
        limiter: AsyncRateLimiter = None,
        default_rule: str = "default",
        exempt_paths: Optional[Set[str]] = None
    ):
        """Initialize middleware."""
        super().__init__(app)
        self.limiter = limiter or AsyncRateLimiter()
        self.default_rule = default_rule
        self.exempt_paths = exempt_paths or {
            "/health",
            "/metrics",
            "/docs",
            "/redoc",
            "/openapi.json",
            "/static/"
        }

    async def dispatch(self, request: Request, call_next) -> Response:
        """Process request with rate limiting."""

        # Skip rate limiting for exempt paths
        if any(request.url.path.startswith(path) for path in self.exempt_paths):
            return await call_next(request)

        # Check rate limit
        allowed, status = await self.limiter.is_allowed(request, self.default_rule)

        if not allowed:
            logger.warning(
                "Rate limit exceeded",
                extra={
                    "client_ip": self.limiter._get_client_ip(request),
                    "path": request.url.path,
                    "method": request.method,
                    "remaining": status.remaining,
                    "limit": status.limit,
                    "reset_at": status.reset_at.isoformat()
                }
            )

            return self._create_rate_limit_response(status)

        # Add rate limit headers to response
        response = await call_next(request)
        self._add_rate_limit_headers(response, status)

        return response

    def _create_rate_limit_response(self, status: RateLimitStatus) -> JSONResponse:
        """Create rate limit exceeded response."""
        headers = {
            "X-RateLimit-Limit": str(status.limit),
            "X-RateLimit-Remaining": str(status.remaining),
            "X-RateLimit-Reset": str(int(status.reset_at.timestamp())),
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY"
        }

        if status.retry_after:
            headers["Retry-After"] = str(status.retry_after)

        return JSONResponse(
            status_code=429,
            content={
                "success": False,
                "error": "RATE_LIMIT_EXCEEDED",
                "message": "Too many requests. Please slow down.",
                "details": {
                    "limit": status.limit,
                    "remaining": status.remaining,
                    "reset_at": status.reset_at.isoformat(),
                    "retry_after": status.retry_after
                }
            },
            headers=headers
        )

    def _add_rate_limit_headers(self, response: Response, status: RateLimitStatus) -> None:
        """Add rate limit headers to successful response."""
        response.headers["X-RateLimit-Limit"] = str(status.limit)
        response.headers["X-RateLimit-Remaining"] = str(status.remaining)
        response.headers["X-RateLimit-Reset"] = str(int(status.reset_at.timestamp()))

        if status.is_warning:
            response.headers["X-RateLimit-Warning"] = "Approaching rate limit"


def create_default_rate_limiter() -> AsyncRateLimiter:
    """Create rate limiter with sensible default rules."""
    config = get_config()

    limiter = AsyncRateLimiter()

    # General API rate limit
    limiter.add_rule("default", RateLimitRule(
        requests=config.rate_limit_requests_per_minute,
        window_seconds=60,
        algorithm=RateLimitAlgorithm.TOKEN_BUCKET,
        scope=RateLimitScope.IP,
        burst_requests=config.rate_limit_burst_size,
        block_duration_seconds=60,
        warning_threshold=0.8
    ))

    # Strict limits for auth endpoints
    limiter.add_rule("auth", RateLimitRule(
        requests=5,
        window_seconds=60,
        algorithm=RateLimitAlgorithm.SLIDING_WINDOW,
        scope=RateLimitScope.IP,
        paths={"/auth/"},
        block_duration_seconds=300,  # 5 minutes
        warning_threshold=0.6
    ))

    # More permissive for authenticated users
    limiter.add_rule("authenticated", RateLimitRule(
        requests=config.rate_limit_requests_per_minute * 2,
        window_seconds=60,
        algorithm=RateLimitAlgorithm.TOKEN_BUCKET,
        scope=RateLimitScope.USER,
        block_duration_seconds=30,
        warning_threshold=0.9
    ))

    # Very strict for expensive operations
    limiter.add_rule("expensive", RateLimitRule(
        requests=10,
        window_seconds=300,  # 5 minutes
        algorithm=RateLimitAlgorithm.SLIDING_WINDOW,
        scope=RateLimitScope.USER,
        paths={"/api/cards/generate", "/api/games/create"},
        block_duration_seconds=600,  # 10 minutes
        warning_threshold=0.5
    ))

    return limiter


# Utility decorator for specific endpoint rate limits
def rate_limit(rule_name: str = "default"):
    """Decorator to apply specific rate limit to an endpoint."""
    def decorator(func):
        func.__rate_limit_rule__ = rule_name
        return func
    return decorator


# Context manager for temporary rate limit bypass
@asynccontextmanager
async def bypass_rate_limit(limiter: AsyncRateLimiter, request: Request, rule_name: str):
    """Temporarily bypass rate limit for specific operations."""
    key = await limiter._generate_key(request, limiter.rules[rule_name])
    # Reset the limit temporarily
    await limiter.backend.reset_rate_limit(key)
    try:
        yield
    finally:
        # Restore original status if needed
        pass  # In practice, this would restore the counter state
