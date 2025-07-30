#!/usr/bin/env python3
"""
Master test runner for all Foute Muziek Bingo tests
Runs all individual test modules and provides summary
"""
import asyncio
import sys
import os
import subprocess

# Add parent directory to path so we can import app modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def run_individual_test(test_module, test_name):
    """Run an individual test module"""
    print(f"\n{'='*60}")
    print(f"RUNNING: {test_name}")
    print(f"{'='*60}")
    
    try:
        # Import and run the test module
        if test_module == "test_models":
            from tests.test_models import run_tests
            run_tests()
        elif test_module == "test_auth_service":
            from tests.test_auth_service import run_auth_tests
            await run_auth_tests()
        elif test_module == "test_database":
            from tests.test_database import run_database_tests
            await run_database_tests()
        elif test_module == "test_game_service":
            from tests.test_game_service import run_game_service_tests
            await run_game_service_tests()
        
        print(f"✅ {test_name} completed successfully")
        return True
        
    except Exception as e:
        print(f"❌ {test_name} failed with error: {e}")
        return False


async def check_environment():
    """Check if environment is properly configured"""
    print("Checking environment configuration...")
    
    required_env_vars = [
        "SUPABASE_URL",
        "SUPABASE_SERVICE_KEY", 
        "SPOTIFY_CLIENT_ID",
        "SPOTIFY_CLIENT_SECRET",
        "JWT_SECRET"
    ]
    
    missing_vars = []
    for var in required_env_vars:
        if not os.getenv(var):
            missing_vars.append(var)
    
    if missing_vars:
        print(f"⚠️  Missing environment variables: {', '.join(missing_vars)}")
        print("   Some tests may be limited or fail")
        return False
    else:
        print("✅ All required environment variables are set")
        return True


def check_dependencies():
    """Check if required packages are installed"""
    print("\nChecking Python dependencies...")
    
    required_packages = [
        "fastapi",
        "uvicorn", 
        "supabase",
        "pydantic",
        "spotipy",
        "jwt"  # pyjwt package imports as 'jwt'
    ]
    
    missing_packages = []
    for package in required_packages:
        try:
            __import__(package)
        except ImportError:
            missing_packages.append(package)
    
    if missing_packages:
        print(f"❌ Missing packages: {', '.join(missing_packages)}")
        print("   Install with: pip install " + " ".join(missing_packages))
        return False
    else:
        print("✅ All required packages are installed")
        return True


async def run_all_tests():
    """Run all test suites"""
    print("🧪 FOUTE MUZIEK BINGO - COMPREHENSIVE TEST SUITE")
    print("="*80)
    
    # Environment checks
    env_ok = await check_environment()
    deps_ok = check_dependencies()
    
    if not deps_ok:
        print("❌ Cannot run tests - missing dependencies")
        return False
    
    # Test modules to run
    test_modules = [
        ("test_models", "Pydantic Models & Validation"),
        ("test_auth_service", "Authentication Service"),
        ("test_database", "Database Operations"),
        ("test_game_service", "Game Service Logic")
    ]
    
    results = {}
    
    # Run each test module
    for module, name in test_modules:
        success = await run_individual_test(module, name)
        results[name] = success
    
    # Print summary
    print(f"\n{'='*80}")
    print("TEST SUMMARY")
    print(f"{'='*80}")
    
    total_tests = len(results)
    passed_tests = sum(1 for result in results.values() if result)
    failed_tests = total_tests - passed_tests
    
    for test_name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status} {test_name}")
    
    print(f"\nOverall Results:")
    print(f"  Total Tests: {total_tests}")
    print(f"  Passed: {passed_tests}")
    print(f"  Failed: {failed_tests}")
    print(f"  Success Rate: {(passed_tests/total_tests)*100:.1f}%")
    
    if failed_tests == 0:
        print("\n🎉 All tests passed!")
        return True
    else:
        print(f"\n⚠️  {failed_tests} test(s) failed - review output above")
        return False


def run_linting_checks():
    """Run Python linting checks"""
    print(f"\n{'='*60}")
    print("PYTHON LINTING CHECKS")
    print(f"{'='*60}")
    
    # Check if flake8 is available
    try:
        result = subprocess.run(["flake8", "--version"], capture_output=True, text=True)
        if result.returncode == 0:
            print("Running flake8 linting...")
            result = subprocess.run(["flake8", "app/", "tests/"], capture_output=True, text=True)
            if result.returncode == 0:
                print("✅ Flake8 linting: PASS")
            else:
                print("❌ Flake8 linting: FAIL")
                print(result.stdout)
        else:
            print("⚠️  flake8 not available - install with: pip install flake8")
    except FileNotFoundError:
        print("⚠️  flake8 not installed - skipping linting checks")
    
    # Basic syntax check
    print("\nRunning basic syntax checks...")
    try:
        import py_compile
        import glob
        
        python_files = glob.glob("app/**/*.py", recursive=True)
        syntax_errors = 0
        
        for file_path in python_files:
            try:
                py_compile.compile(file_path, doraise=True)
            except py_compile.PyCompileError as e:
                print(f"❌ Syntax error in {file_path}: {e}")
                syntax_errors += 1
        
        if syntax_errors == 0:
            print(f"✅ Syntax check: PASS ({len(python_files)} files checked)")
        else:
            print(f"❌ Syntax check: FAIL ({syntax_errors} files with errors)")
            
    except Exception as e:
        print(f"❌ Syntax check failed: {e}")


if __name__ == "__main__":
    print("Starting comprehensive test suite...\n")
    
    # Run linting first
    run_linting_checks()
    
    # Run all tests
    success = asyncio.run(run_all_tests())
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)