"""
Production-grade configuration management with environment variable validation.
Replaces hardcoded fallback secrets and ensures secure production deployment.
"""

import os
import secrets
import logging
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from dotenv import load_dotenv

logger = logging.getLogger("music_bingo")


@dataclass
class AppConfig:
    """Application configuration with validation."""
    
    # Security Configuration
    secret_key: str
    jwt_secret: str
    jwt_refresh_secret: str
    
    # Database Configuration
    supabase_url: str
    supabase_service_key: str
    
    # Spotify Configuration
    spotify_client_id: str
    spotify_client_secret: str
    spotify_redirect_uri: str
    
    # Redis/Dragonfly Configuration
    redis_url: str
    redis_password: Optional[str]
    
    # Application Configuration
    app_env: str
    debug: bool
    allowed_origins: str
    session_lifetime_hours: int
    max_sessions_per_user: int
    
    # Token Maintenance Configuration
    spotify_token_maintenance_interval: int
    spotify_token_safety_window: int
    
    # Rate Limiting Configuration
    rate_limit_requests_per_minute: int
    rate_limit_burst_size: int
    
    
class ConfigurationError(Exception):
    """Raised when configuration validation fails."""
    pass


def load_environment_config() -> None:
    """Load .env file with proper precedence handling."""
    # Load .env from project root if it exists
    env_path = os.path.join(os.getcwd(), ".env")
    if os.path.exists(env_path):
        load_dotenv(dotenv_path=env_path, override=False)
        logger.info(f"Loaded environment configuration from {env_path}")
    else:
        logger.info("No .env file found, using system environment variables")


def validate_production_config() -> List[str]:
    """
    Validate that all required production environment variables are set.
    Returns list of missing/invalid variables.
    """
    missing_vars = []
    invalid_vars = []
    
    # Critical security variables (no fallbacks allowed in production)
    critical_vars = [
        "SECRET_KEY",
        "JWT_SECRET", 
        "JWT_REFRESH_SECRET",
        "SUPABASE_URL",
        "SUPABASE_SERVICE_KEY",
        "SPOTIFY_CLIENT_ID",
        "SPOTIFY_CLIENT_SECRET",
        "SPOTIFY_REDIRECT_URI"
    ]
    
    app_env = os.getenv("APP_ENV", "development").lower()
    
    for var in critical_vars:
        value = os.getenv(var)
        if not value:
            missing_vars.append(var)
        elif app_env == "production":
            # In production, check for insecure fallback values
            insecure_patterns = [
                "dev-", "test-", "fallback-", "change-in-production",
                "your_", "example_", "localhost", "127.0.0.1"
            ]
            if any(pattern in value.lower() for pattern in insecure_patterns):
                invalid_vars.append(f"{var} (appears to be a fallback/development value)")
    
    # Validate URL formats
    supabase_url = os.getenv("SUPABASE_URL", "")
    if supabase_url and not (supabase_url.startswith("https://") and ".supabase.co" in supabase_url):
        invalid_vars.append("SUPABASE_URL (invalid format)")
    
    spotify_redirect = os.getenv("SPOTIFY_REDIRECT_URI", "")
    if spotify_redirect and app_env == "production" and "localhost" in spotify_redirect:
        invalid_vars.append("SPOTIFY_REDIRECT_URI (localhost not allowed in production)")
    
    # Combine missing and invalid
    issues = missing_vars + invalid_vars
    
    if issues and app_env == "production":
        error_msg = f"Production configuration validation failed:\\n"
        error_msg += f"Missing variables: {missing_vars}\\n" if missing_vars else ""
        error_msg += f"Invalid variables: {invalid_vars}" if invalid_vars else ""
        raise ConfigurationError(error_msg)
    
    return issues


def generate_secure_fallbacks() -> Dict[str, str]:
    """
    Generate secure fallback values for development environment only.
    These should NEVER be used in production.
    """
    return {
        "SECRET_KEY": secrets.token_urlsafe(32),
        "JWT_SECRET": secrets.token_urlsafe(32),
        "JWT_REFRESH_SECRET": secrets.token_urlsafe(32),
    }


