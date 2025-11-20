"""
Pydantic schemas for job-related requests and responses.
Provides validation and serialization for API endpoints.
"""
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, validator, HttpUrl
from datetime import datetime
from decimal import Decimal
from enum import Enum


class JobStatus(str, Enum):
    """Job status enumeration."""
    PENDING = "pending"
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Resolution(str, Enum):
    """Supported video resolutions."""
    R_360P = "360p"
    R_720P = "720p"
    R_1080P = "1080p"


class TranscriptionLanguage(str, Enum):
    """Common transcription languages."""
    AUTO = "auto"
    EN = "en"
    ES = "es"
    PT = "pt"
    FR = "fr"
    DE = "de"
    IT = "it"
    JA = "ja"
    KO = "ko"
    ZH = "zh"


# ========================================
# Request Schemas
# ========================================

class JobCreateBase(BaseModel):
    """Base schema for job creation."""
    target_resolutions: Optional[List[Resolution]] = Field(
        default=["720p"],
        description="Target resolutions for transcoding"
    )
    enable_hls: bool = Field(
        default=True,
        description="Enable HLS streaming output"
    )
    enable_audio_extraction: bool = Field(
        default=False,
        description="Extract audio to MP3"
    )
    enable_transcription: bool = Field(
        default=False,
        description="Enable automatic transcription"
    )
    transcription_language: Optional[TranscriptionLanguage] = Field(
        default=TranscriptionLanguage.AUTO,
        description="Language for transcription (auto-detect if not specified)"
    )
    webhook_url: Optional[HttpUrl] = Field(
        default=None,
        description="Webhook URL for job completion notification"
    )
    metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Custom metadata (max 10KB)"
    )
    priority: int = Field(
        default=5,
        ge=1,
        le=10,
        description="Job priority (1=lowest, 10=highest)"
    )

    @validator("target_resolutions")
    def validate_resolutions(cls, v):
        """Ensure at least one resolution is specified."""
        if not v or len(v) == 0:
            raise ValueError("At least one target resolution must be specified")
        # Remove duplicates while preserving order
        seen = set()
        return [x for x in v if not (x in seen or seen.add(x))]

    @validator("metadata")
    def validate_metadata_size(cls, v):
        """Ensure metadata is not too large."""
        if v:
            import json
            metadata_json = json.dumps(v)
            if len(metadata_json) > 10240:  # 10KB
                raise ValueError("Metadata exceeds 10KB limit")
        return v


class JobCreateUpload(JobCreateBase):
    """Schema for creating a job via file upload."""
    # File will be in the multipart form data
    # This schema handles the JSON fields only
    pass


class JobCreateFilesystem(JobCreateBase):
    """Schema for creating a job from filesystem path."""
    source_path: str = Field(
        ...,
        description="Absolute path to video file on server filesystem",
        min_length=1,
        max_length=2048
    )
    custom_thumbnail_path: Optional[str] = Field(
        default=None,
        description="Optional path to custom thumbnail image",
        max_length=2048
    )

    @validator("source_path")
    def validate_source_path(cls, v):
        """Ensure path looks valid."""
        if not v.startswith("/"):
            raise ValueError("source_path must be an absolute path")
        return v


class JobCreateMinIO(JobCreateBase):
    """Schema for creating a job from MinIO object."""
    object_key: str = Field(
        ...,
        description="MinIO object key (path within bucket)",
        min_length=1,
        max_length=2048
    )
    bucket_name: Optional[str] = Field(
        default="videos",
        description="MinIO bucket name"
    )
    custom_thumbnail_object_key: Optional[str] = Field(
        default=None,
        description="Optional MinIO object key for custom thumbnail",
        max_length=2048
    )


# ========================================
# Response Schemas
# ========================================

class JobResponse(BaseModel):
    """Schema for job response."""
    id: int
    job_id: str
    status: JobStatus
    priority: int

    # Source information
    source_filename: str
    source_size_bytes: Optional[int] = None
    source_duration_seconds: Optional[Decimal] = None
    source_resolution: Optional[str] = None
    source_codec: Optional[str] = None
    source_bitrate: Optional[int] = None
    source_fps: Optional[Decimal] = None

    # Processing configuration
    target_resolutions: Optional[List[str]] = None
    enable_hls: bool
    enable_audio_extraction: bool
    enable_transcription: bool
    transcription_language: Optional[str] = None

    # Output information (populated when completed)
    output_formats: Optional[List[str]] = None
    hls_manifest_url: Optional[str] = None
    audio_file_url: Optional[str] = None
    transcription_url: Optional[str] = None
    thumbnail_url: Optional[str] = None

    # Processing metrics
    processing_started_at: Optional[datetime] = None
    processing_completed_at: Optional[datetime] = None
    processing_duration_seconds: Optional[int] = None
    compression_ratio: Optional[Decimal] = None
    output_total_size_bytes: Optional[int] = None

    # Error handling
    error_message: Optional[str] = None
    retry_count: int

    # Metadata
    metadata: Optional[Dict[str, Any]] = None
    webhook_url: Optional[str] = None
    webhook_sent: bool

    # Timestamps
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True  # Pydantic v2 (was orm_mode in v1)


class JobListResponse(BaseModel):
    """Schema for paginated job list response."""
    total: int
    page: int
    page_size: int
    jobs: List[JobResponse]


class JobCreateResponse(BaseModel):
    """Schema for job creation response."""
    job_id: str
    status: JobStatus
    message: str = "Job created successfully"

    class Config:
        from_attributes = True


class JobStatusResponse(BaseModel):
    """Simplified schema for job status queries."""
    job_id: str
    status: JobStatus
    progress_percent: Optional[int] = Field(
        default=None,
        description="Processing progress (0-100)"
    )
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ========================================
# Validation Response Schema
# ========================================

class VideoValidationResult(BaseModel):
    """Schema for video validation results."""
    is_valid: bool
    filename: str
    size_bytes: int
    duration_seconds: Optional[Decimal] = None
    resolution: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    codec: Optional[str] = None
    bitrate: Optional[int] = None
    fps: Optional[Decimal] = None
    format: Optional[str] = None
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
