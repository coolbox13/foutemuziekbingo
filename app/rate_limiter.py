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

"""
Enhanced monitoring and analytics for the rate limiter.
Adds comprehensive statistics, abuse pattern detection, and alerting.
"""
import time
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
import asyncio
import logging

logger = logging.getLogger("music_bingo")

@dataclass
class RateLimitAnalytics:
    """Comprehensive rate limiting analytics and monitoring."""

    # Basic counters
    requests_checked: int = 0
    requests_blocked: int = 0
    requests_warned: int = 0

    # Per-endpoint metrics
    endpoint_stats: Dict[str, Dict[str, int]] = field(default_factory=dict)

    # Per-rule metrics
    rule_stats: Dict[str, Dict[str, int]] = field(default_factory=dict)

    # Abuse detection
    suspicious_ips: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    blocked_users: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    # Performance metrics
    avg_processing_time_ms: float = 0.0
    total_processing_time: float = 0.0

    # Time-based metrics
    start_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_reset: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def record_request(self, rule_name: str, endpoint: str, processing_time_ms: float):
        """Record a processed request."""
        self.requests_checked += 1
        self.total_processing_time += processing_time_ms
        self.avg_processing_time_ms = self.total_processing_time / self.requests_checked

        # Per-endpoint stats
        if endpoint not in self.endpoint_stats:
            self.endpoint_stats[endpoint] = {"checked": 0, "blocked": 0, "warned": 0}
        self.endpoint_stats[endpoint]["checked"] += 1

        # Per-rule stats
        if rule_name not in self.rule_stats:
            self.rule_stats[rule_name] = {"checked": 0, "blocked": 0, "warned": 0}
        self.rule_stats[rule_name]["checked"] += 1

    def record_block(self, rule_name: str, endpoint: str, client_ip: str, user_id: Optional[str] = None):
        """Record a blocked request."""
        self.requests_blocked += 1

        # Update endpoint stats
        if endpoint in self.endpoint_stats:
            self.endpoint_stats[endpoint]["blocked"] += 1

        # Update rule stats
        if rule_name in self.rule_stats:
            self.rule_stats[rule_name]["blocked"] += 1

        # Track suspicious IP
        if client_ip not in self.suspicious_ips:
            self.suspicious_ips[client_ip] = {
                "blocks": 0,
                "first_block": datetime.now(timezone.utc),
                "last_block": datetime.now(timezone.utc),
                "endpoints": set()
            }

        self.suspicious_ips[client_ip]["blocks"] += 1
        self.suspicious_ips[client_ip]["last_block"] = datetime.now(timezone.utc)
        self.suspicious_ips[client_ip]["endpoints"].add(endpoint)

        # Track blocked user if authenticated
        if user_id:
            if user_id not in self.blocked_users:
                self.blocked_users[user_id] = {
                    "blocks": 0,
                    "first_block": datetime.now(timezone.utc),
                    "last_block": datetime.now(timezone.utc),
                    "endpoints": set()
                }

            self.blocked_users[user_id]["blocks"] += 1
            self.blocked_users[user_id]["last_block"] = datetime.now(timezone.utc)
            self.blocked_users[user_id]["endpoints"].add(endpoint)

    def record_warning(self, rule_name: str, endpoint: str):
        """Record a warning (approaching limit)."""
        self.requests_warned += 1

        if endpoint in self.endpoint_stats:
            self.endpoint_stats[endpoint]["warned"] += 1

        if rule_name in self.rule_stats:
            self.rule_stats[rule_name]["warned"] += 1

    def get_comprehensive_stats(self) -> Dict[str, Any]:
        """Get comprehensive statistics for monitoring."""
        now = datetime.now(timezone.utc)
        uptime_seconds = (now - self.start_time).total_seconds()

        # Calculate rates
        requests_per_second = self.requests_checked / max(uptime_seconds, 1)
        block_rate = (self.requests_blocked / max(self.requests_checked, 1)) * 100
        warning_rate = (self.requests_warned / max(self.requests_checked, 1)) * 100

        # Identify top problem IPs
        top_blocked_ips = sorted(
            self.suspicious_ips.items(),
            key=lambda x: x[1]["blocks"],
            reverse=True
        )[:10]

        # Identify most blocked endpoints
        top_blocked_endpoints = sorted(
            [(endpoint, stats["blocked"]) for endpoint, stats in self.endpoint_stats.items()],
            key=lambda x: x[1],
            reverse=True
        )[:10]

        return {
            # Basic metrics
            "requests_total": self.requests_checked,
            "requests_blocked_total": self.requests_blocked,
            "requests_warned_total": self.requests_warned,
            "requests_allowed_total": self.requests_checked - self.requests_blocked,

            # Rates and percentages
            "requests_per_second": round(requests_per_second, 2),
            "block_rate_percent": round(block_rate, 2),
            "warning_rate_percent": round(warning_rate, 2),
            "success_rate_percent": round(100 - block_rate, 2),

            # Performance metrics
            "avg_processing_time_ms": round(self.avg_processing_time_ms, 2),
            "total_processing_time_ms": round(self.total_processing_time, 2),

            # Time metrics
            "uptime_seconds": int(uptime_seconds),
            "uptime_hours": round(uptime_seconds / 3600, 2),
            "start_time": self.start_time.isoformat(),
            "last_reset": self.last_reset.isoformat(),

            # Detailed stats
            "endpoint_stats": dict(self.endpoint_stats),
            "rule_stats": dict(self.rule_stats),

            # Security insights
            "unique_blocked_ips": len(self.suspicious_ips),
            "unique_blocked_users": len(self.blocked_users),
            "top_blocked_ips": [(ip, stats["blocks"]) for ip, stats in top_blocked_ips],
            "top_blocked_endpoints": top_blocked_endpoints,

            # Abuse patterns
            "potential_abuse_patterns": self._detect_abuse_patterns()
        }

    def _detect_abuse_patterns(self) -> List[Dict[str, Any]]:
        """Detect potential abuse patterns."""
        patterns = []
        now = datetime.now(timezone.utc)

        # Pattern 1: High frequency blocks from single IP
        for ip, stats in self.suspicious_ips.items():
            if stats["blocks"] >= 10:  # 10+ blocks
                time_span = (stats["last_block"] - stats["first_block"]).total_seconds()
                if time_span < 300:  # Within 5 minutes
                    patterns.append({
                        "type": "rapid_fire_abuse",
                        "ip": ip,
                        "blocks": stats["blocks"],
                        "time_span_seconds": int(time_span),
                        "endpoints_hit": len(stats["endpoints"]),
                        "severity": "high" if stats["blocks"] >= 20 else "medium"
                    })

        # Pattern 2: Distributed attack (multiple IPs, same endpoints)
        endpoint_ip_map = {}
        for ip, stats in self.suspicious_ips.items():
            for endpoint in stats["endpoints"]:
                if endpoint not in endpoint_ip_map:
                    endpoint_ip_map[endpoint] = set()
                endpoint_ip_map[endpoint].add(ip)

        for endpoint, ips in endpoint_ip_map.items():
            if len(ips) >= 5:  # 5+ different IPs hitting same endpoint
                patterns.append({
                    "type": "distributed_attack",
                    "endpoint": endpoint,
                    "unique_ips": len(ips),
                    "severity": "high" if len(ips) >= 10 else "medium"
                })

        # Pattern 3: Authenticated user abuse
        for user_id, stats in self.blocked_users.items():
            if stats["blocks"] >= 5:  # 5+ blocks for authenticated user
                patterns.append({
                    "type": "authenticated_abuse",
                    "user_id": user_id,
                    "blocks": stats["blocks"],
                    "endpoints_hit": len(stats["endpoints"]),
                    "severity": "medium"
                })

        return patterns

    def reset_stats(self, keep_history: bool = False):
        """Reset statistics, optionally keeping historical data."""
        if not keep_history:
            self.__init__()
        else:
            # Keep abuse tracking but reset counters
            self.requests_checked = 0
            self.requests_blocked = 0
            self.requests_warned = 0
            self.endpoint_stats.clear()
            self.rule_stats.clear()
            self.avg_processing_time_ms = 0.0
            self.total_processing_time = 0.0
            self.last_reset = datetime.now(timezone.utc)

    def get_prometheus_metrics(self) -> List[str]:
        """Generate Prometheus-compatible metrics."""
        stats = self.get_comprehensive_stats()

        metrics = [
            # Basic counters
            "# HELP rate_limit_requests_total Total rate limiting requests processed",
            "# TYPE rate_limit_requests_total counter",
            f"rate_limit_requests_total {stats['requests_total']}",

            "# HELP rate_limit_blocks_total Total requests blocked by rate limiting",
            "# TYPE rate_limit_blocks_total counter",
            f"rate_limit_blocks_total {stats['requests_blocked_total']}",

            "# HELP rate_limit_warnings_total Total rate limiting warnings issued",
            "# TYPE rate_limit_warnings_total counter",
            f"rate_limit_warnings_total {stats['requests_warned_total']}",

            # Rates
            "# HELP rate_limit_requests_per_second Current rate of requests processed",
            "# TYPE rate_limit_requests_per_second gauge",
            f"rate_limit_requests_per_second {stats['requests_per_second']}",

            "# HELP rate_limit_block_rate_percent Percentage of requests blocked",
            "# TYPE rate_limit_block_rate_percent gauge",
            f"rate_limit_block_rate_percent {stats['block_rate_percent']}",

            # Performance
            "# HELP rate_limit_processing_time_ms Average processing time in milliseconds",
            "# TYPE rate_limit_processing_time_ms gauge",
            f"rate_limit_processing_time_ms {stats['avg_processing_time_ms']}",

            # Security
            "# HELP rate_limit_blocked_ips_total Number of unique IPs blocked",
            "# TYPE rate_limit_blocked_ips_total gauge",
            f"rate_limit_blocked_ips_total {stats['unique_blocked_ips']}",

            "# HELP rate_limit_abuse_patterns_total Number of detected abuse patterns",
            "# TYPE rate_limit_abuse_patterns_total gauge",
            f"rate_limit_abuse_patterns_total {len(stats['potential_abuse_patterns'])}",
        ]

        # Per-rule metrics
        for rule_name, rule_stats in stats["rule_stats"].items():
            rule_label = rule_name.replace("-", "_")
            metrics.extend([
                f"rate_limit_rule_requests_total{{rule=\"{rule_name}\"}} {rule_stats['checked']}",
                f"rate_limit_rule_blocks_total{{rule=\"{rule_name}\"}} {rule_stats['blocked']}",
                f"rate_limit_rule_warnings_total{{rule=\"{rule_name}\"}} {rule_stats['warned']}",
            ])

        return metrics




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
        self._analytics = RateLimitAnalytics()

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
        # Enhanced analytics handles request tracking

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

        # Update analytics
        processing_time = time.time() * 1000  # Convert to ms
        start_time = processing_time - 1  # Approximate processing time
        self._analytics.record_request(rule_name, request.url.path, processing_time - start_time)

        if status.is_blocked:
            user_id = await self._get_user_id(request)
            self._analytics.record_block(rule_name, request.url.path, client_ip, user_id)
        elif status.is_warning:
            self._analytics.record_warning(rule_name, request.url.path)

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
        """Get comprehensive rate limiter statistics with analytics."""
        stats = self._analytics.get_comprehensive_stats()
        stats.update({
            "rules_configured": len(self.rules),
            "rule_names": list(self.rules.keys()),
            "backend_stats": self.backend.get_statistics() if hasattr(self.backend, 'get_statistics') else {}
        })
        return stats

    def get_prometheus_metrics(self) -> List[str]:
        """Get Prometheus-compatible metrics."""
        return self._analytics.get_prometheus_metrics()

    def get_abuse_patterns(self) -> List[Dict[str, Any]]:
        """Get detected abuse patterns for security monitoring."""
        return self._analytics._detect_abuse_patterns()

    def reset_analytics(self, keep_history: bool = False):
        """Reset analytics data."""
        self._analytics.reset_stats(keep_history)


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
            "X-Content-Type-Options": "nosnif",
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
    """Create rate limiter with production-grade rules based on usage analysis."""
    config = get_config()

    limiter = AsyncRateLimiter()

    # General API rate limit for anonymous users
    limiter.add_rule("default", RateLimitRule(
        requests=config.rate_limit_requests_per_minute,  # Default 60
        window_seconds=60,
        algorithm=RateLimitAlgorithm.TOKEN_BUCKET,
        scope=RateLimitScope.IP,
        burst_requests=config.rate_limit_burst_size,  # Default 10
        block_duration_seconds=60,
        warning_threshold=0.8
    ))

    # Strict limits for authentication endpoints (prevent brute force)
    limiter.add_rule("auth", RateLimitRule(
        requests=5,  # Conservative for auth endpoints
        window_seconds=60,
        algorithm=RateLimitAlgorithm.SLIDING_WINDOW,
        scope=RateLimitScope.IP,
        paths={"/auth/"},
        block_duration_seconds=900,  # 15 minutes block for auth failures
        warning_threshold=0.6
    ))

    # Production limits for authenticated users (2x anonymous)
    limiter.add_rule("authenticated", RateLimitRule(
        requests=120,  # 2x config default, supports heavy usage
        window_seconds=60,
        algorithm=RateLimitAlgorithm.TOKEN_BUCKET,
        scope=RateLimitScope.USER,
        burst_requests=15,  # 1.5x dashboard load burst
        block_duration_seconds=60,  # Short block for authenticated users
        warning_threshold=0.85
    ))

    # Game and dashboard operations (bulk validation optimized)
    limiter.add_rule("game_operations", RateLimitRule(
        requests=80,  # Sufficient for active gaming with bulk validation
        window_seconds=60,
        algorithm=RateLimitAlgorithm.TOKEN_BUCKET,
        scope=RateLimitScope.USER,
        paths={"/game/api/games", "/dashboard/api/"},
        burst_requests=12,  # Dashboard load burst
        block_duration_seconds=60,
        warning_threshold=0.8
    ))

    # Card operations (generation and validation)
    limiter.add_rule("card_operations", RateLimitRule(
        requests=50,  # Moderate limit for card operations
        window_seconds=60,
        algorithm=RateLimitAlgorithm.TOKEN_BUCKET,
        scope=RateLimitScope.USER,
        paths={"/card/api/"},
        burst_requests=8,  # Card generation burst
        block_duration_seconds=120,  # Longer block for resource-intensive ops
        warning_threshold=0.75
    ))

    # Playback and real-time operations
    limiter.add_rule("realtime_operations", RateLimitRule(
        requests=100,  # Higher limit for real-time game operations
        window_seconds=60,
        algorithm=RateLimitAlgorithm.TOKEN_BUCKET,
        scope=RateLimitScope.USER,
        paths={"/playback/api/"},
        burst_requests=10,
        block_duration_seconds=30,  # Short block for real-time ops
        warning_threshold=0.9
    ))

    # Expensive operations (file generation, save/load)
    limiter.add_rule("expensive", RateLimitRule(
        requests=10,  # Very conservative for expensive operations
        window_seconds=300,  # 5 minutes
        algorithm=RateLimitAlgorithm.SLIDING_WINDOW,
        scope=RateLimitScope.USER,
        paths={"/api/cards/generate", "/api/games/create", "/game_management/api/"},
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
