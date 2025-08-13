"""
Production-grade Redis/Dragonfly caching layer for performance optimization.

This module implements a comprehensive caching system with:
- Multiple cache types (playlists, tracks, user data, metadata)
- TTL-based expiration policies
- Cache invalidation strategies
- Statistics and monitoring
- Performance optimization features
- Integration with existing Dragonfly setup

Key Features:
- Automatic cache warming and refreshing
- Cache hit/miss statistics
- Memory usage monitoring
- Bulk operations for performance
- Namespace-based organization
- Configurable TTL policies
- Health monitoring and diagnostics

Cache Structure:
- Playlists: User playlists and metadata
- Tracks: Track information and analysis data
- User Sessions: User preferences and temporary data
- Game State: Temporary game-related cached data
- Metadata: Spotify API responses and computed data

Cache Key Schema:
- mb:playlist:{user_id}:{playlist_id}
- mb:track:{track_id}
- mb:user:{user_id}:data
- mb:game:{game_id}:state
- mb:meta:{type}:{identifier}
"""

import asyncio
import json
import logging
import hashlib
import time
from typing import Dict, Any, Optional, List, Union, Set, Tuple
from datetime import datetime, timezone, timedelta
from contextlib import asynccontextmanager
from dataclasses import dataclass, asdict
from enum import Enum

import redis.asyncio as redis
from app.config import get_config

logger = logging.getLogger("music_bingo")

class CacheType(Enum):
    """Cache types with different TTL policies."""
    PLAYLIST = "playlist"
    TRACK = "track"
    USER_DATA = "user"
    GAME_STATE = "game"
    METADATA = "meta"
    SESSION_DATA = "session"

@dataclass
class CacheEntry:
    """Cache entry with metadata."""
    data: Any
    created_at: float
    ttl: int
    hits: int = 0
    last_accessed: float = None

@dataclass
class CacheStats:
    """Cache statistics for monitoring."""
    total_keys: int
    total_memory: int
    hit_rate: float
    miss_rate: float
    eviction_rate: float
    avg_ttl: float
    cache_types: Dict[str, int]

