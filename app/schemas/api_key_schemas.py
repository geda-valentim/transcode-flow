"""
API Key Management Schemas

Pydantic models for API key management requests and responses.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, EmailStr


class APIKeyCreate(BaseModel):
    """Request body for creating a new API key"""
    name: str = Field(..., min_length=1, max_length=255)
    email: Optional[EmailStr] = None
    organization: Optional[str] = Field(None, max_length=255)
    permissions: Optional[Dict[str, Any]] = None
    scopes: Optional[List[str]] = None
    rate_limit_per_hour: int = Field(100, ge=1, le=10000)
    rate_limit_per_day: int = Field(1000, ge=1, le=100000)
    storage_quota_gb: int = Field(100, ge=1, le=10000)
    jobs_quota_monthly: int = Field(1000, ge=1, le=100000)
    expires_in_days: Optional[int] = Field(None, ge=1, le=3650)
    ip_whitelist: Optional[List[str]] = None
    ip_blacklist: Optional[List[str]] = None
    is_master_key: bool = False
    notes: Optional[str] = Field(None, max_length=2048)
    key_metadata: Optional[Dict[str, Any]] = None


class APIKeyResponse(BaseModel):
    """Response containing API key details"""
    id: int
    key_prefix: str
    name: str
    email: Optional[str]
    organization: Optional[str]
    is_active: bool
    is_master_key: bool
    permissions: Dict[str, Any]
    scopes: List[str]
    rate_limit_per_hour: int
    rate_limit_per_day: int
    storage_quota_gb: int
    storage_used_bytes: int
    storage_usage_percent: float
    jobs_quota_monthly: int
    jobs_used_monthly: int
    jobs_usage_percent: float
    total_requests: int
    last_used_at: Optional[datetime]
    expires_at: Optional[datetime]
    is_expired: bool
    is_valid: bool
    ip_whitelist: Optional[List[str]]
    ip_blacklist: Optional[List[str]]
    parent_key_id: Optional[int]
    rotated_from_key_id: Optional[int]
    rotation_scheduled_at: Optional[datetime]
    notes: Optional[str]
    key_metadata: Optional[Dict[str, Any]]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class APIKeyCreatedResponse(APIKeyResponse):
    """Response when a new API key is created (includes the full key)"""
    api_key: str = Field(..., description="The full API key (only shown once)")


class APIKeyRotateRequest(BaseModel):
    """Request body for rotating an API key"""
    expires_old_key_in_days: int = Field(30, ge=1, le=365)
    schedule_rotation: bool = False
    rotation_days: Optional[int] = Field(None, ge=30, le=365)


class APIKeyUpdateScopes(BaseModel):
    """Request body for updating API key scopes"""
    scopes: List[str]
    merge: bool = False


class APIKeyUpdateIPFilter(BaseModel):
    """Request body for updating IP filtering"""
    ip_whitelist: Optional[List[str]] = None
    ip_blacklist: Optional[List[str]] = None


class APIKeyUsageStats(BaseModel):
    """Detailed usage statistics for an API key"""
    key_id: int
    key_prefix: str
    name: str
    total_requests: int
    requests_today: int
    requests_this_hour: int
    storage_used_bytes: int
    storage_quota_gb: int
    storage_usage_percent: float
    storage_remaining_gb: float
    jobs_used_monthly: int
    jobs_quota_monthly: int
    jobs_usage_percent: float
    jobs_remaining: int
    rate_limit_per_hour: int
    rate_limit_per_day: int
    rate_limit_status: str
    last_used_at: Optional[datetime]
    days_since_last_use: Optional[int]
    expires_at: Optional[datetime]
    days_until_expiration: Optional[int]
    is_expired: bool
    needs_rotation: bool
    rotation_scheduled_at: Optional[datetime]


class SubKeyCreate(BaseModel):
    """Request body for creating a sub-key"""
    name: str = Field(..., min_length=1, max_length=255)
    scopes: List[str]
    expires_in_days: Optional[int] = Field(90, ge=1, le=365)
    ip_whitelist: Optional[List[str]] = None
    notes: Optional[str] = Field(None, max_length=2048)
