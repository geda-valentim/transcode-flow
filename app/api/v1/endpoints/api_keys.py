"""
API Key Management Endpoints
Provides comprehensive API key management for the Transcode Flow platform.
"""

from datetime import datetime, timezone, timedelta
from typing import List
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session
import secrets
import hashlib

from app.db import get_db
from app.core.security import get_api_key
from app.models.api_key import APIKey
from app.schemas.api_key_schemas import (
    APIKeyCreate, APIKeyResponse, APIKeyCreatedResponse,
    APIKeyRotateRequest, APIKeyUpdateScopes, APIKeyUpdateIPFilter,
    APIKeyUsageStats, SubKeyCreate
)

router = APIRouter(prefix="/api-keys", tags=["api-keys"])


def generate_api_key() -> tuple[str, str, str]:
    """Generate new API key with hash and prefix"""
    raw_key = secrets.token_urlsafe(32)
    full_key = f"tfk_{raw_key}"
    key_hash = hashlib.sha256(full_key.encode()).hexdigest()
    key_prefix = full_key[:12]
    return full_key, key_hash, key_prefix


@router.post("", response_model=APIKeyCreatedResponse, status_code=201)
async def create_api_key(data: APIKeyCreate, db: Session = Depends(get_db),
                        current_key: APIKey = Depends(get_api_key)):
    """Create new API key (master keys only)"""
    if not current_key.is_master_key:
        raise HTTPException(403, "Only master keys can create new keys")

    full_key, key_hash, key_prefix = generate_api_key()
    expires_at = datetime.now(timezone.utc) + timedelta(days=data.expires_in_days) if data.expires_in_days else None

    new_key = APIKey(
        key_hash=key_hash, key_prefix=key_prefix, name=data.name, email=data.email,
        organization=data.organization, is_active=True,
        permissions=data.permissions or {"can_upload": True, "can_transcode": True, "can_extract_audio": True, "can_transcribe": False, "max_resolution": "1080p"},
        scopes=data.scopes or ["jobs:create", "jobs:read", "jobs:list", "streaming:generate_token"],
        rate_limit_per_hour=data.rate_limit_per_hour, rate_limit_per_day=data.rate_limit_per_day,
        storage_quota_gb=data.storage_quota_gb, jobs_quota_monthly=data.jobs_quota_monthly,
        expires_at=expires_at, ip_whitelist=data.ip_whitelist, ip_blacklist=data.ip_blacklist,
        is_master_key=data.is_master_key, notes=data.notes, key_metadata=data.key_metadata
    )

    db.add(new_key)
    db.commit()
    db.refresh(new_key)

    response_data = APIKeyResponse.model_validate(new_key).model_dump()
    response_data["api_key"] = full_key
    return APIKeyCreatedResponse(**response_data)


@router.get("/{key_id}", response_model=APIKeyResponse)
async def get_api_key_details(key_id: int, db: Session = Depends(get_db),
                     current_key: APIKey = Depends(get_api_key)):
    """Get API key details"""
    api_key = db.query(APIKey).filter(APIKey.id == key_id).first()
    if not api_key:
        raise HTTPException(404, "API key not found")

    if api_key.id != current_key.id:
        if not current_key.is_master_key or api_key.parent_key_id != current_key.id:
            raise HTTPException(403, "Access denied")

    return APIKeyResponse.model_validate(api_key)


@router.get("", response_model=List[APIKeyResponse])
async def list_api_keys(include_inactive: bool = False, db: Session = Depends(get_db),
                       current_key: APIKey = Depends(get_api_key)):
    """List API keys (self + sub-keys for master keys)"""
    query = db.query(APIKey)

    if current_key.is_master_key:
        query = query.filter((APIKey.id == current_key.id) | (APIKey.parent_key_id == current_key.id))
    else:
        query = query.filter(APIKey.id == current_key.id)

    if not include_inactive:
        query = query.filter(APIKey.is_active == True)

    return [APIKeyResponse.model_validate(k) for k in query.order_by(APIKey.created_at.desc()).all()]