class CacheManager:
    """
    Production-grade Redis/Dragonfly cache manager.
    
    Provides high-performance caching with automatic TTL management,
    invalidation strategies, and comprehensive monitoring.
    """
    
    def __init__(self):
        """Initialize cache manager with configuration."""
        self.config = get_config()
        self.redis_client: Optional[redis.Redis] = None
        self._connection_lock = asyncio.Lock()
        
        # Cache configuration with TTL policies (in seconds)
        self.ttl_policies = {
            CacheType.PLAYLIST: 3600,      # 1 hour - playlists change infrequently
            CacheType.TRACK: 86400,        # 24 hours - track metadata is stable
            CacheType.USER_DATA: 1800,     # 30 minutes - user preferences
            CacheType.GAME_STATE: 7200,    # 2 hours - active game data
            CacheType.METADATA: 43200,     # 12 hours - API response caching
            CacheType.SESSION_DATA: 900,   # 15 minutes - temporary session data
        }
        
        # Cache key prefixes for organization
        self.key_prefix = "mb"  # MusicBingo prefix
        self.stats_key = f"{self.key_prefix}:stats"
        self.health_key = f"{self.key_prefix}:health"
        
        # Statistics tracking
        self._stats_cache = {
            'hits': 0,
            'misses': 0,
            'sets': 0,
            'deletes': 0,
            'evictions': 0,
            'errors': 0
        }
        
        # Cache warming configuration
        self.warm_on_startup = True
        self.auto_refresh_enabled = True
        self.bulk_operation_size = 100
        
    async def _get_redis(self) -> redis.Redis:
        """Get or create Redis connection with error handling."""
        if self.redis_client is None:
            async with self._connection_lock:
                if self.redis_client is None:
                    try:
                        # Use existing Redis configuration from config
                        connection_kwargs = {
                            "decode_responses": True,
                            "socket_connect_timeout": 5,
                            "socket_timeout": 5,
                            "retry_on_timeout": True,
                            "health_check_interval": 30,
                            "max_connections": 20
                        }
                        
                        if self.config.redis_password:
                            connection_kwargs["password"] = self.config.redis_password
                        
                        self.redis_client = redis.from_url(
                            self.config.redis_url,
                            **connection_kwargs
                        )
                        
                        # Test connection
                        await self.redis_client.ping()
                        logger.info(f"Cache manager connected to Redis at {self.config.redis_url}")
                        
                        # Initialize cache statistics if needed
                        await self._initialize_stats()
                        
                    except Exception as e:
                        logger.error(f"Failed to connect cache manager to Redis: {e}")
                        raise CacheConnectionError(f"Redis connection failed: {e}")
        
        return self.redis_client
    
    async def _initialize_stats(self):
        """Initialize cache statistics storage."""
        try:
            redis_client = await self._get_redis()
            
            # Initialize stats if they don't exist
            if not await redis_client.exists(self.stats_key):
                initial_stats = {
                    'hits': 0,
                    'misses': 0,
                    'sets': 0,
                    'deletes': 0,
                    'evictions': 0,
                    'errors': 0,
                    'created_at': datetime.now(timezone.utc).isoformat()
                }
                await redis_client.hset(self.stats_key, mapping=initial_stats)
                
                # Set health check data
                health_data = {
                    'status': 'healthy',
                    'last_check': datetime.now(timezone.utc).isoformat(),
                    'version': '1.0.0'
                }
                await redis_client.hset(self.health_key, mapping=health_data)
                
        except Exception as e:
            logger.error(f"Failed to initialize cache stats: {e}")
    
    def _generate_key(self, cache_type: CacheType, identifier: str, user_id: str = None) -> str:
        """
        Generate cache key with proper namespacing.
        
        Args:
            cache_type: Type of cache entry
            identifier: Primary identifier
            user_id: Optional user context
            
        Returns:
            Formatted cache key
        """
        if user_id:
            return f"{self.key_prefix}:{cache_type.value}:{user_id}:{identifier}"
        else:
            return f"{self.key_prefix}:{cache_type.value}:{identifier}"
    
    def _serialize_data(self, data: Any) -> str:
        """Serialize data for Redis storage."""
        try:
            if isinstance(data, (dict, list)):
                return json.dumps(data, default=str, ensure_ascii=False)
            elif isinstance(data, (int, float, bool)):
                return str(data)
            elif isinstance(data, str):
                return data
            else:
                # For complex objects, try to convert to dict first
                if hasattr(data, '__dict__'):
                    return json.dumps(data.__dict__, default=str, ensure_ascii=False)
                else:
                    return json.dumps(data, default=str, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to serialize cache data: {e}")
            raise CacheSerializationError(f"Serialization failed: {e}")
    
    def _deserialize_data(self, data: str) -> Any:
        """Deserialize data from Redis storage."""
        try:
            # Try JSON deserialization first
            try:
                return json.loads(data)
            except json.JSONDecodeError:
                # If JSON fails, return as string
                return data
        except Exception as e:
            logger.error(f"Failed to deserialize cache data: {e}")
            return data  # Return raw data if deserialization fails
    
    async def _update_stats(self, operation: str, count: int = 1):
        """Update cache statistics."""
        try:
            redis_client = await self._get_redis()
            await redis_client.hincrby(self.stats_key, operation, count)
            
            # Update local stats cache
            if operation in self._stats_cache:
                self._stats_cache[operation] += count
                
        except Exception as e:
            logger.error(f"Failed to update cache stats for {operation}: {e}")
    
    async def set(
        self,
        cache_type: CacheType,
        identifier: str,
        data: Any,
        ttl: Optional[int] = None,
        user_id: Optional[str] = None
    ) -> bool:
        """
        Set cache entry with automatic TTL management.
        
        Args:
            cache_type: Type of cache entry
            identifier: Primary identifier
            data: Data to cache
            ttl: Optional custom TTL (uses policy default if not provided)
            user_id: Optional user context
            
        Returns:
            True if successful, False otherwise
        """
        try:
            redis_client = await self._get_redis()
            
            # Generate cache key
            cache_key = self._generate_key(cache_type, identifier, user_id)
            
            # Use configured TTL or custom TTL
            effective_ttl = ttl or self.ttl_policies.get(cache_type, 3600)
            
            # Create cache entry with metadata
            cache_entry = CacheEntry(
                data=data,
                created_at=time.time(),
                ttl=effective_ttl,
                hits=0,
                last_accessed=time.time()
            )
            
            # Serialize and store
            serialized_data = self._serialize_data(asdict(cache_entry))
            await redis_client.setex(cache_key, effective_ttl, serialized_data)
            
            # Update statistics
            await self._update_stats('sets')
            
            logger.debug(
                f"[CACHE-SET] {cache_type.value}:{identifier} (TTL: {effective_ttl}s)",
                extra={"cache_key": cache_key, "user_id": user_id}
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to set cache entry: {e}")
            await self._update_stats('errors')
            return False
    
    async def get(
        self,
        cache_type: CacheType,
        identifier: str,
        user_id: Optional[str] = None
    ) -> Optional[Any]:
        """
        Get cache entry with hit tracking.
        
        Args:
            cache_type: Type of cache entry
            identifier: Primary identifier
            user_id: Optional user context
            
        Returns:
            Cached data if found, None otherwise
        """
        try:
            redis_client = await self._get_redis()
            
            # Generate cache key
            cache_key = self._generate_key(cache_type, identifier, user_id)
            
            # Retrieve from cache
            cached_data = await redis_client.get(cache_key)
            
            if cached_data:
                # Deserialize cache entry
                cache_entry_dict = self._deserialize_data(cached_data)
                
                if isinstance(cache_entry_dict, dict) and 'data' in cache_entry_dict:
                    # Update hit count and last accessed time
                    cache_entry_dict['hits'] += 1
                    cache_entry_dict['last_accessed'] = time.time()
                    
                    # Store updated metadata
                    ttl = await redis_client.ttl(cache_key)
                    if ttl > 0:
                        updated_data = self._serialize_data(cache_entry_dict)
                        await redis_client.setex(cache_key, ttl, updated_data)
                    
                    # Update statistics
                    await self._update_stats('hits')
                    
                    logger.debug(
                        f"[CACHE-HIT] {cache_type.value}:{identifier}",
                        extra={"cache_key": cache_key, "user_id": user_id}
                    )
                    
                    return cache_entry_dict['data']
                else:
                    # Handle legacy cache entries without metadata
                    await self._update_stats('hits')
                    return cache_entry_dict
            else:
                # Cache miss
                await self._update_stats('misses')
                
                logger.debug(
                    f"[CACHE-MISS] {cache_type.value}:{identifier}",
                    extra={"cache_key": cache_key, "user_id": user_id}
                )
                
                return None
                
        except Exception as e:
            logger.error(f"Failed to get cache entry: {e}")
            await self._update_stats('errors')
            return None
    
    async def delete(
        self,
        cache_type: CacheType,
        identifier: str,
        user_id: Optional[str] = None
    ) -> bool:
        """
        Delete cache entry.
        
        Args:
            cache_type: Type of cache entry
            identifier: Primary identifier
            user_id: Optional user context
            
        Returns:
            True if deleted, False otherwise
        """
        try:
            redis_client = await self._get_redis()
            
            # Generate cache key
            cache_key = self._generate_key(cache_type, identifier, user_id)
            
            # Delete from cache
            deleted = await redis_client.delete(cache_key)
            
            if deleted:
                await self._update_stats('deletes')
                logger.debug(
                    f"[CACHE-DELETE] {cache_type.value}:{identifier}",
                    extra={"cache_key": cache_key, "user_id": user_id}
                )
                
            return bool(deleted)
            
        except Exception as e:
            logger.error(f"Failed to delete cache entry: {e}")
            await self._update_stats('errors')
            return False
    
    async def exists(
        self,
        cache_type: CacheType,
        identifier: str,
        user_id: Optional[str] = None
    ) -> bool:
        """
        Check if cache entry exists.
        
        Args:
            cache_type: Type of cache entry
            identifier: Primary identifier
            user_id: Optional user context
            
        Returns:
            True if exists, False otherwise
        """
        try:
            redis_client = await self._get_redis()
            cache_key = self._generate_key(cache_type, identifier, user_id)
            return bool(await redis_client.exists(cache_key))
        except Exception as e:
            logger.error(f"Failed to check cache existence: {e}")
            return False
    
    async def invalidate_pattern(self, pattern: str) -> int:
        """
        Invalidate cache entries matching a pattern.
        
        Args:
            pattern: Redis key pattern to match
            
        Returns:
            Number of keys deleted
        """
        try:
            redis_client = await self._get_redis()
            
            deleted_count = 0
            async for key in redis_client.scan_iter(match=pattern):
                if await redis_client.delete(key):
                    deleted_count += 1
            
            if deleted_count > 0:
                await self._update_stats('deletes', deleted_count)
                logger.info(f"[CACHE-INVALIDATE] Deleted {deleted_count} keys matching pattern: {pattern}")
            
            return deleted_count
            
        except Exception as e:
            logger.error(f"Failed to invalidate cache pattern {pattern}: {e}")
            await self._update_stats('errors')
            return 0
    
    async def invalidate_user_cache(self, user_id: str) -> int:
        """
        Invalidate all cache entries for a specific user.
        
        Args:
            user_id: User identifier
            
        Returns:
            Number of keys deleted
        """
        pattern = f"{self.key_prefix}:*:{user_id}:*"
        return await self.invalidate_pattern(pattern)
    
    async def invalidate_game_cache(self, game_id: str) -> int:
        """
        Invalidate all cache entries for a specific game.
        
        Args:
            game_id: Game identifier
            
        Returns:
            Number of keys deleted
        """
        pattern = f"{self.key_prefix}:game:*:{game_id}*"
        return await self.invalidate_pattern(pattern)
    
    async def bulk_set(
        self,
        cache_type: CacheType,
        entries: Dict[str, Any],
        ttl: Optional[int] = None,
        user_id: Optional[str] = None
    ) -> int:
        """
        Set multiple cache entries in bulk for performance.
        
        Args:
            cache_type: Type of cache entries
            entries: Dictionary of identifier -> data mappings
            ttl: Optional custom TTL
            user_id: Optional user context
            
        Returns:
            Number of successfully set entries
        """
        try:
            redis_client = await self._get_redis()
            
            # Use pipeline for bulk operations
            async with redis_client.pipeline() as pipe:
                effective_ttl = ttl or self.ttl_policies.get(cache_type, 3600)
                successful_sets = 0
                
                for identifier, data in entries.items():
                    try:
                        cache_key = self._generate_key(cache_type, identifier, user_id)
                        
                        cache_entry = CacheEntry(
                            data=data,
                            created_at=time.time(),
                            ttl=effective_ttl,
                            hits=0,
                            last_accessed=time.time()
                        )
                        
                        serialized_data = self._serialize_data(asdict(cache_entry))
                        pipe.setex(cache_key, effective_ttl, serialized_data)
                        successful_sets += 1
                        
                    except Exception as e:
                        logger.error(f"Failed to prepare bulk set for {identifier}: {e}")
                
                # Execute pipeline
                results = await pipe.execute()
                actual_sets = sum(1 for result in results if result)
                
                # Update statistics
                await self._update_stats('sets', actual_sets)
                
                logger.info(
                    f"[CACHE-BULK-SET] {cache_type.value}: {actual_sets}/{len(entries)} entries set",
                    extra={"user_id": user_id}
                )
                
                return actual_sets
                
        except Exception as e:
            logger.error(f"Failed to bulk set cache entries: {e}")
            await self._update_stats('errors')
            return 0
    
    async def bulk_get(
        self,
        cache_type: CacheType,
        identifiers: List[str],
        user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get multiple cache entries in bulk for performance.
        
        Args:
            cache_type: Type of cache entries
            identifiers: List of identifiers to retrieve
            user_id: Optional user context
            
        Returns:
            Dictionary of identifier -> data mappings for found entries
        """
        try:
            redis_client = await self._get_redis()
            
            # Generate all cache keys
            cache_keys = [
                self._generate_key(cache_type, identifier, user_id)
                for identifier in identifiers
            ]
            
            # Use pipeline for bulk operations
            async with redis_client.pipeline() as pipe:
                for cache_key in cache_keys:
                    pipe.get(cache_key)
                
                results = await pipe.execute()
            
            # Process results
            found_entries = {}
            hits = 0
            misses = 0
            
            for identifier, cache_key, cached_data in zip(identifiers, cache_keys, results):
                if cached_data:
                    try:
                        cache_entry_dict = self._deserialize_data(cached_data)
                        
                        if isinstance(cache_entry_dict, dict) and 'data' in cache_entry_dict:
                            found_entries[identifier] = cache_entry_dict['data']
                        else:
                            found_entries[identifier] = cache_entry_dict
                        
                        hits += 1
                    except Exception as e:
                        logger.error(f"Failed to deserialize bulk cache entry {identifier}: {e}")
                        misses += 1
                else:
                    misses += 1
            
            # Update statistics
            await self._update_stats('hits', hits)
            await self._update_stats('misses', misses)
            
            logger.debug(
                f"[CACHE-BULK-GET] {cache_type.value}: {hits} hits, {misses} misses",
                extra={"user_id": user_id}
            )
            
            return found_entries
            
        except Exception as e:
            logger.error(f"Failed to bulk get cache entries: {e}")
            await self._update_stats('errors')
            return {}
    
    async def get_ttl(
        self,
        cache_type: CacheType,
        identifier: str,
        user_id: Optional[str] = None
    ) -> int:
        """
        Get remaining TTL for cache entry.
        
        Args:
            cache_type: Type of cache entry
            identifier: Primary identifier
            user_id: Optional user context
            
        Returns:
            Remaining TTL in seconds, -1 if not found
        """
        try:
            redis_client = await self._get_redis()
            cache_key = self._generate_key(cache_type, identifier, user_id)
            return await redis_client.ttl(cache_key)
        except Exception as e:
            logger.error(f"Failed to get TTL: {e}")
            return -1
    
    async def extend_ttl(
        self,
        cache_type: CacheType,
        identifier: str,
        additional_seconds: int,
        user_id: Optional[str] = None
    ) -> bool:
        """
        Extend TTL for cache entry.
        
        Args:
            cache_type: Type of cache entry
            identifier: Primary identifier
            additional_seconds: Seconds to add to current TTL
            user_id: Optional user context
            
        Returns:
            True if successful, False otherwise
        """
        try:
            redis_client = await self._get_redis()
            cache_key = self._generate_key(cache_type, identifier, user_id)
            
            current_ttl = await redis_client.ttl(cache_key)
            if current_ttl > 0:
                new_ttl = current_ttl + additional_seconds
                return bool(await redis_client.expire(cache_key, new_ttl))
            
            return False
            
        except Exception as e:
            logger.error(f"Failed to extend TTL: {e}")
            return False
    
    async def get_cache_stats(self) -> CacheStats:
        """
        Get comprehensive cache statistics.
        
        Returns:
            Cache statistics object
        """
        try:
            redis_client = await self._get_redis()
            
            # Get stats from Redis
            stats_data = await redis_client.hgetall(self.stats_key)
            
            # Get Redis info for memory usage
            info = await redis_client.info()
            used_memory = info.get('used_memory', 0)
            
            # Count keys by type
            cache_types = {}
            total_keys = 0
            
            for cache_type in CacheType:
                pattern = f"{self.key_prefix}:{cache_type.value}:*"
                count = 0
                async for _ in redis_client.scan_iter(match=pattern):
                    count += 1
                cache_types[cache_type.value] = count
                total_keys += count
            
            # Calculate rates
            hits = int(stats_data.get('hits', 0))
            misses = int(stats_data.get('misses', 0))
            total_requests = hits + misses
            
            hit_rate = (hits / total_requests * 100) if total_requests > 0 else 0
            miss_rate = (misses / total_requests * 100) if total_requests > 0 else 0
            
            # Calculate average TTL
            total_ttl = 0
            ttl_count = 0
            
            for cache_type in CacheType:
                pattern = f"{self.key_prefix}:{cache_type.value}:*"
                async for key in redis_client.scan_iter(match=pattern):
                    ttl = await redis_client.ttl(key)
                    if ttl > 0:
                        total_ttl += ttl
                        ttl_count += 1
            
            avg_ttl = (total_ttl / ttl_count) if ttl_count > 0 else 0
            
            return CacheStats(
                total_keys=total_keys,
                total_memory=used_memory,
                hit_rate=hit_rate,
                miss_rate=miss_rate,
                eviction_rate=float(stats_data.get('evictions', 0)),
                avg_ttl=avg_ttl,
                cache_types=cache_types
            )
            
        except Exception as e:
            logger.error(f"Failed to get cache stats: {e}")
            return CacheStats(0, 0, 0.0, 0.0, 0.0, 0.0, {})
    
    async def health_check(self) -> Dict[str, Any]:
        """
        Perform cache health check.
        
        Returns:
            Health status and metrics
        """
        try:
            redis_client = await self._get_redis()
            
            # Test basic operations
            test_key = f"{self.key_prefix}:health_test"
            test_value = f"test_{int(time.time())}"
            
            # Test set/get/delete
            await redis_client.setex(test_key, 5, test_value)
            retrieved_value = await redis_client.get(test_key)
            await redis_client.delete(test_key)
            
            if retrieved_value != test_value:
                raise Exception("Cache read/write test failed")
            
            # Get cache statistics
            stats = await self.get_cache_stats()
            
            # Get Redis info
            info = await redis_client.info()
            
            return {
                'healthy': True,
                'redis_connected': True,
                'total_keys': stats.total_keys,
                'memory_usage': stats.total_memory,
                'hit_rate': f"{stats.hit_rate:.2f}%",
                'cache_types': stats.cache_types,
                'redis_version': info.get('redis_version', 'unknown'),
                'connected_clients': info.get('connected_clients', 0),
                'last_check': datetime.now(timezone.utc).isoformat()
            }
            
        except Exception as e:
            logger.error(f"Cache health check failed: {e}")
            return {
                'healthy': False,
                'error': str(e),
                'last_check': datetime.now(timezone.utc).isoformat()
            }
    
    async def cleanup_expired(self) -> int:
        """
        Manual cleanup of expired entries (Redis handles this automatically).
        
        Returns:
            Number of expired entries cleaned up
        """
        try:
            redis_client = await self._get_redis()
            
            cleaned_count = 0
            async for key in redis_client.scan_iter(match=f"{self.key_prefix}:*"):
                ttl = await redis_client.ttl(key)
                if ttl == -2:  # Key expired and was deleted
                    cleaned_count += 1
            
            if cleaned_count > 0:
                logger.info(f"[CACHE-CLEANUP] {cleaned_count} expired entries cleaned up")
                await self._update_stats('evictions', cleaned_count)
            
            return cleaned_count
            
        except Exception as e:
            logger.error(f"Failed to cleanup expired cache entries: {e}")
            return 0
    
    async def warm_cache(self, cache_types: List[CacheType] = None):
        """
        Warm cache with frequently accessed data.
        
        Args:
            cache_types: Optional list of cache types to warm (warms all if not specified)
        """
        if not self.warm_on_startup:
            return
        
        try:
            types_to_warm = cache_types or list(CacheType)
            
            logger.info(f"[CACHE-WARM] Starting cache warming for: {[t.value for t in types_to_warm]}")
            
            # This is a placeholder for cache warming logic
            # In a real implementation, you would:
            # 1. Load frequently accessed playlists
            # 2. Pre-cache popular tracks
            # 3. Load user preferences for active users
            # 4. etc.
            
            logger.info("[CACHE-WARM] Cache warming completed")
            
        except Exception as e:
            logger.error(f"Failed to warm cache: {e}")
    
    async def close(self):
        """Close Redis connection."""
        if self.redis_client:
            await self.redis_client.close()
            self.redis_client = None
            logger.info("Cache manager connection closed")


# Exception classes
class CacheConnectionError(Exception):
    """Raised when cache connection fails."""
    pass

class CacheSerializationError(Exception):
    """Raised when cache serialization fails."""
    pass

# Global cache manager instance
_cache_manager: Optional[CacheManager] = None

def get_cache_manager() -> CacheManager:
    """Get the global cache manager instance."""
    global _cache_manager
    if _cache_manager is None:
        _cache_manager = CacheManager()
    return _cache_manager

async def cleanup_cache_manager():
    """Cleanup the global cache manager."""
    global _cache_manager
    if _cache_manager:
        await _cache_manager.close()
        _cache_manager = None

@asynccontextmanager
async def cache_manager_lifespan():
    """Context manager for cache manager lifecycle."""
    cache_mgr = get_cache_manager()
    try:
        # Test connection
        await cache_mgr._get_redis()
        
        # Warm cache if enabled
        await cache_mgr.warm_cache()
        
        yield cache_mgr
    finally:
        await cache_mgr.close()

# Convenience functions for common cache operations
async def cache_playlist(user_id: str, playlist_id: str, playlist_data: Dict[str, Any], ttl: int = None) -> bool:
    """Cache playlist data."""
    cache_mgr = get_cache_manager()
    return await cache_mgr.set(CacheType.PLAYLIST, playlist_id, playlist_data, ttl, user_id)

async def get_cached_playlist(user_id: str, playlist_id: str) -> Optional[Dict[str, Any]]:
    """Get cached playlist data."""
    cache_mgr = get_cache_manager()
    return await cache_mgr.get(CacheType.PLAYLIST, playlist_id, user_id)

async def cache_track(track_id: str, track_data: Dict[str, Any], ttl: int = None) -> bool:
    """Cache track metadata."""
    cache_mgr = get_cache_manager()
    return await cache_mgr.set(CacheType.TRACK, track_id, track_data, ttl)

async def get_cached_track(track_id: str) -> Optional[Dict[str, Any]]:
    """Get cached track metadata."""
    cache_mgr = get_cache_manager()
    return await cache_mgr.get(CacheType.TRACK, track_id)

async def cache_user_data(user_id: str, user_data: Dict[str, Any], ttl: int = None) -> bool:
    """Cache user preferences and data."""
    cache_mgr = get_cache_manager()
    return await cache_mgr.set(CacheType.USER_DATA, "preferences", user_data, ttl, user_id)

async def get_cached_user_data(user_id: str) -> Optional[Dict[str, Any]]:
    """Get cached user preferences and data."""
    cache_mgr = get_cache_manager()
    return await cache_mgr.get(CacheType.USER_DATA, "preferences", user_id)

async def invalidate_user_cache(user_id: str) -> int:
    """Invalidate all cache for a user."""
    cache_mgr = get_cache_manager()
    return await cache_mgr.invalidate_user_cache(user_id)

async def get_cache_statistics() -> CacheStats:
    """Get cache performance statistics."""
    cache_mgr = get_cache_manager()
    return await cache_mgr.get_cache_stats()
