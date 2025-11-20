"""
Redis caching layer for Transcode Flow.
Provides caching for frequently accessed data to reduce database load.
"""
import json
import hashlib
from typing import Optional, Any, Callable
from functools import wraps
import redis
from datetime import timedelta


class CacheManager:
    """Manages Redis caching for the application."""

    def __init__(self, redis_client: redis.Redis, default_ttl: int = 300):
        """
        Initialize cache manager.

        Args:
            redis_client: Redis client instance
            default_ttl: Default TTL in seconds (5 minutes)
        """
        self.redis = redis_client
        self.default_ttl = default_ttl
        self.prefix = "transcode_flow:"

    def _make_key(self, namespace: str, key: str) -> str:
        """Generate cache key with namespace."""
        return f"{self.prefix}{namespace}:{key}"

    def get(self, namespace: str, key: str) -> Optional[Any]:
        """
        Get value from cache.

        Args:
            namespace: Cache namespace (e.g., 'jobs', 'api_keys')
            key: Cache key

        Returns:
            Cached value or None if not found
        """
        try:
            cache_key = self._make_key(namespace, key)
            value = self.redis.get(cache_key)

            if value is None:
                return None

            # Deserialize JSON
            return json.loads(value)
        except (redis.RedisError, json.JSONDecodeError) as e:
            print(f"Cache get error: {e}")
            return None

    def set(
        self,
        namespace: str,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
    ) -> bool:
        """
        Set value in cache.

        Args:
            namespace: Cache namespace
            key: Cache key
            value: Value to cache (must be JSON serializable)
            ttl: Time to live in seconds (None uses default)

        Returns:
            True if successful, False otherwise
        """
        try:
            cache_key = self._make_key(namespace, key)
            serialized = json.dumps(value)
            ttl_seconds = ttl or self.default_ttl

            self.redis.setex(cache_key, ttl_seconds, serialized)
            return True
        except (redis.RedisError, TypeError, json.JSONEncodeError) as e:
            print(f"Cache set error: {e}")
            return False

    def delete(self, namespace: str, key: str) -> bool:
        """Delete value from cache."""
        try:
            cache_key = self._make_key(namespace, key)
            self.redis.delete(cache_key)
            return True
        except redis.RedisError as e:
            print(f"Cache delete error: {e}")
            return False

    def invalidate_pattern(self, pattern: str) -> int:
        """
        Invalidate all keys matching pattern.

        Args:
            pattern: Pattern to match (e.g., 'jobs:*')

        Returns:
            Number of keys deleted
        """
        try:
            full_pattern = f"{self.prefix}{pattern}"
            keys = self.redis.keys(full_pattern)

            if not keys:
                return 0

            return self.redis.delete(*keys)
        except redis.RedisError as e:
            print(f"Cache invalidate error: {e}")
            return 0

    def exists(self, namespace: str, key: str) -> bool:
        """Check if key exists in cache."""
        try:
            cache_key = self._make_key(namespace, key)
            return bool(self.redis.exists(cache_key))
        except redis.RedisError:
            return False

    def increment(self, namespace: str, key: str, amount: int = 1) -> Optional[int]:
        """Increment counter in cache."""
        try:
            cache_key = self._make_key(namespace, key)
            return self.redis.incrby(cache_key, amount)
        except redis.RedisError as e:
            print(f"Cache increment error: {e}")
            return None

    def get_many(self, namespace: str, keys: list[str]) -> dict[str, Any]:
        """Get multiple values from cache."""
        result = {}
        for key in keys:
            value = self.get(namespace, key)
            if value is not None:
                result[key] = value
        return result

    def set_many(
        self,
        namespace: str,
        mapping: dict[str, Any],
        ttl: Optional[int] = None,
    ) -> bool:
        """Set multiple values in cache."""
        try:
            for key, value in mapping.items():
                self.set(namespace, key, value, ttl)
            return True
        except Exception as e:
            print(f"Cache set_many error: {e}")
            return False


