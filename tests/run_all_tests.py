#!/usr/bin/env python3
"""
Master test runner for all Foute Muziek Bingo tests
Automatically discovers and runs all test modules in the tests directory
"""
import asyncio
import sys
import os
import subprocess
import glob
from pathlib import Path

# Load test environment first
from test_utils import load_test_environment, ensure_environment
load_test_environment()

# Add parent directory to path so we can import app modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def discover_test_modules():
    """Automatically discover all test modules in the tests directory."""
    test_dir = Path(__file__).parent
    test_files = glob.glob(str(test_dir / "test_*.py"))

    # Exclude run_all_tests.py and test_utils.py
    exclude_files = {"run_all_tests.py", "test_utils.py"}

    modules = []
    for test_file in sorted(test_files):
        file_name = Path(test_file).name
        if file_name not in exclude_files:
            module_name = file_name[:-3]  # Remove .py extension
            # Create friendly display name
            display_name = module_name.replace('test_', '').replace('_', ' ').title()
            modules.append((module_name, display_name))

    return modules


async def run_individual_test(test_module, test_name):
    """Run an individual test module"""
    print(f"\n{'='*60}")
    print(f"RUNNING: {test_name}")
    print(f"{'='*60}")

    try:
        # Import and run the test module
        if test_module == "test_models":
            from tests.test_models import run_model_tests
            await run_model_tests()

        elif test_module == "test_auth_service":
            from tests.test_auth_service import run_auth_service_tests
            await run_auth_service_tests()

        elif test_module == "test_database":
            from tests.test_database import run_database_tests
            await run_database_tests()

        elif test_module == "test_game_service":
            from tests.test_game_service import run_game_service_tests
            await run_game_service_tests()

        elif test_module == "test_auth_integration":
            # Run pytest-style test if available
            result = subprocess.run([
                sys.executable, "-m", "pytest", f"tests/{test_module}.py", "-v"
            ], capture_output=True, text=True, cwd=os.path.dirname(os.path.dirname(__file__)))

            if result.returncode == 0:
                print("✅ Auth Integration tests passed")
            else:
                print(f"❌ Auth Integration tests failed: {result.stderr}")
                return False

        elif test_module == "test_cache_integration":
            # Run the comprehensive cache tests
            result = subprocess.run([
                sys.executable, f"tests/{test_module}.py"
            ], capture_output=True, text=True, cwd=os.path.dirname(os.path.dirname(__file__)))

            if result.returncode == 0:
                print("✅ Cache Integration tests passed")
            else:
                print("❌ Cache Integration tests failed")
                if result.stdout:
                    print("STDOUT:", result.stdout[-1000:])  # Last 1000 chars
                if result.stderr:
                    print("STDERR:", result.stderr[-1000:])
                return False

        elif test_module == "test_comprehensive_rate_limiting":
            # Run the comprehensive rate limiting tests
            result = subprocess.run([
                sys.executable, f"tests/{test_module}.py"
            ], capture_output=True, text=True, cwd=os.path.dirname(os.path.dirname(__file__)))

            if result.returncode == 0:
                print("✅ Comprehensive Rate Limiting tests passed")
            else:
                print("❌ Comprehensive Rate Limiting tests failed")
                return False

        elif test_module == "test_redis_sessions":
            # Run the Redis session tests
            result = subprocess.run([
                sys.executable, f"tests/{test_module}.py"
            ], capture_output=True, text=True, cwd=os.path.dirname(os.path.dirname(__file__)))

            if result.returncode == 0:
                print("✅ Redis Sessions tests passed")
            else:
                print("❌ Redis Sessions tests failed")
                return False

        elif test_module == "test_websocket_integration":
            # Run the WebSocket integration tests
            result = subprocess.run([
                sys.executable, f"tests/{test_module}.py"
            ], capture_output=True, text=True, cwd=os.path.dirname(os.path.dirname(__file__)))

            if result.returncode == 0:
                print("✅ WebSocket Integration tests passed")
            else:
                print("❌ WebSocket Integration tests failed")
                return False

        elif test_module == "test_performance_suite":
            # Run the performance suite
            result = subprocess.run([
                sys.executable, f"tests/{test_module}.py"
            ], capture_output=True, text=True, cwd=os.path.dirname(os.path.dirname(__file__)))

            if result.returncode == 0:
                print("✅ Performance Suite tests passed")
            else:
                print("❌ Performance Suite tests failed")
                return False

        elif test_module == "test_csrf_protection":
            # Run CSRF protection tests
            result = subprocess.run([
                sys.executable, f"tests/{test_module}.py"
            ], capture_output=True, text=True, cwd=os.path.dirname(os.path.dirname(__file__)))

            if result.returncode == 0:
                print("✅ CSRF Protection tests passed")
            else:
                print("❌ CSRF Protection tests failed")
                return False

        elif test_module == "test_input_validation":
            # Run input validation tests
            result = subprocess.run([
                sys.executable, f"tests/{test_module}.py"
            ], capture_output=True, text=True, cwd=os.path.dirname(os.path.dirname(__file__)))

            if result.returncode == 0:
                print("✅ Input Validation tests passed")
            else:
                print("❌ Input Validation tests failed")
                return False

        elif test_module == "test_state_management":
            # Run state management tests
            result = subprocess.run([
                sys.executable, f"tests/{test_module}.py"
            ], capture_output=True, text=True, cwd=os.path.dirname(os.path.dirname(__file__)))

            if result.returncode == 0:
                print("✅ State Management tests passed")
            else:
                print("❌ State Management tests failed")
                return False

        else:
            # Generic test runner for other modules
            try:
                # Try to run as executable module
                result = subprocess.run([
                    sys.executable, f"tests/{test_module}.py"
                ], capture_output=True, text=True, cwd=os.path.dirname(os.path.dirname(__file__)))

                if result.returncode == 0:
                    print(f"✅ {test_name} tests passed")
                else:
                    print(f"❌ {test_name} tests failed")
                    if result.stderr:
                        print("Error:", result.stderr[:500])
                    return False
            except Exception as e:
                print(f"❌ {test_name} failed to execute: {e}")
                return False

        print(f"✅ {test_name} completed successfully")
        return True

    except Exception as e:
        print(f"❌ {test_name} failed with error: {e}")
        return False


