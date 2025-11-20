"""
Security module for API key authentication and authorization.
"""
import hashlib
import secrets
from typing import Optional
from fastapi import HTTPException, Security, status, Depends
from fastapi.security import APIKeyHeader
from sqlalchemy.orm import Session

from app.models.api_key import APIKey
from app.db import get_db

# API Key header scheme
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=True)


def generate_api_key() -> tuple[str, str, str]:
    """
    Generate a new API key.

    Returns:
        tuple: (full_key, key_hash, key_prefix)
            - full_key: The complete API key to give to the user (show only once)
            - key_hash: SHA256 hash to store in database
            - key_prefix: First 8 characters for identification
    """
    # Generate a secure random key (32 bytes = 64 hex chars)
    full_key = secrets.token_urlsafe(32)

    # Create hash for database storage
    key_hash = hash_api_key(full_key)

    # Get prefix for display/identification (first 8 chars)
    key_prefix = full_key[:8]

    return full_key, key_hash, key_prefix


def hash_api_key(api_key: str) -> str:
    """
    Hash an API key using SHA256.

    Args:
        api_key: The plain text API key

    Returns:
        str: Hexadecimal hash of the API key
    """
    return hashlib.sha256(api_key.encode()).hexdigest()


def verify_api_key(db: Session, api_key: str) -> Optional[APIKey]:
    """
    Verify an API key and return the associated APIKey object.

    Args:
        db: Database session
        api_key: The API key to verify

    Returns:
        APIKey object if valid, None otherwise
    """
    if not api_key:
        return None

    # Hash the provided key
    key_hash = hash_api_key(api_key)

    # Query database for matching key
    api_key_obj = db.query(APIKey).filter(
        APIKey.key_hash == key_hash,
        APIKey.is_active == True
    ).first()

    if not api_key_obj:
        return None

    # Check if key is expired
    if api_key_obj.is_expired:
        return None

    # Update last_used_at
    from datetime import datetime, timezone
    api_key_obj.last_used_at = datetime.now(timezone.utc)
    api_key_obj.total_requests += 1
    db.commit()

    return api_key_obj


async def get_api_key(
    api_key_header: str = Security(api_key_header),
    db: Session = Depends(get_db)
) -> APIKey:
    """
    FastAPI dependency for API key authentication.

    Usage in endpoints:
        @app.get("/protected")
        def protected_route(api_key: APIKey = Depends(get_api_key)):
            return {"message": f"Hello {api_key.name}"}

    Args:
        api_key_header: API key from request header
        db: Database session

    Returns:
        APIKey: Valid API key object

    Raises:
        HTTPException: If API key is invalid or missing
    """
    api_key_obj = verify_api_key(db, api_key_header)

    if not api_key_obj:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    return api_key_obj


def check_permission(api_key: APIKey, permission: str) -> bool:
    """
    Check if an API key has a specific permission.

    Args:
        api_key: APIKey object
        permission: Permission name (e.g., "can_upload", "can_transcribe")

    Returns:
        bool: True if permission exists and is True

    Raises:
        HTTPException: If permission is denied
    """
    has_perm = api_key.has_permission(permission)

    if not has_perm:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Permission denied: {permission} not granted for this API key",
        )

    return True


def check_storage_quota(api_key: APIKey, required_bytes: int) -> bool:
    """
    Check if API key has sufficient storage quota.

    Args:
        api_key: APIKey object
        required_bytes: Bytes needed for the operation

    Returns:
        bool: True if quota is available

    Raises:
        HTTPException: If quota is exceeded
    """
    if not api_key.has_storage_quota(required_bytes):
        quota_gb = api_key.storage_quota_gb
        used_gb = api_key.storage_used_bytes / (1024 ** 3)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Storage quota exceeded. Used: {used_gb:.2f}GB / {quota_gb}GB",
        )

    return True


def check_jobs_quota(api_key: APIKey) -> bool:
    """
    Check if API key has remaining jobs quota.

    Args:
        api_key: APIKey object

    Returns:
        bool: True if quota is available

    Raises:
        HTTPException: If quota is exceeded
    """
    if not api_key.has_jobs_quota():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Monthly jobs quota exceeded. "
                   f"Used: {api_key.jobs_used_monthly} / {api_key.jobs_quota_monthly}",
        )

    return True


def increment_jobs_usage(db: Session, api_key: APIKey) -> None:
    """
    Increment the monthly jobs counter for an API key.

    Args:
        db: Database session
        api_key: APIKey object
    """
    api_key.jobs_used_monthly += 1
    db.commit()


def increment_storage_usage(db: Session, api_key: APIKey, bytes_used: int) -> None:
    """
    Increment the storage usage counter for an API key.

    Args:
        db: Database session
        api_key: APIKey object
        bytes_used: Number of bytes to add to usage
    """
    api_key.storage_used_bytes += bytes_used
    db.commit()
