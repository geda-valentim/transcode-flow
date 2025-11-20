"""
Streaming Token Service

Generates secure, time-limited tokens for HLS video streaming.
Tokens are JWT-based with job_id, expiration, and optional IP restrictions.
"""

from jose import jwt
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from redis import Redis

from app.core.config import settings
from app.models.job import Job


class StreamingTokenService:
    """
    Service for generating and validating secure streaming tokens.

    Features:
    - JWT-based tokens with expiration
    - Per-job access control
    - Optional IP whitelisting
    - Token revocation via Redis blacklist
    - Configurable expiration times
    """

    def __init__(
        self,
        secret_key: str = settings.SECRET_KEY,
        algorithm: str = "HS256",
        redis_client: Optional[Redis] = None
    ):
        """
        Initialize the streaming token service.

        Args:
            secret_key: Secret key for JWT signing
            algorithm: JWT algorithm (default: HS256)
            redis_client: Redis client for token blacklist
        """
        self.secret_key = secret_key
        self.algorithm = algorithm
        self.redis_client = redis_client

    def generate_token(
        self,
        job_id: str,
        api_key_prefix: str,
        expires_in_seconds: int = 3600,
        allowed_ips: Optional[list[str]] = None,
        max_uses: Optional[int] = None
    ) -> str:
        """
        Generate a streaming token for a specific job.

        Args:
            job_id: The job ID to grant access to
            api_key_prefix: API key prefix for tracking
            expires_in_seconds: Token expiration time (default: 1 hour)
            allowed_ips: Optional list of allowed IP addresses
            max_uses: Optional maximum number of times token can be used

        Returns:
            JWT token string

        Example:
            >>> service = StreamingTokenService()
            >>> token = service.generate_token(
            ...     job_id="job_abc123",
            ...     api_key_prefix="sk-1234",
            ...     expires_in_seconds=7200,
            ...     allowed_ips=["192.168.1.100"]
            ... )
        """
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=expires_in_seconds)

        # Generate unique token ID for revocation
        token_id = secrets.token_urlsafe(16)

        payload: Dict[str, Any] = {
            "jti": token_id,  # JWT ID for revocation
            "job_id": job_id,
            "api_key_prefix": api_key_prefix,
            "iat": int(now.timestamp()),  # Issued at
            "exp": int(expires_at.timestamp()),  # Expiration
            "type": "streaming",
        }

        # Add optional claims
        if allowed_ips:
            payload["allowed_ips"] = allowed_ips

        if max_uses:
            payload["max_uses"] = max_uses

        # Generate JWT token
        token = jwt.encode(payload, self.secret_key, algorithm=self.algorithm)

        # Store in Redis for usage tracking if max_uses is set
        if max_uses and self.redis_client:
            redis_key = f"stream_token_uses:{token_id}"
            self.redis_client.setex(
                redis_key,
                expires_in_seconds,
                0  # Initial use count
            )

        return token

    def validate_token(
        self,
        token: str,
        job_id: str,
        client_ip: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Validate a streaming token.

        Args:
            token: JWT token to validate
            job_id: Expected job ID
            client_ip: Client's IP address for IP restriction check

        Returns:
            Dictionary with validation result and token payload

        Raises:
            jwt.ExpiredSignatureError: If token is expired
            jwt.InvalidTokenError: If token is invalid

        Example:
            >>> result = service.validate_token(
            ...     token="eyJ0eXAiOiJKV1QiLC...",
            ...     job_id="job_abc123",
            ...     client_ip="192.168.1.100"
            ... )
            >>> if result["valid"]:
            ...     print("Token is valid!")
        """
        try:
            # Decode and verify token
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm]
            )

            # Verify token type
            if payload.get("type") != "streaming":
                return {
                    "valid": False,
                    "error": "invalid_token_type",
                    "message": "Token is not a streaming token"
                }

            # Verify job_id matches
            if payload.get("job_id") != job_id:
                return {
                    "valid": False,
                    "error": "job_id_mismatch",
                    "message": "Token is not valid for this job"
                }

            # Check if token is blacklisted
            token_id = payload.get("jti")
            if token_id and self.redis_client:
                if self.redis_client.exists(f"stream_token_blacklist:{token_id}"):
                    return {
                        "valid": False,
                        "error": "token_revoked",
                        "message": "Token has been revoked"
                    }

            # Verify IP restrictions if specified
            allowed_ips = payload.get("allowed_ips")
            if allowed_ips and client_ip:
                if client_ip not in allowed_ips:
                    return {
                        "valid": False,
                        "error": "ip_not_allowed",
                        "message": f"IP address {client_ip} not allowed for this token"
                    }

            # Check and increment usage count if max_uses is set
            max_uses = payload.get("max_uses")
            if max_uses and token_id and self.redis_client:
                redis_key = f"stream_token_uses:{token_id}"
                current_uses = int(self.redis_client.get(redis_key) or 0)

                if current_uses >= max_uses:
                    return {
                        "valid": False,
                        "error": "max_uses_exceeded",
                        "message": f"Token has exceeded maximum uses ({max_uses})"
                    }

                # Increment use count
                self.redis_client.incr(redis_key)

            return {
                "valid": True,
                "payload": payload,
                "job_id": payload["job_id"],
                "api_key_prefix": payload.get("api_key_prefix"),
            }

        except jwt.ExpiredSignatureError:
            return {
                "valid": False,
                "error": "token_expired",
                "message": "Token has expired"
            }
        except jwt.InvalidTokenError as e:
            return {
                "valid": False,
                "error": "invalid_token",
                "message": f"Invalid token: {str(e)}"
            }

    def revoke_token(self, token: str) -> bool:
        """
        Revoke a streaming token by adding it to the blacklist.

        Args:
            token: JWT token to revoke

        Returns:
            True if token was revoked, False otherwise

        Example:
            >>> service.revoke_token("eyJ0eXAiOiJKV1QiLC...")
            True
        """
        if not self.redis_client:
            raise RuntimeError("Redis client is required for token revocation")

        try:
            # Decode token to get token_id and expiration
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm]
            )

            token_id = payload.get("jti")
            exp = payload.get("exp")

            if not token_id or not exp:
                return False

            # Calculate remaining TTL
            now = datetime.now(timezone.utc)
            exp_time = datetime.fromtimestamp(exp, tz=timezone.utc)
            ttl_seconds = int((exp_time - now).total_seconds())

            if ttl_seconds <= 0:
                return False  # Token already expired

            # Add to blacklist with TTL
            redis_key = f"stream_token_blacklist:{token_id}"
            self.redis_client.setex(redis_key, ttl_seconds, "1")

            return True

        except jwt.InvalidTokenError:
            return False

    def revoke_all_job_tokens(self, job_id: str) -> None:
        """
        Revoke all streaming tokens for a specific job.

        This is useful when a job is deleted or access should be removed.
        Implemented by blacklisting the job_id pattern.

        Args:
            job_id: Job ID to revoke all tokens for

        Note:
            This adds the job_id to a blacklist. The validate_token method
            must check this blacklist in addition to individual token revocation.
        """
        if not self.redis_client:
            raise RuntimeError("Redis client is required for token revocation")

        # Add job_id to blacklist for 24 hours (longer than max token life)
        redis_key = f"stream_job_blacklist:{job_id}"
        self.redis_client.setex(redis_key, 86400, "1")

    def generate_streaming_url(
        self,
        job_id: str,
        resolution: str,
        api_key_prefix: str,
        base_url: str = "https://yourdomain.com",
        expires_in_seconds: int = 3600,
        allowed_ips: Optional[list[str]] = None
    ) -> Dict[str, str]:
        """
        Generate a complete streaming URL with token for a specific resolution.

        Args:
            job_id: Job ID
            resolution: Video resolution (e.g., "720p", "1080p")
            api_key_prefix: API key prefix for tracking
            base_url: Base URL for streaming endpoint
            expires_in_seconds: Token expiration time
            allowed_ips: Optional list of allowed IPs

        Returns:
            Dictionary with streaming URLs and token info

        Example:
            >>> urls = service.generate_streaming_url(
            ...     job_id="job_abc123",
            ...     resolution="720p",
            ...     api_key_prefix="sk-1234"
            ... )
            >>> print(urls["hls_url"])
            https://yourdomain.com/stream/TOKEN/job_abc123/720p/playlist.m3u8
        """
        # Generate token
        token = self.generate_token(
            job_id=job_id,
            api_key_prefix=api_key_prefix,
            expires_in_seconds=expires_in_seconds,
            allowed_ips=allowed_ips
        )

        # Construct streaming URLs
        path_prefix = f"{job_id}/{resolution}"

        return {
            "token": token,
            "hls_url": f"{base_url}/stream/{token}/{path_prefix}/playlist.m3u8",
            "expires_at": (
                datetime.now(timezone.utc) + timedelta(seconds=expires_in_seconds)
            ).isoformat(),
            "expires_in_seconds": expires_in_seconds,
            "job_id": job_id,
            "resolution": resolution,
        }

    def verify_job_access(
        self,
        db: Session,
        job_id: str,
        api_key_prefix: str
    ) -> bool:
        """
        Verify that an API key has access to a specific job.

        Args:
            db: Database session
            job_id: Job ID to check access for
            api_key_prefix: API key prefix

        Returns:
            True if API key has access to job, False otherwise
        """
        job = db.query(Job).filter(Job.id == job_id).first()

        if not job:
            return False

        # Check if job belongs to the same API key
        if job.api_key_prefix != api_key_prefix:
            return False

        # Check job status (only allow streaming for completed jobs)
        if job.status != "completed":
            return False

        return True


# Singleton instance
_streaming_token_service: Optional[StreamingTokenService] = None


def get_streaming_token_service() -> StreamingTokenService:
    """
    Get the singleton StreamingTokenService instance.

    Returns:
        StreamingTokenService instance
    """
    global _streaming_token_service

    if _streaming_token_service is None:
        # Try to initialize with Redis if available
        try:
            from app.core.cache import get_redis_client
            redis_client = get_redis_client()
            _streaming_token_service = StreamingTokenService(redis_client=redis_client)
        except Exception:
            # Fall back to service without Redis
            _streaming_token_service = StreamingTokenService()

    return _streaming_token_service
