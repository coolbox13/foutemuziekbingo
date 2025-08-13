"""
Production-grade CORS configuration with environment-specific security policies.
Implements secure CORS settings based on environment and provides validation.
"""

import logging
import re
from typing import List, Dict, Any, Optional
from urllib.parse import urlparse

from app.config import get_config

logger = logging.getLogger("music_bingo")


class CORSSecurityError(Exception):
    """Raised when CORS configuration has security issues."""
    pass


class CORSConfig:
    """
    Advanced CORS configuration with security validation and environment-specific policies.

    Provides secure defaults and validates origin patterns to prevent common
    security misconfigurations in production environments.
    """

    def __init__(self):
        """Initialize CORS configuration with security validation."""
        self.config = get_config()
        self._allowed_origins = self._parse_and_validate_origins()
        self._security_headers = self._get_security_headers()

    def _parse_and_validate_origins(self) -> List[str]:
        """Parse and validate allowed origins with security checks."""
        origins_str = self.config.allowed_origins

        if not origins_str:
            if self.config.app_env == "production":
                raise CORSSecurityError("No CORS origins configured for production")
            return ["http://localhost:1313"]  # Development fallback

        # Parse comma-separated origins
        raw_origins = [origin.strip() for origin in origins_str.split(",") if origin.strip()]
        validated_origins = []

        for origin in raw_origins:
            validated = self._validate_origin(origin)
            if validated:
                validated_origins.append(validated)

        if not validated_origins and self.config.app_env == "production":
            raise CORSSecurityError("No valid CORS origins after validation")

        # Additional security checks for production
        if self.config.app_env == "production":
            self._validate_production_origins(validated_origins)

        logger.info(f"CORS origins configured: {len(validated_origins)} origins")
        if self.config.app_env != "production":
            logger.debug(f"CORS origins: {validated_origins}")

        return validated_origins

    def _validate_origin(self, origin: str) -> Optional[str]:
        """
        Validate a single origin for security compliance.

        Args:
            origin: Origin URL to validate

        Returns:
            Validated origin or None if invalid
        """
        # Handle wildcard (only allowed in development)
        if origin == "*":
            if self.config.app_env == "production":
                logger.error("Wildcard CORS origin '*' not allowed in production")
                raise CORSSecurityError("Wildcard origins not allowed in production")
            return origin

        # Parse URL
        try:
            parsed = urlparse(origin)
        except Exception as e:
            logger.warning(f"Invalid CORS origin URL '{origin}': {e}")
            return None

        # Validate scheme
        if parsed.scheme not in ('http', 'https'):
            logger.warning(f"Invalid CORS origin scheme '{parsed.scheme}' in '{origin}'")
            return None

        # Validate host
        if not parsed.netloc:
            logger.warning(f"No host in CORS origin '{origin}'")
            return None

        # Security checks
        if self.config.app_env == "production":
            # Require HTTPS in production (except for localhost in development/staging)
            if parsed.scheme != 'https' and not self._is_localhost(parsed.netloc):
                logger.warning(f"Non-HTTPS CORS origin not allowed in production: '{origin}'")
                return None

            # Check for suspicious patterns
            if self._is_suspicious_origin(origin):
                logger.error(f"Suspicious CORS origin blocked: '{origin}'")
                return None

        # Normalize the origin
        normalized = f"{parsed.scheme}://{parsed.netloc}"
        if parsed.port and not self._is_default_port(parsed.scheme, parsed.port):
            normalized = f"{parsed.scheme}://{parsed.netloc}"  # netloc includes port

        return normalized

    def _validate_production_origins(self, origins: List[str]) -> None:
        """Additional validation for production origins."""
        localhost_patterns = ['localhost', '127.0.0.1', '0.0.0.0', '::1']

        for origin in origins:
            parsed = urlparse(origin)
            host = parsed.hostname

            # Check for localhost in production
            if any(pattern in host.lower() if host else '' for pattern in localhost_patterns):
                logger.error(f"Localhost CORS origin '{origin}' not allowed in production")
                raise CORSSecurityError(f"Localhost origin not allowed in production: {origin}")

            # Check for private/internal networks
            if self._is_private_network(host):
                logger.warning(f"Private network CORS origin in production: '{origin}'")

            # Validate domain format
            if not self._is_valid_domain(host):
                logger.error(f"Invalid domain in CORS origin: '{origin}'")
                raise CORSSecurityError(f"Invalid domain format: {origin}")

    def _is_localhost(self, netloc: str) -> bool:
        """Check if netloc represents localhost."""
        localhost_patterns = ['localhost', '127.0.0.1', '0.0.0.0', '::1']
        host = netloc.split(':')[0].lower()  # Remove port
        return any(pattern in host for pattern in localhost_patterns)

    def _is_private_network(self, host: str) -> bool:
        """Check if host is in a private network range."""
        if not host:
            return False

        # Simple check for RFC 1918 private networks
        private_patterns = [
            r'^10\.',
            r'^192\.168\.',
            r'^172\.(1[6-9]|2[0-9]|3[01])\.'
        ]

        return any(re.match(pattern, host) for pattern in private_patterns)

    def _is_suspicious_origin(self, origin: str) -> bool:
        """Check for suspicious origin patterns."""
        suspicious_patterns = [
            'data:', 'file:', 'javascript:', 'vbscript:',  # Dangerous schemes
            'xss', 'script', 'iframe',  # XSS-related
            'eval(', 'alert(', '<script',  # Code injection patterns
        ]

        origin_lower = origin.lower()
        return any(pattern in origin_lower for pattern in suspicious_patterns)

    def _is_valid_domain(self, domain: str) -> bool:
        """Validate domain name format."""
        if not domain:
            return False

        # Basic domain validation (not exhaustive, but catches common issues)
        domain_pattern = r'^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*$'
        return re.match(domain_pattern, domain) is not None

    def _is_default_port(self, scheme: str, port: int) -> bool:
        """Check if port is default for the scheme."""
        default_ports = {
            'http': 80,
            'https': 443
        }
        return default_ports.get(scheme) == port

    def _get_security_headers(self) -> List[str]:
        """Get security-focused allowed headers."""
        # Base headers required for modern web applications
        base_headers = [
            "Accept",
            "Accept-Language",
            "Content-Language",
            "Content-Type",
        ]

        # Authentication headers
        auth_headers = [
            "Authorization",
            "X-CSRF-Token",
            "X-CSRFToken",
        ]

        # Additional headers for API functionality
        api_headers = [
            "X-Requested-With",
            "Cache-Control",
        ]

        # Production vs development headers
        if self.config.app_env == "production":
            # Minimal headers for production security
            return base_headers + auth_headers + ["X-Requested-With"]
        else:
            # More permissive for development
            return base_headers + auth_headers + api_headers + [
                "User-Agent",
                "X-Debug",
                "X-Client-Version"
            ]

    def get_cors_config(self) -> Dict[str, Any]:
        """
        Get FastAPI CORS middleware configuration.

        Returns:
            Dict with CORS middleware parameters
        """
        # Exposed headers for rate limiting and monitoring
        expose_headers = [
            "X-RateLimit-Limit",
            "X-RateLimit-Remaining",
            "X-RateLimit-Reset",
            "X-RateLimit-Warning",
            "Retry-After",
        ]

        # Production security: more restrictive settings
        if self.config.app_env == "production":
            allowed_methods = ["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"]
        else:
            # Development: allow additional methods for debugging
            allowed_methods = ["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"]

        return {
            "allow_origins": self._allowed_origins,
            "allow_credentials": True,  # Required for session-based auth
            "allow_methods": allowed_methods,
            "allow_headers": self._security_headers,
            "expose_headers": expose_headers,
            "max_age": 86400 if self.config.app_env == "production" else 3600,  # Cache preflight
        }

    def validate_origin_request(self, origin: str) -> bool:
        """
        Runtime validation of origin from incoming request.

        Args:
            origin: Origin header from request

        Returns:
            True if origin is allowed
        """
        if not origin:
            return True  # Allow requests without Origin header (same-origin)

        # Check against configured origins
        if origin in self._allowed_origins:
            return True

        # Check for wildcard (only in development)
        if "*" in self._allowed_origins and self.config.app_env != "production":
            return True

        # Additional runtime checks
        if self.config.app_env == "production":
            # In production, be strict
            logger.warning(f"Unauthorized CORS origin blocked: {origin}")
            return False
        else:
            # In development, allow localhost variations
            if self._is_localhost(origin):
                logger.debug(f"Allowing localhost origin in development: {origin}")
                return True

            logger.warning(f"Unknown origin in development: {origin}")
            return False

    def get_security_report(self) -> Dict[str, Any]:
        """
        Get CORS security configuration report.

        Returns:
            Security analysis report
        """
        issues = []
        recommendations = []

        # Analyze current configuration
        if len(self._allowed_origins) > 10:
            issues.append(f"Large number of allowed origins: {len(self._allowed_origins)}")
            recommendations.append("Consider using a more restrictive origin list")

        if "*" in self._allowed_origins:
            if self.config.app_env == "production":
                issues.append("Wildcard origin in production")
            else:
                recommendations.append("Remove wildcard origin before production deployment")

        # Check for HTTP origins in production
        if self.config.app_env == "production":
            http_origins = [o for o in self._allowed_origins if o.startswith('http://')]
            if http_origins:
                issues.append(f"HTTP origins in production: {len(http_origins)}")
                recommendations.append("Use HTTPS origins in production")

        return {
            "environment": self.config.app_env,
            "total_origins": len(self._allowed_origins),
            "origins_configured": len(self._allowed_origins) > 0,
            "wildcard_used": "*" in self._allowed_origins,
            "https_only": all(o.startswith('https://') or o == "*" for o in self._allowed_origins),
            "security_headers_count": len(self._security_headers),
            "issues": issues,
            "recommendations": recommendations,
            "configuration_valid": len(issues) == 0
        }


