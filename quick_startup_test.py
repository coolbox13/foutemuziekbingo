#!/usr/bin/env python3
"""
Quick startup test to verify uvicorn logging integration works.
"""

import asyncio
import logging
import sys
import os
from pathlib import Path

# Add the app directory to Python path
sys.path.insert(0, os.path.join(os.getcwd(), 'app'))

async def test_startup_logging():
    """Test that startup logging works correctly."""
    
    print("🚀 Testing application startup logging...")
    
    try:
        # Clear log for clean test
        log_file = Path("logs/music_bingo.log")
        if log_file.exists():
            log_file.unlink()
        
        # Import and create app (this triggers all logging setup)
        from app.fastapi_app import create_app
        app = create_app()
        
        # Give some time for logging to complete
        await asyncio.sleep(0.5)
        
        # Check if log file exists and has expected content
        if log_file.exists():
            with open(log_file, 'r') as f:
                log_content = f.read()
            
            # Look for key indicators
            indicators = [
                "Enhanced logging configured",
                "Third-party library logging",
                "Registered routes"
            ]
            
            found_indicators = sum(1 for indicator in indicators if indicator in log_content)
            
            print(f"✅ Log file created with {len(log_content.split('\n'))} lines")
            print(f"✅ Found {found_indicators}/{len(indicators)} expected log indicators")
            
            if found_indicators >= 2:  # At least 2 out of 3 should be present
                print("✅ Startup logging working correctly")
                return True
            else:
                print("❌ Missing expected log content")
                return False
        else:
            print("❌ Log file was not created during startup")
            return False
            
    except Exception as e:
        print(f"❌ Startup test failed: {e}")
        return False

if __name__ == "__main__":
    success = asyncio.run(test_startup_logging())
    if success:
        print("\n🎉 Application startup logging test passed!")
    else:
        print("\n❌ Application startup logging test failed!")
    sys.exit(0 if success else 1)