def cached(
    namespace: str,
    key_func: Optional[Callable] = None,
    ttl: int = 300,
):
    """
    Decorator for caching function results.

    Args:
        namespace: Cache namespace
        key_func: Function to generate cache key from args
        ttl: TTL in seconds

    Example:
        @cached('jobs', lambda job_id: f'job_{job_id}', ttl=600)
        def get_job(job_id: str):
            return db.query(Job).filter(Job.id == job_id).first()
    """

    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Get cache manager from kwargs or create new one
            cache = kwargs.get("cache")
            if not cache or not isinstance(cache, CacheManager):
                # No cache available, call function directly
                return func(*args, **kwargs)

            # Generate cache key
            if key_func:
                cache_key = key_func(*args, **kwargs)
            else:
                # Default: hash all args
                key_str = f"{func.__name__}:{str(args)}:{str(kwargs)}"
                cache_key = hashlib.md5(key_str.encode()).hexdigest()

            # Try to get from cache
            cached_value = cache.get(namespace, cache_key)
            if cached_value is not None:
                return cached_value

            # Call function and cache result
            result = func(*args, **kwargs)

            # Only cache if result is not None
            if result is not None:
                cache.set(namespace, cache_key, result, ttl)

            return result

        return wrapper

    return decorator


# Specific cache utilities for common operations


class JobCache:
    """Cache utilities for job operations."""

    def __init__(self, cache: CacheManager):
        self.cache = cache
        self.namespace = "jobs"

    def get_job(self, job_id: str) -> Optional[dict]:
        """Get job from cache."""
        return self.cache.get(self.namespace, job_id)

    def set_job(self, job_id: str, job_data: dict, ttl: int = 600):
        """Cache job data."""
        return self.cache.set(self.namespace, job_id, job_data, ttl)

    def invalidate_job(self, job_id: str):
        """Invalidate job cache."""
        return self.cache.delete(self.namespace, job_id)

    def invalidate_user_jobs(self, api_key_prefix: str):
        """Invalidate all jobs for a user."""
        return self.cache.invalidate_pattern(f"{self.namespace}:user:{api_key_prefix}:*")


class APIKeyCache:
    """Cache utilities for API key operations."""

    def __init__(self, cache: CacheManager):
        self.cache = cache
        self.namespace = "api_keys"

    def get_key_by_hash(self, key_hash: str) -> Optional[dict]:
        """Get API key by hash from cache."""
        return self.cache.get(self.namespace, f"hash:{key_hash}")

    def set_key(self, key_hash: str, key_data: dict, ttl: int = 1800):
        """Cache API key data (30 min TTL)."""
        return self.cache.set(self.namespace, f"hash:{key_hash}", key_data, ttl)

    def invalidate_key(self, key_hash: str):
        """Invalidate API key cache."""
        self.cache.delete(self.namespace, f"hash:{key_hash}")

    def get_rate_limit(self, key_prefix: str) -> Optional[dict]:
        """Get rate limit counters from cache."""
        return self.cache.get("rate_limit", key_prefix)

    def increment_requests(self, key_prefix: str, period: str) -> Optional[int]:
        """Increment request counter."""
        return self.cache.increment("rate_limit", f"{key_prefix}:{period}")


class StreamingTokenCache:
    """Cache utilities for streaming tokens."""

    def __init__(self, cache: CacheManager):
        self.cache = cache
        self.namespace = "streaming_tokens"

    def is_blacklisted(self, token_id: str) -> bool:
        """Check if token is blacklisted."""
        return self.cache.exists(self.namespace, f"blacklist:{token_id}")

    def blacklist_token(self, token_id: str, ttl: int):
        """Add token to blacklist."""
        return self.cache.set(self.namespace, f"blacklist:{token_id}", True, ttl)

    def get_usage_count(self, token_id: str) -> int:
        """Get token usage count."""
        count = self.cache.get(self.namespace, f"usage:{token_id}")
        return int(count) if count is not None else 0

    def increment_usage(self, token_id: str) -> Optional[int]:
        """Increment token usage counter."""
        return self.cache.increment(self.namespace, f"usage:{token_id}")


# Global cache instance (initialized in app startup)
_cache_manager: Optional[CacheManager] = None


def get_cache_manager() -> Optional[CacheManager]:
    """Get global cache manager instance."""
    return _cache_manager


def init_cache_manager(redis_client: redis.Redis, default_ttl: int = 300):
    """Initialize global cache manager."""
    global _cache_manager
    _cache_manager = CacheManager(redis_client, default_ttl)
    return _cache_manager
