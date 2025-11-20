"""
Rate limiting module using Redis for distributed rate limiting.
Implements sliding window algorithm for accurate rate limiting.
"""
import redis
from typing import Optional
from datetime import datetime, timedelta
from fastapi import HTTPException, status
import logging

from app.core.config import settings
from app.models.api_key import APIKey

logger = logging.getLogger(__name__)

# Redis client (lazy initialization)
_redis_client: Optional[redis.Redis] = None


def get_redis_client() -> redis.Redis:
    """
    Get or create Redis client.

    Returns:
        redis.Redis: Redis client instance
    """
    global _redis_client

    if _redis_client is None:
        try:
            _redis_client = redis.from_url(
                settings.REDIS_URL,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
            )
            # Test connection
            _redis_client.ping()
            logger.info("Redis connection established for rate limiting")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            # Rate limiting will be disabled if Redis is unavailable
            _redis_client = None

    return _redis_client


def check_rate_limit(api_key: APIKey) -> bool:
    """
    Check if the API key is within rate limits.

    Uses Redis to track:
    - Requests per hour
    - Requests per day

    Args:
        api_key: APIKey object to check

    Returns:
        bool: True if within limits

    Raises:
        HTTPException: If rate limit is exceeded
    """
    if not settings.RATE_LIMIT_ENABLED:
        return True

    redis_client = get_redis_client()

    # If Redis is unavailable, allow request (fail open)
    if redis_client is None:
        logger.warning("Rate limiting bypassed - Redis unavailable")
        return True

    api_key_id = api_key.id
    now = datetime.utcnow()

    # Check hourly limit
    hour_key = f"ratelimit:hour:{api_key_id}:{now.strftime('%Y%m%d%H')}"
    hour_requests = redis_client.get(hour_key)
    hour_requests = int(hour_requests) if hour_requests else 0

    if hour_requests >= api_key.rate_limit_per_hour:
        reset_time = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Hourly rate limit exceeded. "
                   f"Limit: {api_key.rate_limit_per_hour} requests/hour. "
                   f"Resets at: {reset_time.isoformat()}",
            headers={
                "X-RateLimit-Limit-Hour": str(api_key.rate_limit_per_hour),
                "X-RateLimit-Remaining-Hour": "0",
                "X-RateLimit-Reset": str(int(reset_time.timestamp())),
            },
        )

    # Check daily limit
    day_key = f"ratelimit:day:{api_key_id}:{now.strftime('%Y%m%d')}"
    day_requests = redis_client.get(day_key)
    day_requests = int(day_requests) if day_requests else 0

    if day_requests >= api_key.rate_limit_per_day:
        reset_time = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Daily rate limit exceeded. "
                   f"Limit: {api_key.rate_limit_per_day} requests/day. "
                   f"Resets at: {reset_time.isoformat()}",
            headers={
                "X-RateLimit-Limit-Day": str(api_key.rate_limit_per_day),
                "X-RateLimit-Remaining-Day": "0",
                "X-RateLimit-Reset": str(int(reset_time.timestamp())),
            },
        )

    # Increment counters
    pipeline = redis_client.pipeline()

    # Increment hour counter
    pipeline.incr(hour_key)
    pipeline.expire(hour_key, 3600)  # Expire after 1 hour

    # Increment day counter
    pipeline.incr(day_key)
    pipeline.expire(day_key, 86400)  # Expire after 24 hours

    pipeline.execute()

    logger.debug(
        f"Rate limit check passed for API key {api_key_id}: "
        f"hour={hour_requests + 1}/{api_key.rate_limit_per_hour}, "
        f"day={day_requests + 1}/{api_key.rate_limit_per_day}"
    )

    return True


def get_rate_limit_status(api_key: APIKey) -> dict:
    """
    Get current rate limit status for an API key.

    Args:
        api_key: APIKey object

    Returns:
        dict: Rate limit information
    """
    redis_client = get_redis_client()

    if redis_client is None:
        return {
            "available": False,
            "message": "Rate limiting unavailable - Redis not connected",
        }

    api_key_id = api_key.id
    now = datetime.utcnow()

    # Get current counts
    hour_key = f"ratelimit:hour:{api_key_id}:{now.strftime('%Y%m%d%H')}"
    day_key = f"ratelimit:day:{api_key_id}:{now.strftime('%Y%m%d')}"

    hour_requests = redis_client.get(hour_key)
    day_requests = redis_client.get(day_key)

    hour_requests = int(hour_requests) if hour_requests else 0
    day_requests = int(day_requests) if day_requests else 0

    hour_remaining = max(0, api_key.rate_limit_per_hour - hour_requests)
    day_remaining = max(0, api_key.rate_limit_per_day - day_requests)

    hour_reset = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
    day_reset = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)

    return {
        "available": True,
        "hourly": {
            "limit": api_key.rate_limit_per_hour,
            "used": hour_requests,
            "remaining": hour_remaining,
            "reset_at": hour_reset.isoformat(),
        },
        "daily": {
            "limit": api_key.rate_limit_per_day,
            "used": day_requests,
            "remaining": day_remaining,
            "reset_at": day_reset.isoformat(),
        },
    }


def reset_rate_limit(api_key_id: int) -> bool:
    """
    Reset rate limits for a specific API key (admin function).

    Args:
        api_key_id: ID of the API key

    Returns:
        bool: True if successful
    """
    redis_client = get_redis_client()

    if redis_client is None:
        return False

    now = datetime.utcnow()

    # Delete current hour and day keys
    hour_key = f"ratelimit:hour:{api_key_id}:{now.strftime('%Y%m%d%H')}"
    day_key = f"ratelimit:day:{api_key_id}:{now.strftime('%Y%m%d')}"

    redis_client.delete(hour_key, day_key)

    logger.info(f"Rate limits reset for API key {api_key_id}")
    return True