async def check_environment():
    """Check if environment is properly configured"""
    print("Checking environment configuration...")
    return ensure_environment()


def check_dependencies():
    """Check if required packages are installed"""
    print("\nChecking Python dependencies...")

    required_packages = [
        "fastapi", "pydantic", "supabase", "redis",
        "pytest", "asyncio", "httpx"
    ]

    missing_packages = []
    for package in required_packages:
        try:
            __import__(package)
        except ImportError:
            missing_packages.append(package)

    if missing_packages:
        print(f"⚠️  Missing packages: {', '.join(missing_packages)}")
        print("   Run: pip install -r requirements.txt")
        return False
    else:
        print("✅ All required packages are installed")
        return True


def run_linting():
    """Run code linting checks"""
    print(f"\n{'='*60}")
    print("PYTHON LINTING CHECKS")
    print(f"{'='*60}")

    # Run flake8 on all Python files
    print("Running flake8 linting...")
    try:
        result = subprocess.run([
            "flake8", "app/", "tests/", "--max-line-length=100", "--exclude=__pycache__"
        ], capture_output=True, text=True)

        if result.returncode == 0:
            print("✅ Flake8 linting: PASS")
        else:
            print("❌ Flake8 linting: FAIL")
            print(result.stdout[:2000])  # Show first 2000 chars of output
            return False
    except FileNotFoundError:
        print("⚠️  flake8 not found - skipping lint check")

    # Run basic syntax checks
    print("\nRunning basic syntax checks...")
    py_files = glob.glob("app/*.py") + glob.glob("tests/*.py")
    syntax_errors = 0

    for py_file in py_files:
        try:
            with open(py_file, 'r') as f:
                compile(f.read(), py_file, 'exec')
        except SyntaxError as e:
            print(f"❌ Syntax error in {py_file}: {e}")
            syntax_errors += 1

    if syntax_errors == 0:
        print(f"✅ Syntax check: PASS ({len(py_files)} files checked)")
        return True
    else:
        print(f"❌ Syntax check: FAIL ({syntax_errors} errors found)")
        return False


async def main():
    """Run all test suites"""
    print("🧪 FOUTE MUZIEK BINGO - COMPREHENSIVE TEST SUITE")
    print("=" * 80)

    # Environment checks
    env_ok = await check_environment()
    deps_ok = check_dependencies()

    if not env_ok:
        print("❌ Environment check failed - some tests may not work properly")

    if not deps_ok:
        print("❌ Cannot run tests - missing dependencies")
        return False

    # Run linting first
    lint_ok = run_linting()
    if not lint_ok:
        print("❌ Linting failed - please fix code quality issues")

    # Discover and run all test modules
    test_modules = discover_test_modules()

    print(f"\n🔍 Discovered {len(test_modules)} test modules:")
    for module, name in test_modules:
        print(f"  • {module} → {name}")

    results = {}

    # Run each test module
    for module, name in test_modules:
        success = await run_individual_test(module, name)
        results[name] = success

    # Print summary
    print(f"\n{'='*80}")
    print("COMPREHENSIVE TEST SUMMARY")
    print(f"{'='*80}")

    total_tests = len(results)
    passed_tests = sum(1 for result in results.values() if result)
    failed_tests = total_tests - passed_tests

    for test_name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status} {test_name}")

    print("\nOverall Results:")
    print(f"  Total Test Modules: {total_tests}")
    print(f"  Passed: {passed_tests}")
    print(f"  Failed: {failed_tests}")
    print(f"  Success Rate: {(passed_tests/total_tests)*100:.1f}%")

    if failed_tests == 0:
        print("\n🎉 All test modules passed!")
        return True
    else:
        print(f"\n⚠️  {failed_tests} test module(s) failed - review output above")
        return False


if __name__ == "__main__":
    # Run the complete test suite
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
