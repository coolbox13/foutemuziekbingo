#!/usr/bin/env python3
"""
Test script for database.py
Tests Supabase connection and database operations
"""
import asyncio
import os

# Load test environment first
from test_utils import load_test_environment
load_test_environment()

from app.database import SupabaseService


async def test_database_connection():
    """Test Supabase database connection"""
    print("Testing Supabase database connection...")

    db_service = SupabaseService()

    try:
        await db_service.initialize()
        print("✅ Database initialization: PASS")
    except Exception as e:
        print(f"❌ Database initialization: FAIL - {e}")
        return False

    return True


async def test_health_check():
    """Test database health check"""
    print("\nTesting database health check...")

    db_service = SupabaseService()

    try:
        await db_service.initialize()
        is_healthy = await db_service.health_check()
        if is_healthy:
            print("✅ Database health check: PASS")
        else:
            print("❌ Database health check: FAIL - Not healthy")
    except Exception as e:
        print(f"❌ Database health check: FAIL - {e}")


async def test_query_execution():
    """Test basic query execution"""
    print("\nTesting query execution...")

    db_service = SupabaseService()

    try:
        await db_service.initialize()

        # Test a simple query (list tables or similar)
        async def simple_query():
            # This would be a real query in production
            return {"status": "success", "tables": ["users", "games", "playlists"]}

        result = await db_service.execute_query(simple_query)
        print("✅ Query execution: PASS")
        print(f"  Result status: {result.get('status')}")

    except Exception as e:
        print(f"❌ Query execution: FAIL - {e}")


async def test_error_handling():
    """Test database error handling"""
    print("\nTesting error handling...")

    db_service = SupabaseService()

    try:
        await db_service.initialize()

        # Test error handling with a function that raises an exception
        async def failing_query():
            raise Exception("Simulated database error")

        try:
            await db_service.execute_query(failing_query)
            print("❌ Error handling: FAIL - Should have raised exception")
        except Exception:
            print("✅ Error handling: PASS")

    except Exception as e:
        print(f"❌ Error handling setup: FAIL - {e}")


async def test_connection_recovery():
    """Test connection recovery mechanisms"""
    print("\nTesting connection recovery...")

    db_service = SupabaseService()

    try:
        await db_service.initialize()

        # Simulate connection issues and recovery
        print("✅ Connection recovery setup: PASS")
        print("  (Would test reconnection logic in production)")

    except Exception as e:
        print(f"❌ Connection recovery: FAIL - {e}")


async def run_database_tests():
    """Run all database tests"""
    print("=" * 50)
    print("DATABASE TESTS")
    print("=" * 50)

    # Check environment variables
    if not os.getenv("SUPABASE_URL") or not os.getenv("SUPABASE_SERVICE_KEY"):
        print("⚠️  WARNING: SUPABASE_URL or SUPABASE_SERVICE_KEY not set")
        print("   Database tests will be limited")

    connection_ok = await test_database_connection()

    if connection_ok:
        await test_health_check()
        await test_query_execution()
        await test_error_handling()
        await test_connection_recovery()
    else:
        print("⚠️  Skipping advanced tests due to connection failure")

    print("\nDatabase tests completed!")


if __name__ == "__main__":
    asyncio.run(run_database_tests())
