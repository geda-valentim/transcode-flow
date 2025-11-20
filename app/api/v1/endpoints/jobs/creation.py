"""
Job creation endpoints for video transcoding operations.
Handles job creation via upload, filesystem, and MinIO.
"""
import uuid
import os
from typing import Optional
from fastapi import APIRouter, Depends, File, UploadFile, Form, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.job import Job, JobStatus
from app.models.api_key import APIKey
from app.schemas.job import (
    JobCreateUpload,
    JobCreateFilesystem,
    JobCreateMinIO,
    JobCreateResponse,
)
from app.core.security import get_api_key, check_jobs_quota
from app.core.config import settings
from .validations import (
    check_upload_permissions,
    check_job_permissions,
    validate_and_process_upload,
    validate_filesystem_path,
    parse_metadata,
    build_job_metadata,
    increment_usage_counters,
)

router = APIRouter()


@router.post("/upload", response_model=JobCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_job_upload(
    video_file: UploadFile = File(..., description="Video file to transcode"),
    target_resolutions: Optional[str] = Form(default="720p", description="Comma-separated resolutions (e.g., '360p,720p')"),
    enable_hls: bool = Form(default=True),
    enable_audio_extraction: bool = Form(default=False),
    enable_transcription: bool = Form(default=False),
    transcription_language: str = Form(default="auto"),
    webhook_url: Optional[str] = Form(default=None),
    metadata: Optional[str] = Form(default=None, description="JSON metadata"),
    priority: int = Form(default=5, ge=1, le=10),
    thumbnail: Optional[UploadFile] = File(default=None, description="Custom thumbnail image"),
    api_key: APIKey = Depends(get_api_key),
    db: Session = Depends(get_db),
):
    """
    Create a new transcoding job by uploading a video file.

    - **video_file**: Video file to upload and transcode
    - **thumbnail**: Optional custom thumbnail image
    - **target_resolutions**: Comma-separated list (e.g., "360p,720p,1080p")
    - **enable_hls**: Generate HLS streaming output
    - **enable_audio_extraction**: Extract audio to MP3
    - **enable_transcription**: Enable automatic transcription
    - **transcription_language**: Language code or "auto"
    - **webhook_url**: URL to receive completion notification
    - **metadata**: Custom JSON metadata (max 10KB)
    - **priority**: Job priority (1=lowest, 10=highest)
    """
    # Check permissions and quotas
    check_upload_permissions(api_key, enable_transcription)
    check_jobs_quota(api_key)

    # Validate and process upload
    file_content, file_size, validation_result = await validate_and_process_upload(
        video_file, api_key
    )

    # Generate job ID
    job_id = str(uuid.uuid4())

    # Save video file to temp storage
    temp_video_path = os.path.join(settings.TEMP_DIR, f"{job_id}_{video_file.filename}")

    with open(temp_video_path, "wb") as f:
        f.write(file_content)

    # Save thumbnail if provided
    custom_thumbnail_path = None
    if thumbnail:
        thumbnail_content = await thumbnail.read()
        custom_thumbnail_path = os.path.join(settings.TEMP_DIR, f"{job_id}_thumb_{thumbnail.filename}")
        with open(custom_thumbnail_path, "wb") as f:
            f.write(thumbnail_content)

    # Parse target resolutions
    resolutions_list = [r.strip() for r in target_resolutions.split(",")]

    # Parse and build metadata
    parsed_metadata = parse_metadata(metadata)
    video_metadata = build_job_metadata(validation_result, parsed_metadata)

    # Create job record
    job = Job(
        api_key_id=api_key.id,
        job_id=job_id,
        status=JobStatus.PENDING,
        priority=priority,
        source_path=temp_video_path,
        source_filename=video_file.filename,
        source_size_bytes=file_size,
        source_duration_seconds=validation_result.duration_seconds,
        source_resolution=validation_result.resolution,
        source_codec=validation_result.codec,
        source_bitrate=validation_result.bitrate,
        source_fps=validation_result.fps,
        target_resolutions=resolutions_list,
        enable_hls=enable_hls,
        enable_audio_extraction=enable_audio_extraction,
        enable_transcription=enable_transcription,
        transcription_language=transcription_language if enable_transcription else None,
        custom_thumbnail_path=custom_thumbnail_path,
        webhook_url=webhook_url,
        job_metadata=video_metadata,
    )

    db.add(job)
    db.commit()
    db.refresh(job)

    # Increment usage counters
    increment_usage_counters(db, api_key, file_size)

    return JobCreateResponse(
        job_id=job.job_id,
        status=job.status,
        message="Job created successfully and queued for processing",
    )


@router.post("/filesystem", response_model=JobCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_job_filesystem(
    job_data: JobCreateFilesystem,
    api_key: APIKey = Depends(get_api_key),
    db: Session = Depends(get_db),
):
    """
    Create a new transcoding job from a file on the server filesystem.

    Requires the video file to already exist on the server.
    Useful for processing files uploaded via other methods (FTP, rsync, etc.).
    """
    # Check permissions and quotas
    check_job_permissions(api_key, job_data.enable_transcription)
    check_jobs_quota(api_key)

    # Validate file from filesystem
    validation_result = validate_filesystem_path(job_data.source_path, api_key)

    # Generate job ID
    job_id = str(uuid.uuid4())

    # Build metadata
    video_metadata = build_job_metadata(
        validation_result,
        job_data.metadata
    )

    # Create job record
    job = Job(
        api_key_id=api_key.id,
        job_id=job_id,
        status=JobStatus.PENDING,
        priority=job_data.priority,
        source_path=job_data.source_path,
        source_filename=os.path.basename(job_data.source_path),
        source_size_bytes=validation_result.size_bytes,
        source_duration_seconds=validation_result.duration_seconds,
        source_resolution=validation_result.resolution,
        source_codec=validation_result.codec,
        source_bitrate=validation_result.bitrate,
        source_fps=validation_result.fps,
        target_resolutions=[r.value for r in job_data.target_resolutions],
        enable_hls=job_data.enable_hls,
        enable_audio_extraction=job_data.enable_audio_extraction,
        enable_transcription=job_data.enable_transcription,
        transcription_language=job_data.transcription_language.value if job_data.enable_transcription else None,
        custom_thumbnail_path=job_data.custom_thumbnail_path,
        webhook_url=str(job_data.webhook_url) if job_data.webhook_url else None,
        job_metadata=video_metadata,
    )

    db.add(job)
    db.commit()
    db.refresh(job)

    # Increment usage counters
    increment_usage_counters(db, api_key, validation_result.size_bytes)

    return JobCreateResponse(
        job_id=job.job_id,
        status=job.status,
        message="Job created successfully from filesystem path",
    )


@router.post("/minio", response_model=JobCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_job_minio(
    job_data: JobCreateMinIO,
    api_key: APIKey = Depends(get_api_key),
    db: Session = Depends(get_db),
):
    """
    Create a new transcoding job from a file stored in MinIO/S3.

    Requires the video file to already exist in the MinIO bucket.
    The file will be downloaded, validated, and processed.
    """
    # Check permissions and quotas
    check_job_permissions(api_key, job_data.enable_transcription)
    check_jobs_quota(api_key)

    # TODO: Implement MinIO client and download logic
    # For now, return a placeholder response

    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="MinIO integration will be implemented in Sprint 2. "
               "Please use /upload or /filesystem endpoints for now.",
    )
