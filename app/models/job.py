"""
SQLAlchemy model for video transcoding jobs.
Represents the jobs table in the database.
"""
from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    Enum,
    Boolean,
    BigInteger,
    DECIMAL,
    Index,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from sqlalchemy.ext.declarative import declarative_base
import enum

Base = declarative_base()


class JobStatus(str, enum.Enum):
    """Job status enumeration."""
    PENDING = "pending"
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Job(Base):
    """
    Video transcoding job model.
    Maps to the 'jobs' table in PostgreSQL.
    """
    __tablename__ = "jobs"

    # Primary Key
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Foreign Key
    api_key_id = Column(Integer, nullable=False, index=True)

    # Job Identification
    job_id = Column(String(36), unique=True, nullable=False, index=True)

    # Status & Priority
    status = Column(
        Enum(JobStatus, name="job_status"),
        default=JobStatus.PENDING,
        nullable=False,
        index=True,
    )
    priority = Column(Integer, default=5, nullable=False)

    # Source Video Information
    source_path = Column(String(2048), nullable=False)
    source_filename = Column(String(512), nullable=False)
    source_size_bytes = Column(BigInteger, nullable=True)
    source_duration_seconds = Column(DECIMAL(10, 2), nullable=True)
    source_resolution = Column(String(20), nullable=True)  # e.g., "1920x1080"
    source_codec = Column(String(50), nullable=True)
    source_bitrate = Column(BigInteger, nullable=True)
    source_fps = Column(DECIMAL(5, 2), nullable=True)

    # Processing Configuration
    target_resolutions = Column(JSONB, nullable=True)  # ["360p", "720p", "1080p"]
    enable_hls = Column(Boolean, default=True, nullable=False)
    enable_audio_extraction = Column(Boolean, default=False, nullable=False)
    enable_transcription = Column(Boolean, default=False, nullable=False)
    transcription_language = Column(String(10), nullable=True)  # "auto" or ISO code
    custom_thumbnail_path = Column(String(2048), nullable=True)

    # Output Information
    output_path = Column(String(2048), nullable=True)
    output_formats = Column(JSONB, nullable=True)  # List of generated formats
    hls_manifest_url = Column(String(2048), nullable=True)
    audio_file_url = Column(String(2048), nullable=True)
    transcription_url = Column(String(2048), nullable=True)
    thumbnail_url = Column(String(2048), nullable=True)

    # Processing Metrics
    processing_started_at = Column(DateTime(timezone=True), nullable=True)
    processing_completed_at = Column(DateTime(timezone=True), nullable=True)
    processing_duration_seconds = Column(Integer, nullable=True)
    compression_ratio = Column(DECIMAL(5, 2), nullable=True)
    output_total_size_bytes = Column(BigInteger, nullable=True)

    # Error Handling
    error_message = Column(String(2048), nullable=True)
    retry_count = Column(Integer, default=0, nullable=False)

    # Metadata & Webhooks
    metadata = Column(JSONB, nullable=True)  # Flexible JSON storage
    webhook_url = Column(String(2048), nullable=True)
    webhook_sent = Column(Boolean, default=False, nullable=False)

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
    # - idx_jobs_status (status)
    # - idx_jobs_api_key_id (api_key_id)
    # - idx_jobs_created_at (created_at)
    # - idx_jobs_job_id (job_id) [unique]
    # - idx_jobs_status_priority (status, priority DESC)
    # - idx_jobs_api_key_status (api_key_id, status)

    def __repr__(self):
        return f"<Job(id={self.id}, job_id={self.job_id}, status={self.status})>"

    @property
    def is_completed(self) -> bool:
        """Check if job is in a terminal state."""
        return self.status in [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED]

    @property
    def is_processing(self) -> bool:
        """Check if job is actively being processed."""
        return self.status in [JobStatus.QUEUED, JobStatus.PROCESSING]
