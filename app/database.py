"""
Supabase Database Service for Foute Muziek Bingo FastAPI
Migrated from PWA project with modern Python patterns
"""
import os
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
from supabase import create_client, Client
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

logger = logging.getLogger("music_bingo")


class DatabaseError(Exception):
    """Custom database error class"""

    def __init__(self, message: str, original_error: Optional[Exception] = None):
        super().__init__(message)
        self.original_error = original_error


class NotFoundError(DatabaseError):
    """Resource not found error"""

    def __init__(self, message: str = "Resource not found"):
        super().__init__(message)


class ValidationError(DatabaseError):
    """Validation error"""

    def __init__(self, message: str = "Validation failed"):
        super().__init__(message)


class ConflictError(DatabaseError):
    """Resource conflict error"""

    def __init__(self, message: str = "Resource conflict"):
        super().__init__(message)


class SupabaseService:
    """
    Supabase database service with comprehensive error handling
    Adapted from PWA TypeScript implementation to Python
    """

    def __init__(self):
        self.client: Optional[Client] = None
        self.is_initialized = False
        self.connection_status = "disconnected"
        self.last_health_check: Optional[datetime] = None

    async def initialize(self) -> None:
        """Initialize Supabase connection with comprehensive error handling"""
        init_id = f"db-init-{int(datetime.now().timestamp())}"

        try:
            logger.info(
                "[DB-INIT-001] Starting database initialization",
                extra={"init_id": init_id, "timestamp": datetime.now().isoformat()},
            )

            supabase_url = os.getenv("SUPABASE_URL")
            supabase_service_key = os.getenv("SUPABASE_SERVICE_KEY")

            if not supabase_url or not supabase_service_key:
                message = "Supabase URL and Service Key must be provided"
                logger.error(
                    "[DB-INIT-ERROR-001] Missing required Supabase configuration",
                    extra={
                        "init_id": init_id,
                        "has_url": bool(supabase_url),
                        "has_service_key": bool(supabase_service_key),
                    },
                )
                raise DatabaseError(message)

            logger.info(
                "[DB-INIT-002] Creating Supabase client",
                extra={
                    "init_id": init_id,
                    "supabase_url": supabase_url[:30] + "...",
                    "service_key_length": len(supabase_service_key),
                },
            )

            # Initialize Supabase client with service key for server-side operations
            self.client = create_client(supabase_url, supabase_service_key)

            logger.info(
                f"[DB-INIT-003] Testing database connection", extra={"init_id": init_id}
            )

            # Test the connection with comprehensive health check
            health_check_result = await self.perform_health_check()

            if health_check_result["is_healthy"]:
                self.connection_status = "connected"
                self.is_initialized = True
                self.last_health_check = datetime.now()

                logger.info(
                    "[DB-INIT-004] Database connection established successfully",
                    extra={
                        "init_id": init_id,
                        "health_check": health_check_result,
                        "timestamp": datetime.now().isoformat(),
                    },
                )
            else:
                self.connection_status = "error"
                logger.warning(
                    "[DB-INIT-WARN-004] Database connection has issues",
                    extra={"init_id": init_id, "health_check": health_check_result},
                )

                # In development, allow the app to start even if database connection fails
                if os.getenv("NODE_ENV") == "development":
                    logger.warning(
                        "[DB-INIT-WARN-005] Continuing in development mode despite database connection issues",
                        extra={"init_id": init_id},
                    )
                    self.is_initialized = True
                else:
                    raise DatabaseError("Database connection health check failed")

            logger.info(
                "[DB-INIT-005] Database initialization completed",
                extra={
                    "init_id": init_id,
                    "status": self.connection_status,
                    "is_initialized": self.is_initialized,
                    "timestamp": datetime.now().isoformat(),
                },
            )

        except Exception as error:
            self.connection_status = "error"
            message = f"Database initialization failed: {str(error)}"
            logger.error(
                "[DB-INIT-ERROR] Database initialization failed",
                extra={
                    "init_id": init_id,
                    "error": {"message": str(error), "type": type(error).__name__},
                },
            )

            if os.getenv("NODE_ENV") == "development":
                logger.warning(
                    "[DB-INIT-WARN] Continuing in development mode despite initialization failure",
                    extra={"init_id": init_id},
                )
                self.is_initialized = True
            else:
                raise DatabaseError(message, error)

    def get_client(self) -> Client:
        """Get Supabase client instance with initialization check"""
        if not self.client or not self.is_initialized:
            raise DatabaseError("Database not initialized. Call initialize() first.")
        return self.client

    async def perform_health_check(self) -> Dict[str, Any]:
        """Perform comprehensive database health check"""
        start_time = datetime.now()
        health_check_id = f"health-{int(start_time.timestamp())}"

        logger.debug(
            "[DB-HEALTH-001] Starting database health check",
            extra={"health_check_id": health_check_id},
        )

        result = {
            "is_healthy": False,
            "checks": {"connection": False, "auth": False, "tables": {}},
            "response_time": 0,
            "timestamp": start_time,
            "error": None,
        }

        try:
            # Test basic connection
            logger.debug(
                "[DB-HEALTH-002] Testing basic connection",
                extra={"health_check_id": health_check_id},
            )

            # Try to access a dummy table - if we get a "relation does not exist" error, that's good
            try:
                response = self.client.table("_dummy_").select("*").limit(0).execute()
                # Connection is good if we can make the request (even if table doesn't exist)
                result["checks"]["connection"] = True
            except Exception as conn_error:
                # Expected errors that indicate connection is working:
                # - PostgreSQL: "relation does not exist"
                # - Supabase: "Could not find the table" or "schema cache"
                error_str = str(conn_error)
                connection_working_indicators = [
                    "relation" in error_str and "does not exist" in error_str,
                    "Could not find the table" in error_str,
                    "schema cache" in error_str,
                    "PGRST205" in error_str  # Supabase table not found error code
                ]

                if any(connection_working_indicators):
                    logger.debug(
                        "[DB-HEALTH-CONN-OK] Connection test passed (dummy table doesn't exist as expected)",
                        extra={"health_check_id": health_check_id, "error": error_str},
                    )
                    result["checks"]["connection"] = True
                else:
                    logger.error(
                        "[DB-HEALTH-CONN-ERROR] Connection test failed",
                        extra={
                            "health_check_id": health_check_id,
                            "error": error_str,
                            "error_type": type(conn_error).__name__,
                        },
                    )
                    result["checks"]["connection"] = False
                    raise conn_error

            if result["checks"]["connection"]:
                logger.debug(
                    "[DB-HEALTH-003] Basic connection successful",
                    extra={"health_check_id": health_check_id},
                )

                # Test authentication by checking if we can access the users table
                try:
                    response = (
                        self.client.table("users")
                        .select("*", count="exact")
                        .limit(0)
                        .execute()
                    )
                    result["checks"]["auth"] = True
                    logger.debug(
                        "[DB-HEALTH-004] Auth check result",
                        extra={
                            "health_check_id": health_check_id,
                            "auth_result": result["checks"]["auth"],
                        },
                    )
                except Exception as auth_error:
                    logger.error(
                        "[DB-HEALTH-WARN-004] Auth check failed",
                        extra={
                            "health_check_id": health_check_id,
                            "error": str(auth_error),
                            "error_type": type(auth_error).__name__,
                        },
                    )
                    result["checks"]["auth"] = False

                # Test key tables existence
                critical_tables = ["users", "games", "playlists"]

                for table in critical_tables:
                    try:
                        response = (
                            self.client.table(table)
                            .select("*", count="exact")
                            .limit(0)
                            .execute()
                        )
                        result["checks"]["tables"][table] = True

                        logger.debug(
                            "[DB-HEALTH-005] Table check result",
                            extra={
                                "health_check_id": health_check_id,
                                "table": table,
                                "exists": result["checks"]["tables"][table],
                            },
                        )
                    except Exception as table_error:
                        result["checks"]["tables"][table] = False
                        logger.debug(
                            "[DB-HEALTH-WARN-005] Table check failed",
                            extra={
                                "health_check_id": health_check_id,
                                "table": table,
                                "error": str(table_error),
                            },
                        )

            # Determine overall health
            result["is_healthy"] = (
                result["checks"]["connection"] and result["checks"]["auth"]
            )

        except Exception as error:
            result["error"] = str(error)
            logger.error(
                "[DB-HEALTH-ERROR] Health check failed",
                extra={
                    "health_check_id": health_check_id,
                    "error": result["error"],
                    "error_type": type(error).__name__,
                },
            )

        end_time = datetime.now()
        result["response_time"] = (
            end_time - start_time
        ).total_seconds() * 1000  # Convert to milliseconds
        self.last_health_check = result["timestamp"]

        logger.debug(
            "[DB-HEALTH-006] Health check completed",
            extra={
                "health_check_id": health_check_id,
                "result": {
                    "is_healthy": result["is_healthy"],
                    "response_time": result["response_time"],
                    "checks": result["checks"],
                },
            },
        )

        return result

    async def health_check(self) -> bool:
        """Simple health check for testing - returns True if database is healthy"""
        health_result = await self.perform_health_check()
        return health_result.get("is_healthy", False)

    def get_status(self) -> Dict[str, Any]:
        """Get database connection status and statistics"""
        uptime = None
        if self.is_initialized and self.last_health_check:
            uptime = (datetime.now() - self.last_health_check).total_seconds() * 1000

        return {
            "status": self.connection_status,
            "is_initialized": self.is_initialized,
            "last_health_check": self.last_health_check,
            "uptime": uptime,
        }

    # Database query helpers with consistent error handling

    async def execute_query(self, query_fn):
        """Generic query helper with comprehensive error handling"""
        try:
            if not self.client or not self.is_initialized:
                raise DatabaseError(
                    "Database not initialized. Call initialize() first."
                )

            result = query_fn(self.client)

            if hasattr(result, "execute"):
                response = result.execute()
                if hasattr(response, "data") and response.data is not None:
                    return response.data
                else:
                    raise NotFoundError("No data returned from query")
            else:
                return result

        except Exception as error:
            if isinstance(error, (DatabaseError, NotFoundError)):
                raise error
            message = f"Unexpected database error: {str(error)}"
            logger.error(
                "[DB-QUERY-ERROR] Unexpected database error",
                extra={"error": {"message": str(error), "type": type(error).__name__}},
            )
            raise DatabaseError(message, error)

    async def create_record(self, table: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new record in the specified table"""
        try:
            logger.debug(
                "[DB-CREATE] Creating record",
                extra={"table": table, "data_keys": list(data.keys())},
            )

            def query_fn(client):
                return client.table(table).insert(data)

            result = await self.execute_query(query_fn)
            return result[0] if result and len(result) > 0 else {}

        except Exception as error:
            message = f"Failed to create record in {table}: {str(error)}"
            logger.error(
                "[DB-CREATE-ERROR] Create record failed",
                extra={"table": table, "error": str(error)},
            )
            raise DatabaseError(message, error)

    async def get_record(self, table: str, record_id: str) -> Optional[Dict[str, Any]]:
        """Get a single record by ID"""
        try:
            logger.debug(
                f"[DB-GET] Getting record", extra={"table": table, "id": record_id}
            )

            if not self.client or not self.is_initialized:
                raise DatabaseError(
                    "Database not initialized. Call initialize() first."
                )

            response = (
                self.client.table(table).select("*").eq("id", record_id).execute()
            )

            if response.data and len(response.data) > 0:
                return response.data[0]
            else:
                logger.debug(
                    "[DB-GET] Record not found",
                    extra={"table": table, "id": record_id},
                )
                return None

        except Exception as error:
            if isinstance(error, DatabaseError):
                raise error
            message = f"Unexpected error getting record from {table}: {str(error)}"
            logger.error(
                "[DB-GET-ERROR] Unexpected get record error",
                extra={"table": table, "id": record_id, "error": str(error)},
            )
            raise DatabaseError(message, error)

    async def update_record(
        self, table: str, record_id: str, updates: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Update a record by ID"""
        try:
            logger.debug(
                "[DB-UPDATE] Updating record",
                extra={
                    "table": table,
                    "id": record_id,
                    "update_keys": list(updates.keys()),
                },
            )

            def query_fn(client):
                return client.table(table).update(updates).eq("id", record_id)

            result = await self.execute_query(query_fn)
            return result[0] if result and len(result) > 0 else {}

        except Exception as error:
            message = f"Failed to update record in {table}: {str(error)}"
            logger.error(
                "[DB-UPDATE-ERROR] Update record failed",
                extra={"table": table, "id": record_id, "error": str(error)},
            )
            raise DatabaseError(message, error)

    async def delete_record(self, table: str, record_id: str) -> None:
        """Delete a record by ID"""
        try:
            logger.debug(
                f"[DB-DELETE] Deleting record", extra={"table": table, "id": record_id}
            )

            if not self.client or not self.is_initialized:
                raise DatabaseError(
                    "Database not initialized. Call initialize() first."
                )

            response = self.client.table(table).delete().eq("id", record_id).execute()

            logger.debug(
                "[DB-DELETE] Record deleted successfully",
                extra={"table": table, "id": record_id},
            )

        except Exception as error:
            if isinstance(error, DatabaseError):
                raise error
            message = f"Unexpected error deleting record from {table}: {str(error)}"
            logger.error(
                "[DB-DELETE-ERROR] Unexpected delete record error",
                extra={"table": table, "id": record_id, "error": str(error)},
            )
            raise DatabaseError(message, error)

    async def query_records(self, table: str, **kwargs) -> List[Dict[str, Any]]:
        """Query multiple records with filtering, ordering, and pagination"""
        try:
            filters = kwargs.get("filters", {})
            order_by = kwargs.get("order_by")
            limit = kwargs.get("limit")
            offset = kwargs.get("offset")
            select_fields = kwargs.get("select", "*")

            logger.debug(
                "[DB-QUERY] Querying records",
                extra={
                    "table": table,
                    "filter_count": len(filters) if filters else 0,
                    "order_by": order_by,
                    "limit": limit,
                    "offset": offset,
                },
            )

            if not self.client or not self.is_initialized:
                raise DatabaseError(
                    "Database not initialized. Call initialize() first."
                )

            query = self.client.table(table).select(select_fields)

            # Apply filters
            if filters:
                for column, value in filters.items():
                    if isinstance(value, dict):
                        # Handle complex filter operations
                        for operation, filter_value in value.items():
                            if operation == "in":
                                query = query.in_(column, filter_value)
                            elif operation == "eq":
                                query = query.eq(column, filter_value)
                            elif operation == "neq":
                                query = query.neq(column, filter_value)
                            elif operation == "gt":
                                query = query.gt(column, filter_value)
                            elif operation == "gte":
                                query = query.gte(column, filter_value)
                            elif operation == "lt":
                                query = query.lt(column, filter_value)
                            elif operation == "lte":
                                query = query.lte(column, filter_value)
                            else:
                                # Fallback for unknown operations
                                query = query.eq(column, filter_value)
                    else:
                        # Simple equality filter
                        query = query.eq(column, value)

            # Apply ordering
            if order_by:
                if isinstance(order_by, dict):
                    ascending = order_by.get("ascending", True)
                    column = order_by.get("column")
                    if column:
                        query = query.order(column, desc=not ascending)
                elif isinstance(order_by, str):
                    query = query.order(order_by)

            # Apply pagination
            if limit:
                query = query.limit(limit)

            if offset:
                query = query.range(offset, offset + (limit or 100) - 1)

            response = query.execute()
            result = response.data or []

            logger.debug(
                "[DB-QUERY] Query completed",
                extra={"table": table, "result_count": len(result)},
            )

            return result

        except Exception as error:
            if isinstance(error, DatabaseError):
                raise error
            message = f"Unexpected error querying records from {table}: {str(error)}"
            logger.error(
                "[DB-QUERY-ERROR] Unexpected query records error",
                extra={
                    "table": table, 
                    "error": str(error),
                    "error_type": type(error).__name__,
                    "filters": filters,
                    "order_by": order_by,
                    "limit": limit,
                    "offset": offset,
                    "select_fields": select_fields
                },
                exc_info=True  # Include full traceback
            )
            raise DatabaseError(message, error)

    async def count_records(
        self, table: str, filters: Optional[Dict[str, Any]] = None
    ) -> int:
        """Count records in a table with optional filters"""
        try:
            logger.debug(
                "[DB-COUNT] Counting records",
                extra={"table": table, "filter_count": len(filters) if filters else 0},
            )

            if not self.client or not self.is_initialized:
                raise DatabaseError(
                    "Database not initialized. Call initialize() first."
                )

            query = self.client.table(table).select("*", count="exact")

            # Apply filters
            if filters:
                for column, value in filters.items():
                    query = query.eq(column, value)

            response = query.execute()
            result = response.count or 0

            logger.debug(
                f"[DB-COUNT] Count completed", extra={"table": table, "count": result}
            )

            return result

        except Exception as error:
            if isinstance(error, DatabaseError):
                raise error
            message = f"Unexpected error counting records in {table}: {str(error)}"
            logger.error(
                "[DB-COUNT-ERROR] Unexpected count records error",
                extra={"table": table, "error": str(error)},
            )
            raise DatabaseError(message, error)


# Global database instance
database = SupabaseService()
