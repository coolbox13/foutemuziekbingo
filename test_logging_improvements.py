#!/usr/bin/env python3
"""
Test script to validate that console errors now appear in application logs.
This script tests various error scenarios that previously only appeared in console.
"""

import asyncio
import os
import sys
import logging
import tempfile
import subprocess
import time
from pathlib import Path
from datetime import datetime

# Add the app directory to the Python path
sys.path.insert(0, os.path.join(os.getcwd(), 'app'))

async def test_logging_improvements():
    """Test that console errors are now properly logged."""
    
    print("🧪 TESTING LOGGING IMPROVEMENTS")
    print("=" * 60)
    
    # Clear previous log file for clean testing
    log_file = Path("logs/music_bingo.log")
    if log_file.exists():
        # Keep a backup for comparison
        backup_file = f"logs/music_bingo_backup_{int(time.time())}.log"
        subprocess.run(['cp', str(log_file), backup_file])
        log_file.unlink()
    
    test_results = []
    
    # Test 1: Import and basic logging setup
    print("\n📋 Test 1: Basic logging configuration...")
    try:
        from app.fastapi_app import create_app
        
        # Create app to initialize logging
        app = create_app()
        
        # Check if log file was created
        if log_file.exists():
            with open(log_file, 'r') as f:
                log_content = f.read()
            
            if "Enhanced logging configured" in log_content:
                print("✅ Enhanced logging configuration loaded successfully")
                test_results.append(("Enhanced logging config", True))
            else:
                print("❌ Enhanced logging configuration not found in logs")
                test_results.append(("Enhanced logging config", False))
        else:
            print("❌ Log file was not created")
            test_results.append(("Log file creation", False))
            
    except Exception as e:
        print(f"❌ Failed to initialize logging: {e}")
        test_results.append(("Basic logging setup", False))
    
    # Test 2: Socket.IO error handling
    print("\n📋 Test 2: Socket.IO error logging...")
    try:
        import socketio
        from app.socket_handler import sio, logger
        
        # Test that logger is properly configured
        logger.error("TEST: Socket.IO error logging test")
        
        # Check if error appears in log
        time.sleep(0.1)  # Give logger time to write
        with open(log_file, 'r') as f:
            log_content = f.read()
        
        if "TEST: Socket.IO error logging test" in log_content:
            print("✅ Socket.IO error logging working")
            test_results.append(("Socket.IO error logging", True))
        else:
            print("❌ Socket.IO error not found in logs")
            test_results.append(("Socket.IO error logging", False))
            
    except Exception as e:
        print(f"❌ Socket.IO logging test failed: {e}")
        test_results.append(("Socket.IO error logging", False))
    
    # Test 3: Third-party library logging
    print("\n📋 Test 3: Third-party library logging...")
    try:
        # Test uvicorn logger
        uvicorn_logger = logging.getLogger("uvicorn.error")
        uvicorn_logger.error("TEST: Uvicorn error logging test")
        
        # Test socketio logger
        socketio_logger = logging.getLogger("socketio")
        socketio_logger.warning("TEST: SocketIO warning logging test")
        
        time.sleep(0.1)
        with open(log_file, 'r') as f:
            log_content = f.read()
        
        uvicorn_logged = "TEST: Uvicorn error logging test" in log_content
        socketio_logged = "TEST: SocketIO warning logging test" in log_content
        
        if uvicorn_logged and socketio_logged:
            print("✅ Third-party library logging working")
            test_results.append(("Third-party logging", True))
        else:
            print(f"❌ Third-party logging issues - Uvicorn: {uvicorn_logged}, SocketIO: {socketio_logged}")
            test_results.append(("Third-party logging", False))
            
    except Exception as e:
        print(f"❌ Third-party logging test failed: {e}")
        test_results.append(("Third-party logging", False))
    
    # Test 4: Root logger capture
    print("\n📋 Test 4: Root logger capture...")
    try:
        root_logger = logging.getLogger()
        root_logger.error("TEST: Root logger capture test")
        
        time.sleep(0.1)
        with open(log_file, 'r') as f:
            log_content = f.read()
        
        if "TEST: Root logger capture test" in log_content:
            print("✅ Root logger capture working")
            test_results.append(("Root logger capture", True))
        else:
            print("❌ Root logger capture not working")
            test_results.append(("Root logger capture", False))
            
    except Exception as e:
        print(f"❌ Root logger test failed: {e}")
        test_results.append(("Root logger capture", False))
    
    # Test 5: Verify no print statements remain in production code
    print("\n📋 Test 5: Checking for remaining print statements...")
    try:
        print_files = []
        
        # Check main application files for print statements
        app_files = ['app.py', 'app/fastapi_app.py', 'app/socket_handler.py']
        
        for file_path in app_files:
            if os.path.exists(file_path):
                with open(file_path, 'r') as f:
                    content = f.read()
                    lines = content.split('\n')
                    for i, line in enumerate(lines, 1):
                        # Skip comments and string literals
                        stripped = line.strip()
                        if stripped.startswith('#'):
                            continue
                        if 'print(' in line and not line.strip().startswith('#'):
                            # Check if it's in a string or comment
                            if '"""' not in line and "'''" not in line:
                                print_files.append(f"{file_path}:{i}: {line.strip()}")
        
        if not print_files:
            print("✅ No print statements found in main application files")
            test_results.append(("No print statements", True))
        else:
            print("❌ Print statements still found:")
            for item in print_files:
                print(f"  {item}")
            test_results.append(("No print statements", False))
            
    except Exception as e:
        print(f"❌ Print statement check failed: {e}")
        test_results.append(("No print statements", False))
    
    # Test Summary
    print("\n" + "=" * 60)
    print("LOGGING IMPROVEMENT TEST SUMMARY")
    print("=" * 60)
    
    passed_tests = sum(1 for _, passed in test_results if passed)
    total_tests = len(test_results)
    
    for test_name, passed in test_results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status} {test_name}")
    
    print(f"\nResults: {passed_tests}/{total_tests} tests passed")
    print(f"Success Rate: {(passed_tests/total_tests)*100:.1f}%")
    
    if passed_tests == total_tests:
        print("\n🎉 All logging improvement tests passed!")
        print("✅ Console errors will now appear in application logs")
        print("✅ Enhanced error tracking and debugging enabled")
        return True
    else:
        print(f"\n⚠️ {total_tests - passed_tests} test(s) failed - review issues above")
        return False

if __name__ == "__main__":
    success = asyncio.run(test_logging_improvements())
    sys.exit(0 if success else 1)
