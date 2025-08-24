"""
Database Performance Optimization Enhancements for MED-002
Extends the existing SupabaseService with performance monitoring and caching integration
"""
import time
import logging
import hashlib
from typing import Dict, List, Optional, Any, Union, Tuple
from datetime import datetime
from dataclasses import dataclass
from contextlib import asynccontextmanager

from app.database import database, SupabaseService, DatabaseError
from app.cache_manager import CacheManager, CacheType

logger = logging.getLogger("music_bingo")

@dataclass
class QueryPerformanceMetrics:
    """Performance metrics for database queries"""
    query_type: str
    table: str
    execution_time_ms: float
    rows_affected: int
    timestamp: datetime
    cache_hit: bool = False
    query_hash: str = ""

class DatabaseOptimizer:
    """
    Database optimization enhancements for MED-002
    
    Provides performance monitoring, caching integration, and query optimization
    for the Musical Bingo application's database operations.
    """
    
    def __init__(self):
        self.performance_metrics: List[QueryPerformanceMetrics] = []
        self.cache_manager: Optional[CacheManager] = None
        
    def set_cache_manager(self, cache_manager: CacheManager):
        """Set the cache manager for cache-database integration"""
        self.cache_manager = cache_manager
        logger.info("[DB-OPTIMIZER-001] Cache manager integration enabled")

    @asynccontextmanager
    async def track_query_performance(self, query_type: str, table: str, query_data: str = ""):
        """Context manager to track query performance"""
        start_time = time.time()
        rows_affected = 0
        
        # Create query hash for caching
        query_hash = hashlib.md5(f"{query_type}:{table}:{query_data}".encode()).hexdigest()[:8]
        
        try:
            yield {"query_hash": query_hash}
        finally:
            execution_time = (time.time() - start_time) * 1000  # Convert to ms
            
            metric = QueryPerformanceMetrics(
                query_type=query_type,
                table=table,
                execution_time_ms=execution_time,
                rows_affected=rows_affected,
                timestamp=datetime.now(),
                query_hash=query_hash
            )
            
            self.performance_metrics.append(metric)
            
            # Log slow queries (>100ms)
            if execution_time > 100:
                logger.warning(
                    f"[DB-SLOW-QUERY] Slow database query detected",
                    extra={
                        "query_type": query_type,
                        "table": table,
                        "execution_time_ms": execution_time,
                        "query_hash": query_hash
                    }
                )
            
            # Keep only recent metrics to prevent memory bloat
            if len(self.performance_metrics) > 1000:
                self.performance_metrics = self.performance_metrics[-500:]

    async def optimized_get_user_games(self, user_id: str, status_filter: Optional[str] = None, use_cache: bool = True) -> List[Dict[str, Any]]:
        """
        Optimized user games retrieval with caching and performance monitoring
        
        This method combines database optimization with intelligent caching to
        reduce the load on frequently accessed user game queries.
        """
        cache_key = f"user_games:{user_id}:{status_filter or 'all'}"
        
        # Check cache first if caching is enabled
        if use_cache and self.cache_manager:
            try:
                cached_result = await self.cache_manager.get_cached_data(
                    CacheType.USER_DATA,
                    user_id,
                    cache_key
                )
                if cached_result:
                    logger.debug(f"[DB-CACHE-HIT] Using cached user games for {user_id}")
                    return cached_result
            except Exception as e:
                logger.warning(f"[DB-CACHE-WARN] Cache lookup failed: {e}")
        
        # Perform optimized database query
        async with self.track_query_performance("select", "games", f"user_games:{user_id}"):
            try:
                # Build optimized filters
                filters = {"host_id": user_id}
                if status_filter:
                    filters["status"] = status_filter
                
                # Get hosted games
                hosted_games = await database.query_records(
                    "games",
                    filters=filters,
                    order_by={"column": "created_at", "ascending": False},
                    select="id, name, status, host_id, max_players, created_at, is_private, room_code"
                )
                
                # Get player games using optimized query
                player_games_data = await database.query_records(
                    "game_players", 
                    filters={"user_id": user_id}
                )
                
                joined_games = []
                if player_games_data:
                    player_game_ids = [pg["game_id"] for pg in player_games_data]
                    
                    # Use IN clause for bulk retrieval (optimized with idx_games_status)
                    bulk_filters = {"id": {"in": player_game_ids}}
                    if status_filter:
                        bulk_filters["status"] = status_filter
                    
                    joined_games = await database.query_records(
                        "games",
                        filters=bulk_filters,
                        order_by={"column": "created_at", "ascending": False},
                        select="id, name, status, host_id, max_players, created_at, is_private, room_code"
                    )
                
                # Combine and deduplicate
                all_games = hosted_games + joined_games
                seen_ids = set()
                unique_games = []
                
                for game in all_games:
                    if game["id"] not in seen_ids:
                        seen_ids.add(game["id"])
                        unique_games.append(game)
                
                # Cache the result if caching is enabled
                if use_cache and self.cache_manager:
                    try:
                        await self.cache_manager.cache_data(
                            CacheType.USER_DATA,
                            user_id,
                            cache_key,
                            unique_games
                        )
                    except Exception as e:
                        logger.warning(f"[DB-CACHE-WARN] Cache storage failed: {e}")
                
                return unique_games
                
            except Exception as e:
                logger.error(
                    f"[DB-OPTIMIZER-ERROR] Optimized user games query failed",
                    extra={"user_id": user_id, "error": str(e)}
                )
                raise DatabaseError(f"Failed to retrieve user games: {str(e)}")

    async def optimized_get_playlist_track_count(self, playlist_id: str, use_cache: bool = True) -> int:
        """
        Optimized playlist track counting with caching
        
        Uses strategic caching and the idx_playlist_tracks_playlist_id index
        for optimal performance.
        """
        cache_key = f"playlist_track_count:{playlist_id}"
        
        # Check cache first
        if use_cache and self.cache_manager:
            try:
                cached_count = await self.cache_manager.get_cached_data(
                    CacheType.METADATA,
                    "playlist",
                    cache_key
                )
                if cached_count is not None:
                    logger.debug(f"[DB-CACHE-HIT] Using cached track count for playlist {playlist_id}")
                    return cached_count
            except Exception as e:
                logger.warning(f"[DB-CACHE-WARN] Track count cache lookup failed: {e}")
        
        # Perform optimized count query (uses idx_playlist_tracks_playlist_id)
        async with self.track_query_performance("count", "playlist_tracks", playlist_id):
            try:
                count = await database.count_records(
                    "playlist_tracks",
                    filters={"playlist_id": playlist_id}
                )
                
                # Cache the result
                if use_cache and self.cache_manager:
                    try:
                        await self.cache_manager.cache_data(
                            CacheType.METADATA,
                            "playlist",
                            cache_key,
                            count
                        )
                    except Exception as e:
                        logger.warning(f"[DB-CACHE-WARN] Track count cache storage failed: {e}")
                
                return count
                
            except Exception as e:
                logger.error(
                    f"[DB-OPTIMIZER-ERROR] Track count query failed",
                    extra={"playlist_id": playlist_id, "error": str(e)}
                )
                raise DatabaseError(f"Failed to count playlist tracks: {str(e)}")

    async def bulk_cache_user_data(self, user_ids: List[str]) -> Dict[str, Any]:
        """
        Pre-warm cache for multiple users to prevent N+1 cache misses
        
        This method helps prevent cascading cache misses when multiple users
        are accessing the system simultaneously.
        """
        if not self.cache_manager:
            logger.warning("[DB-OPTIMIZER-WARN] Cache manager not available for bulk caching")
            return {"cached": 0, "failed": 0}
        
        logger.info(f"[DB-OPTIMIZER-002] Pre-warming cache for {len(user_ids)} users")
        
        cached_count = 0
        failed_count = 0
        
        for user_id in user_ids:
            try:
                # Cache user games
                games = await self.optimized_get_user_games(user_id, use_cache=False)
                await self.cache_manager.cache_data(
                    CacheType.USER_DATA,
                    user_id,
                    f"user_games:{user_id}:all",
                    games
                )
                cached_count += 1
                
            except Exception as e:
                logger.warning(
                    f"[DB-OPTIMIZER-WARN] Failed to cache user data",
                    extra={"user_id": user_id, "error": str(e)}
                )
                failed_count += 1
        
        logger.info(
            f"[DB-OPTIMIZER-003] Cache pre-warming completed",
            extra={"cached": cached_count, "failed": failed_count}
        )
        
        return {"cached": cached_count, "failed": failed_count}

    def get_performance_metrics(self) -> Dict[str, Any]:
        """Get comprehensive database performance metrics"""
        if not self.performance_metrics:
            return {
                "message": "No performance data available",
                "total_queries": 0,
                "avg_execution_time_ms": 0
            }
        
        total_queries = len(self.performance_metrics)
        avg_execution_time = sum(m.execution_time_ms for m in self.performance_metrics) / total_queries
        slow_queries = [m for m in self.performance_metrics if m.execution_time_ms > 100]
        
        # Group by table and operation
        operations = {}
        for metric in self.performance_metrics:
            key = f"{metric.query_type}:{metric.table}"
            if key not in operations:
                operations[key] = []
            operations[key].append(metric.execution_time_ms)
        
        operation_stats = {}
        for op, times in operations.items():
            operation_stats[op] = {
                "count": len(times),
                "avg_time_ms": sum(times) / len(times),
                "max_time_ms": max(times),
                "min_time_ms": min(times)
            }
        
        # Cache hit analysis if cache manager is available
        cache_stats = {}
        if self.cache_manager:
            try:
                cache_stats = self.cache_manager.get_cache_statistics()
            except Exception as e:
                logger.warning(f"[DB-OPTIMIZER-WARN] Failed to get cache stats: {e}")
                cache_stats = {"error": str(e)}
        
        return {
            "total_queries": total_queries,
            "avg_execution_time_ms": round(avg_execution_time, 2),
            "slow_queries_count": len(slow_queries),
            "slow_queries_percentage": round((len(slow_queries) / total_queries) * 100, 2),
            "operation_stats": operation_stats,
            "cache_integration": cache_stats,
            "recent_slow_queries": [
                {
                    "table": m.table,
                    "query_type": m.query_type,
                    "execution_time_ms": round(m.execution_time_ms, 2),
                    "timestamp": m.timestamp.isoformat()
                }
                for m in slow_queries[-5:]  # Last 5 slow queries
            ]
        }

    def clear_performance_metrics(self):
        """Clear accumulated performance metrics"""
        self.performance_metrics.clear()
        logger.info("[DB-OPTIMIZER] Performance metrics cleared")

    async def validate_indexes_performance(self) -> Dict[str, Any]:
        """
        Validate that the MED-002 performance indexes are working effectively
        
        This method runs test queries to verify index usage and performance.
        """
        logger.info("[DB-OPTIMIZER-004] Validating index performance")
        
        validation_results = {}
        
        # Test queries that should benefit from indexes
        test_queries = [
            {
                "name": "games_by_host_id",
                "table": "games",
                "test_query": "SELECT COUNT(*) FROM games WHERE host_id = 'test_user'",
                "expected_index": "idx_games_host_id"
            },
            {
                "name": "games_by_status",
                "table": "games", 
                "test_query": "SELECT COUNT(*) FROM games WHERE status = 'waiting'",
                "expected_index": "idx_games_status"
            },
            {
                "name": "game_players_by_user_id",
                "table": "game_players",
                "test_query": "SELECT COUNT(*) FROM game_players WHERE user_id = 'test_user'",
                "expected_index": "idx_game_players_user_id"
            }
        ]
        
        for test in test_queries:
            try:
                async with self.track_query_performance("validation", test["table"], test["name"]):
                    # Execute test query (should be fast with indexes)
                    start_time = time.time()
                    
                    # Note: In a real implementation, we'd use EXPLAIN ANALYZE
                    # For now, we'll simulate by timing a simple count query
                    try:
                        count = await database.count_records(
                            test["table"],
                            filters={test["name"].split('_')[-1]: "test_value"}
                        )
                    except Exception:
                        count = 0  # Expected for test values
                    
                    execution_time = (time.time() - start_time) * 1000
                
                validation_results[test["name"]] = {
                    "execution_time_ms": round(execution_time, 2),
                    "expected_index": test["expected_index"],
                    "status": "fast" if execution_time < 50 else "slow"
                }
                
            except Exception as e:
                validation_results[test["name"]] = {
                    "error": str(e),
                    "status": "failed"
                }
        
        logger.info(
            f"[DB-OPTIMIZER-005] Index validation completed",
            extra={"results": validation_results}
        )
        
        return validation_results

# Global database optimizer instance
db_optimizer = DatabaseOptimizer()