def create_cors_config() -> CORSConfig:
    """Create and validate CORS configuration."""
    try:
        return CORSConfig()
    except CORSSecurityError as e:
        logger.error(f"CORS configuration security error: {e}")
        raise
    except Exception as e:
        logger.error(f"Failed to create CORS configuration: {e}")
        raise CORSSecurityError(f"CORS configuration failed: {e}")


# Global CORS configuration instance
_cors_config: Optional[CORSConfig] = None


def get_cors_config() -> CORSConfig:
    """Get the global CORS configuration instance."""
    global _cors_config
    if _cors_config is None:
        _cors_config = create_cors_config()
    return _cors_config


def reload_cors_config() -> CORSConfig:
    """Reload CORS configuration (useful for testing)."""
    global _cors_config
    _cors_config = None
    return get_cors_config()


# Utility functions for CORS validation
def validate_cors_request(origin: str) -> bool:
    """Validate CORS request origin."""
    try:
        cors_config = get_cors_config()
        return cors_config.validate_origin_request(origin)
    except Exception as e:
        logger.error(f"CORS validation error: {e}")
        return False  # Fail closed


def get_cors_security_report() -> Dict[str, Any]:
    """Get comprehensive CORS security report."""
    try:
        cors_config = get_cors_config()
        return cors_config.get_security_report()
    except Exception as e:
        logger.error(f"Failed to generate CORS security report: {e}")
        return {
            "environment": "unknown",
            "error": str(e),
            "configuration_valid": False
        }
