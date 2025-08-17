"""
Test utilities for loading environment and configuration.
"""
import os
import sys
from pathlib import Path


def load_test_environment():
    """Load environment variables for testing."""
    # Add project root to Python path
    project_root = Path(__file__).parent.parent
    sys.path.insert(0, str(project_root))
    
    # Load environment variables from .env file
    env_file = project_root / ".env"
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key] = value
    
    # Set test-specific environment variables if needed
    os.environ.setdefault('ENVIRONMENT', 'test')
    
    return True

def ensure_environment():
    """Ensure all required environment variables are set."""
    required_vars = [
        'SECRET_KEY',
        'JWT_SECRET', 
        'JWT_REFRESH_SECRET',
        'SUPABASE_URL',
        'SUPABASE_SERVICE_KEY',
        'DRAGONFLY_URL'
    ]
    
    missing = []
    for var in required_vars:
        if not os.environ.get(var):
            missing.append(var)
    
    if missing:
        print(f"❌ Missing required environment variables: {', '.join(missing)}")
        print("Please ensure your .env file contains all required variables.")
        return False
    
    return True