def get_app_config() -> AppConfig:
    """
    Create application configuration with validation.
    
    Returns:
        AppConfig with validated settings
        
    Raises:
        ConfigurationError: If production validation fails
    """
    # Load environment variables
    load_environment_config()
    
    # Validate production environment
    app_env = os.getenv("APP_ENV", "development").lower()
    validation_issues = validate_production_config()
    
    if validation_issues:
        if app_env == "production":
            # This should have already raised an exception, but double-check
            raise ConfigurationError("Production validation failed")
        else:
            logger.warning(f"Development environment validation issues: {validation_issues}")
    
    # Generate secure fallbacks for development only
    secure_fallbacks = generate_secure_fallbacks() if app_env != "production" else {}
    
    # Build configuration
    config = AppConfig(
        # Security Configuration - NO fallbacks in production
        secret_key=os.getenv("SECRET_KEY") or secure_fallbacks.get("SECRET_KEY", ""),
        jwt_secret=os.getenv("JWT_SECRET") or secure_fallbacks.get("JWT_SECRET", ""),
        jwt_refresh_secret=os.getenv("JWT_REFRESH_SECRET") or secure_fallbacks.get("JWT_REFRESH_SECRET", ""),
        
        # Database Configuration
        supabase_url=os.getenv("SUPABASE_URL", ""),
        supabase_service_key=os.getenv("SUPABASE_SERVICE_KEY", ""),
        
        # Spotify Configuration
        spotify_client_id=os.getenv("SPOTIFY_CLIENT_ID", ""),
        spotify_client_secret=os.getenv("SPOTIFY_CLIENT_SECRET", ""),
        spotify_redirect_uri=os.getenv("SPOTIFY_REDIRECT_URI", "http://localhost:1313/auth/callback"),
        
        # Redis/Dragonfly Configuration
        redis_url=os.getenv("REDIS_URL", "redis://localhost:6379"),
        redis_password=os.getenv("REDIS_PASSWORD"),
        
        # Application Configuration
        app_env=app_env,
        debug=os.getenv("DEBUG", "false").lower() in ("true", "1", "yes", "on") or app_env == "development",
        allowed_origins=os.getenv("ALLOWED_ORIGINS", "http://localhost:1313"),
        session_lifetime_hours=int(os.getenv("SESSION_LIFETIME_HOURS", "24")),
        max_sessions_per_user=int(os.getenv("MAX_SESSIONS_PER_USER", "5")),
        
        # Token Maintenance Configuration
        spotify_token_maintenance_interval=int(os.getenv("SPOTIFY_TOKEN_MAINTENANCE_INTERVAL", "60")),
        spotify_token_safety_window=int(os.getenv("SPOTIFY_TOKEN_SAFETY_WINDOW", "180")),
        
        # Rate Limiting Configuration
        rate_limit_requests_per_minute=int(os.getenv("RATE_LIMIT_REQUESTS_PER_MINUTE", "60")),
        rate_limit_burst_size=int(os.getenv("RATE_LIMIT_BURST_SIZE", "10")),
    )
    
    # Validate that critical values are set
    if not config.secret_key:
        raise ConfigurationError("SECRET_KEY is required")
    if not config.supabase_url and app_env != "test":
        logger.warning("SUPABASE_URL is not configured")
    
    # Log configuration (safely)
    logger.info(f"Application configuration loaded - Environment: {config.app_env}")
    logger.info(f"Redis URL: {config.redis_url}")
    logger.info(f"Session lifetime: {config.session_lifetime_hours} hours")
    logger.info(f"Rate limiting: {config.rate_limit_requests_per_minute} requests/minute")
    
    return config


# Global configuration instance
_app_config: Optional[AppConfig] = None


def get_config() -> AppConfig:
    """Get the global application configuration instance."""
    global _app_config
    if _app_config is None:
        _app_config = get_app_config()
    return _app_config


def reload_config() -> AppConfig:
    """Force reload of the configuration (useful for testing)."""
    global _app_config
    _app_config = None
    return get_config()


# Configuration health check
def validate_config_health() -> Dict[str, Any]:
    """
    Validate configuration health for monitoring.
    
    Returns:
        Dict with health status and issues
    """
    try:
        config = get_config()
        issues = []
        
        # Check critical connections
        if not config.supabase_url:
            issues.append("Database URL not configured")
        
        if not config.spotify_client_id:
            issues.append("Spotify client not configured")
        
        # Check security settings in production
        if config.app_env == "production":
            if "localhost" in config.allowed_origins:
                issues.append("Production CORS allows localhost")
            
            if config.session_lifetime_hours > 168:  # 1 week
                issues.append("Session lifetime too long for production")
        
        return {
            "healthy": len(issues) == 0,
            "environment": config.app_env,
            "issues": issues,
            "last_validated": os.getenv("CONFIG_VALIDATED_AT", "never")
        }
    
    except Exception as e:
        return {
            "healthy": False,
            "error": str(e),
            "issues": ["Configuration validation failed"]
        }