@router.post("/{key_id}/rotate", response_model=APIKeyCreatedResponse)
async def rotate_api_key(key_id: int, data: APIKeyRotateRequest, db: Session = Depends(get_db),
                        current_key: APIKey = Depends(get_api_key)):
    """Rotate API key with grace period"""
    old_key = db.query(APIKey).filter(APIKey.id == key_id).first()
    if not old_key:
        raise HTTPException(404, "API key not found")

    if old_key.id != current_key.id:
        if not current_key.is_master_key or old_key.parent_key_id != current_key.id:
            raise HTTPException(403, "Access denied")

    full_key, key_hash, key_prefix = generate_api_key()
    old_key_expires_at = datetime.now(timezone.utc) + timedelta(days=data.expires_old_key_in_days)
    new_key_rotation_at = datetime.now(timezone.utc) + timedelta(days=data.rotation_days) if data.schedule_rotation and data.rotation_days else None

    new_key = APIKey(
        key_hash=key_hash, key_prefix=key_prefix, name=f"{old_key.name} (Rotated)",
        email=old_key.email, organization=old_key.organization, is_active=True,
        permissions=old_key.permissions, scopes=old_key.scopes,
        rate_limit_per_hour=old_key.rate_limit_per_hour, rate_limit_per_day=old_key.rate_limit_per_day,
        storage_quota_gb=old_key.storage_quota_gb, jobs_quota_monthly=old_key.jobs_quota_monthly,
        expires_at=old_key.expires_at, ip_whitelist=old_key.ip_whitelist, ip_blacklist=old_key.ip_blacklist,
        is_master_key=old_key.is_master_key, parent_key_id=old_key.parent_key_id,
        rotated_from_key_id=old_key.id, rotation_scheduled_at=new_key_rotation_at,
        key_metadata=old_key.key_metadata, notes=f"Rotated from {old_key.key_prefix}"
    )

    old_key.expires_at = old_key_expires_at
    old_key.notes = f"{old_key.notes or ''}\nRotated on {datetime.now(timezone.utc).isoformat()}. Expires in {data.expires_old_key_in_days} days."

    db.add(new_key)
    db.commit()
    db.refresh(new_key)

    response_data = APIKeyResponse.model_validate(new_key).model_dump()
    response_data["api_key"] = full_key
    return APIKeyCreatedResponse(**response_data)


@router.patch("/{key_id}/scopes", response_model=APIKeyResponse)
async def update_api_key_scopes(key_id: int, data: APIKeyUpdateScopes, db: Session = Depends(get_db),
                               current_key: APIKey = Depends(get_api_key)):
    """Update API key scopes"""
    api_key = db.query(APIKey).filter(APIKey.id == key_id).first()
    if not api_key:
        raise HTTPException(404, "API key not found")

    if api_key.id != current_key.id:
        if not current_key.is_master_key or api_key.parent_key_id != current_key.id:
            raise HTTPException(403, "Access denied")

    if api_key.parent_key_id:
        parent_key = db.query(APIKey).filter(APIKey.id == api_key.parent_key_id).first()
        if parent_key and not set(data.scopes).issubset(set(parent_key.scopes or [])):
            raise HTTPException(400, f"Sub-key scopes must be subset of parent: {parent_key.scopes}")

    api_key.scopes = list(set(api_key.scopes or []).union(set(data.scopes))) if data.merge else data.scopes
    db.commit()
    db.refresh(api_key)
    return APIKeyResponse.model_validate(api_key)


@router.patch("/{key_id}/ip-filter", response_model=APIKeyResponse)
async def update_ip_filter(key_id: int, data: APIKeyUpdateIPFilter, db: Session = Depends(get_db),
                          current_key: APIKey = Depends(get_api_key)):
    """Update IP whitelist/blacklist"""
    api_key = db.query(APIKey).filter(APIKey.id == key_id).first()
    if not api_key:
        raise HTTPException(404, "API key not found")

    if api_key.id != current_key.id:
        if not current_key.is_master_key or api_key.parent_key_id != current_key.id:
            raise HTTPException(403, "Access denied")

    api_key.ip_whitelist = data.ip_whitelist
    api_key.ip_blacklist = data.ip_blacklist
    db.commit()
    db.refresh(api_key)
    return APIKeyResponse.model_validate(api_key)


@router.get("/{key_id}/analytics", response_model=APIKeyUsageStats)
async def get_api_key_analytics(key_id: int, db: Session = Depends(get_db),
                                current_key: APIKey = Depends(get_api_key)):
    """Get detailed usage analytics"""
    api_key = db.query(APIKey).filter(APIKey.id == key_id).first()
    if not api_key:
        raise HTTPException(404, "API key not found")

    if api_key.id != current_key.id:
        if not current_key.is_master_key or api_key.parent_key_id != current_key.id:
            raise HTTPException(403, "Access denied")

    storage_remaining_gb = ((api_key.storage_quota_gb * 1024 * 1024 * 1024) - api_key.storage_used_bytes) / (1024 * 1024 * 1024)
    days_since_last_use = (datetime.now(timezone.utc) - api_key.last_used_at).days if api_key.last_used_at else None
    days_until_expiration = (api_key.expires_at - datetime.now(timezone.utc)).days if api_key.expires_at else None

    return APIKeyUsageStats(
        key_id=api_key.id, key_prefix=api_key.key_prefix, name=api_key.name,
        total_requests=api_key.total_requests, requests_today=0, requests_this_hour=0,
        storage_used_bytes=api_key.storage_used_bytes, storage_quota_gb=api_key.storage_quota_gb,
        storage_usage_percent=api_key.storage_usage_percent, storage_remaining_gb=storage_remaining_gb,
        jobs_used_monthly=api_key.jobs_used_monthly, jobs_quota_monthly=api_key.jobs_quota_monthly,
        jobs_usage_percent=api_key.jobs_usage_percent, jobs_remaining=api_key.jobs_quota_monthly - api_key.jobs_used_monthly,
        rate_limit_per_hour=api_key.rate_limit_per_hour, rate_limit_per_day=api_key.rate_limit_per_day,
        rate_limit_status="healthy", last_used_at=api_key.last_used_at, days_since_last_use=days_since_last_use,
        expires_at=api_key.expires_at, days_until_expiration=days_until_expiration,
        is_expired=api_key.is_expired, needs_rotation=api_key.needs_rotation(),
        rotation_scheduled_at=api_key.rotation_scheduled_at
    )


