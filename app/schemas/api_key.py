"""
Pydantic schemas for API key-related requests and responses.
"""
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field, EmailStr
from datetime import datetime


class APIKeyPermissions(BaseModel):
    """Schema for API key permissions."""
    can_upload: bool = True
    can_transcode: bool = True
    can_extract_audio: bool = True
    can_transcribe: bool = False
    max_resolution: str = Field(
        default="1080p",
        description="Maximum allowed resolution"
    )


class APIKeyCreate(BaseModel):
    """Schema for creating a new API key."""
    name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Descriptive name for the API key"
    )
    email: Optional[EmailStr] = Field(
        default=None,
        description="Contact email for the API key owner"
    )
    organization: Optional[str] = Field(
        default=None,
        max_length=255,
        description="Organization name"
    )
    permissions: Optional[APIKeyPermissions] = Field(
        default_factory=APIKeyPermissions,
        description="API key permissions"
    )
    rate_limit_per_hour: int = Field(
        default=100,
        ge=1,
        le=10000,
        description="Maximum requests per hour"
    )
    rate_limit_per_day: int = Field(
        default=1000,
        ge=1,
        le=100000,
        description="Maximum requests per day"
    )
    storage_quota_gb: int = Field(
        default=100,
        ge=1,
        le=10000,
        description="Storage quota in GB"
    )
    jobs_quota_monthly: int = Field(
        default=1000,
        ge=1,
        le=100000,
        description="Monthly job quota"
    )
    expires_at: Optional[datetime] = Field(
        default=None,
        description="Expiration date (None = never expires)"
    )
    notes: Optional[str] = Field(
        default=None,
        max_length=2048,
        description="Internal notes about this API key"
    )


class APIKeyResponse(BaseModel):
    """Schema for API key response (without the actual key)."""
    id: int
    key_prefix: str
    name: str
    email: Optional[str] = None
    organization: Optional[str] = None
    is_active: bool
    permissions: Dict[str, Any]
    rate_limit_per_hour: int
    rate_limit_per_day: int
    storage_quota_gb: int
    storage_used_bytes: int
    jobs_quota_monthly: int
    jobs_used_monthly: int
    total_requests: int
    last_used_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class APIKeyCreateResponse(BaseModel):
    """Schema for API key creation response (includes the actual key once)."""
    id: int
    key: str = Field(
        ...,
        description="The API key - SAVE THIS! It won't be shown again."
    )
    key_prefix: str
    name: str
    message: str = "API key created successfully. Save the key, it won't be shown again."

    class Config:
        from_attributes = True


class APIKeyUpdate(BaseModel):
    """Schema for updating an API key."""
    name: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=255
    )
    is_active: Optional[bool] = None
    permissions: Optional[APIKeyPermissions] = None
    rate_limit_per_hour: Optional[int] = Field(
        default=None,
        ge=1,
        le=10000
    )
    rate_limit_per_day: Optional[int] = Field(
        default=None,
        ge=1,
        le=100000
    )
    storage_quota_gb: Optional[int] = Field(
        default=None,
        ge=1,
        le=10000
    )
    jobs_quota_monthly: Optional[int] = Field(
        default=None,
        ge=1,
        le=100000
    )
    expires_at: Optional[datetime] = None
    notes: Optional[str] = Field(
        default=None,
        max_length=2048
    )


class APIKeyUsageStats(BaseModel):
    """Schema for API key usage statistics."""
    total_requests: int
    storage_used_gb: float
    storage_quota_gb: int
    storage_usage_percent: float
    jobs_used_monthly: int
    jobs_quota_monthly: int
    jobs_usage_percent: float
    last_used_at: Optional[datetime] = None

    class Config:
        from_attributes = True
