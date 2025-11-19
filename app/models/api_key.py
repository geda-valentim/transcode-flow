"""
SQLAlchemy model for API keys.
Represents the api_keys table in the database.
"""
from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    Boolean,
    BigInteger,
    Index,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class APIKey(Base):
    """
    API Key model for authentication and authorization.
    Maps to the 'api_keys' table in PostgreSQL.
    """
    __tablename__ = "api_keys"

    # Primary Key
    id = Column(Integer, primary_key=True, autoincrement=True)

    # API Key
    key_hash = Column(String(128), unique=True, nullable=False, index=True)
    key_prefix = Column(String(16), nullable=False)  # First 8 chars for identification

    # Owner Information
    name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=True)
    organization = Column(String(255), nullable=True)

    # Status
    is_active = Column(Boolean, default=True, nullable=False, index=True)

    # Permissions (JSONB for flexibility)
    permissions = Column(
        JSONB,
        nullable=False,
        default={
            "can_upload": True,
            "can_transcode": True,
            "can_extract_audio": True,
            "can_transcribe": False,
            "max_resolution": "1080p",
        },
    )

    # Rate Limiting
    rate_limit_per_hour = Column(Integer, default=100, nullable=False)
    rate_limit_per_day = Column(Integer, default=1000, nullable=False)

    # Quota Management
    storage_quota_gb = Column(Integer, default=100, nullable=False)
    storage_used_bytes = Column(BigInteger, default=0, nullable=False)
    jobs_quota_monthly = Column(Integer, default=1000, nullable=False)
    jobs_used_monthly = Column(Integer, default=0, nullable=False)

    # Usage Statistics
    total_requests = Column(BigInteger, default=0, nullable=False)
    last_used_at = Column(DateTime(timezone=True), nullable=True)

    # Expiration
    expires_at = Column(DateTime(timezone=True), nullable=True)

    # Metadata
    metadata = Column(JSONB, nullable=True)
    notes = Column(String(2048), nullable=True)

    # Timestamps
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Indexes for performance (defined in migration, documented here)
    # - idx_api_keys_key_hash (key_hash) [unique]
    # - idx_api_keys_is_active (is_active)
    # - idx_api_keys_created_at (created_at)

    def __repr__(self):
        return f"<APIKey(id={self.id}, name={self.name}, prefix={self.key_prefix})>"

    @property
    def is_expired(self) -> bool:
        """Check if the API key is expired."""
        if self.expires_at is None:
            return False
        from datetime import datetime, timezone
        return datetime.now(timezone.utc) > self.expires_at

    @property
    def is_valid(self) -> bool:
        """Check if the API key is valid (active and not expired)."""
        return self.is_active and not self.is_expired

    @property
    def storage_usage_percent(self) -> float:
        """Calculate storage usage percentage."""
        if self.storage_quota_gb == 0:
            return 0.0
        quota_bytes = self.storage_quota_gb * 1024 * 1024 * 1024
        return (self.storage_used_bytes / quota_bytes) * 100

    @property
    def jobs_usage_percent(self) -> float:
        """Calculate monthly jobs usage percentage."""
        if self.jobs_quota_monthly == 0:
            return 0.0
        return (self.jobs_used_monthly / self.jobs_quota_monthly) * 100

    def has_permission(self, permission: str) -> bool:
        """Check if API key has a specific permission."""
        return self.permissions.get(permission, False)

    def is_within_rate_limit(self, current_hour_requests: int, current_day_requests: int) -> bool:
        """Check if current usage is within rate limits."""
        return (
            current_hour_requests < self.rate_limit_per_hour
            and current_day_requests < self.rate_limit_per_day
        )

    def has_storage_quota(self, required_bytes: int) -> bool:
        """Check if there's enough storage quota available."""
        quota_bytes = self.storage_quota_gb * 1024 * 1024 * 1024
        return (self.storage_used_bytes + required_bytes) <= quota_bytes

    def has_jobs_quota(self) -> bool:
        """Check if there are remaining jobs in monthly quota."""
        return self.jobs_used_monthly < self.jobs_quota_monthly