@router.delete("/{key_id}", status_code=204)
async def revoke_api_key(key_id: int, permanent_delete: bool = False, db: Session = Depends(get_db),
                        current_key: APIKey = Depends(get_api_key)):
    """Revoke or permanently delete API key"""
    api_key = db.query(APIKey).filter(APIKey.id == key_id).first()
    if not api_key:
        raise HTTPException(404, "API key not found")

    if api_key.id == current_key.id:
        raise HTTPException(400, "Cannot revoke your own API key")

    if not current_key.is_master_key:
        raise HTTPException(403, "Only master keys can revoke keys")

    if api_key.parent_key_id != current_key.id and api_key.id != current_key.id:
        raise HTTPException(403, "Can only revoke your own sub-keys")

    if permanent_delete:
        db.delete(api_key)
    else:
        api_key.is_active = False
        api_key.notes = f"{api_key.notes or ''}\nRevoked on {datetime.now(timezone.utc).isoformat()}"

    db.commit()
    return Response(status_code=204)


@router.post("/{parent_key_id}/sub-keys", response_model=APIKeyCreatedResponse, status_code=201)
async def create_sub_key(parent_key_id: int, data: SubKeyCreate, db: Session = Depends(get_db),
                        current_key: APIKey = Depends(get_api_key)):
    """Create sub-key under master key"""
    parent_key = db.query(APIKey).filter(APIKey.id == parent_key_id).first()
    if not parent_key:
        raise HTTPException(404, "Parent API key not found")
    if not parent_key.is_master_key:
        raise HTTPException(400, "Parent key must be a master key")
    if parent_key.id != current_key.id:
        raise HTTPException(403, "Can only create sub-keys for your own master key")

    if not set(data.scopes).issubset(set(parent_key.scopes or [])):
        raise HTTPException(400, f"Sub-key scopes must be subset of parent: {parent_key.scopes}")

    full_key, key_hash, key_prefix = generate_api_key()
    expires_at = datetime.now(timezone.utc) + timedelta(days=data.expires_in_days)

    sub_key = APIKey(
        key_hash=key_hash, key_prefix=key_prefix, name=data.name,
        email=parent_key.email, organization=parent_key.organization, is_active=True,
        permissions=parent_key.permissions, scopes=data.scopes,
        rate_limit_per_hour=parent_key.rate_limit_per_hour // 2, rate_limit_per_day=parent_key.rate_limit_per_day // 2,
        storage_quota_gb=parent_key.storage_quota_gb // 2, jobs_quota_monthly=parent_key.jobs_quota_monthly // 2,
        expires_at=expires_at, ip_whitelist=data.ip_whitelist or parent_key.ip_whitelist,
        ip_blacklist=parent_key.ip_blacklist, is_master_key=False, parent_key_id=parent_key.id, notes=data.notes
    )

    db.add(sub_key)
    db.commit()
    db.refresh(sub_key)

    response_data = APIKeyResponse.model_validate(sub_key).model_dump()
    response_data["api_key"] = full_key
    return APIKeyCreatedResponse(**response_data)


@router.get("/{parent_key_id}/sub-keys", response_model=List[APIKeyResponse])
async def list_sub_keys(parent_key_id: int, include_inactive: bool = False, db: Session = Depends(get_db),
                       current_key: APIKey = Depends(get_api_key)):
    """List all sub-keys for a master key"""
    parent_key = db.query(APIKey).filter(APIKey.id == parent_key_id).first()
    if not parent_key:
        raise HTTPException(404, "Parent API key not found")
    if parent_key.id != current_key.id:
        raise HTTPException(403, "Can only list sub-keys for your own master key")

    query = db.query(APIKey).filter(APIKey.parent_key_id == parent_key_id)
    if not include_inactive:
        query = query.filter(APIKey.is_active == True)

    return [APIKeyResponse.model_validate(k) for k in query.order_by(APIKey.created_at.desc()).all()]
