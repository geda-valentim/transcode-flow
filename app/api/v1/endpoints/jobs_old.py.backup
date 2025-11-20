"""
Job endpoints for video transcoding operations.
Handles job creation via upload, filesystem, and MinIO.
"""
import uuid
import os
import shutil
from typing import Optional, List
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, File, UploadFile, Form, HTTPException, status, Query, Body
from fastapi.responses import StreamingResponse
import csv
import io
import json as json_lib
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.job import Job, JobStatus
from app.models.api_key import APIKey
from app.schemas.job import (
    JobCreateUpload,
    JobCreateFilesystem,
    JobCreateMinIO,
    JobCreateResponse,
    JobResponse,
)
from app.core.security import get_api_key
from app.core.rate_limit import check_rate_limit
from app.core.security import (
    check_permission,
    check_storage_quota,
    check_jobs_quota,
    increment_jobs_usage,
    increment_storage_usage,
)
from app.services.video_validator import video_validator
from app.services.metadata_service import metadata_service
from app.core.config import settings

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
    # Check rate limiting
    check_rate_limit(api_key)

    # Check permissions
    check_permission(api_key, "can_upload")
    check_permission(api_key, "can_transcode")

    if enable_transcription:
        check_permission(api_key, "can_transcribe")

    # Check quotas
    check_jobs_quota(api_key)

    # Read file content
    file_content = await video_file.read()
    file_size = len(file_content)

    # Check storage quota
    check_storage_quota(api_key, file_size)

    # Validate video file
    validation_result = video_validator.validate_uploaded_file(
        file_content=file_content,
        filename=video_file.filename,
        content_type=video_file.content_type,
    )

    if not validation_result.is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": "Video validation failed",
                "errors": validation_result.errors,
                "warnings": validation_result.warnings,
            },
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

    # Parse metadata JSON
    import json
    parsed_metadata = None
    if metadata:
        try:
            parsed_metadata = json.loads(metadata)
            parsed_metadata = metadata_service.validate_metadata(parsed_metadata)
        except json.JSONDecodeError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid JSON in metadata field",
            )

    # Add validation metadata
    video_metadata = metadata_service.extract_video_metadata(validation_result)
    video_metadata["validation"]["validated_at"] = datetime.now(timezone.utc).isoformat()

    if parsed_metadata:
        video_metadata = metadata_service.merge_metadata(video_metadata, parsed_metadata)

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
    increment_jobs_usage(db, api_key)
    increment_storage_usage(db, api_key, file_size)

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
    # Check rate limiting
    check_rate_limit(api_key)

    # Check permissions
    check_permission(api_key, "can_transcode")

    if job_data.enable_transcription:
        check_permission(api_key, "can_transcribe")

    # Check quotas
    check_jobs_quota(api_key)

    # Validate that file exists
    if not os.path.exists(job_data.source_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File not found: {job_data.source_path}",
        )

    # Validate video file
    validation_result = video_validator.validate_file(job_data.source_path)

    if not validation_result.is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": "Video validation failed",
                "errors": validation_result.errors,
                "warnings": validation_result.warnings,
            },
        )

    # Check storage quota
    check_storage_quota(api_key, validation_result.size_bytes)

    # Generate job ID
    job_id = str(uuid.uuid4())

    # Prepare metadata
    video_metadata = metadata_service.extract_video_metadata(validation_result)
    video_metadata["validation"]["validated_at"] = datetime.now(timezone.utc).isoformat()

    if job_data.metadata:
        validated_meta = metadata_service.validate_metadata(job_data.metadata)
        video_metadata = metadata_service.merge_metadata(video_metadata, validated_meta)

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
    increment_jobs_usage(db, api_key)
    increment_storage_usage(db, api_key, validation_result.size_bytes)

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
    # Check rate limiting
    check_rate_limit(api_key)

    # Check permissions
    check_permission(api_key, "can_transcode")

    if job_data.enable_transcription:
        check_permission(api_key, "can_transcribe")

    # Check quotas
    check_jobs_quota(api_key)

    # TODO: Implement MinIO client and download logic
    # For now, return a placeholder response

    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="MinIO integration will be implemented in Sprint 2. "
               "Please use /upload or /filesystem endpoints for now.",
    )


@router.get("/{job_id}", response_model=JobResponse)
async def get_job_status(
    job_id: str,
    api_key: APIKey = Depends(get_api_key),
    db: Session = Depends(get_db),
):
    """
    Get the status and details of a specific job.
    """
    # Query job
    job = db.query(Job).filter(
        Job.job_id == job_id,
        Job.api_key_id == api_key.id,  # Ensure user can only see their own jobs
    ).first()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job not found: {job_id}",
        )

    return job


# ============================================================================
# Sprint 5: Job Monitoring & Control Endpoints
# ============================================================================

@router.get("", response_model=dict)
async def list_jobs(
    page: int = 1,
    page_size: int = 100,
    status_filter: Optional[str] = None,
    api_key: APIKey = Depends(get_api_key),
    db: Session = Depends(get_db),
):
    """
    List jobs for the authenticated user with pagination.

    **Parameters:**
    - page: Page number (default: 1)
    - page_size: Items per page (max 100, default: 100)
    - status_filter: Filter by job status

    **Returns:**
    Paginated list of jobs
    """
    query = db.query(Job).filter(Job.api_key_id == api_key.id)

    if status_filter:
        query = query.filter(Job.status == status_filter)

    # Get total count
    total = query.count()

    # Apply pagination
    offset = (page - 1) * min(page_size, 100)
    jobs = query.order_by(Job.created_at.desc()).offset(offset).limit(min(page_size, 100)).all()

    # Calculate total pages
    total_pages = (total + page_size - 1) // page_size

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "jobs": [JobResponse.from_orm(job) for job in jobs]
    }


@router.delete("/{job_id}")
async def delete_job(
    job_id: str,
    delete_files: bool = False,
    api_key: APIKey = Depends(get_api_key),
    db: Session = Depends(get_db),
):
    """
    Delete a job.

    **Parameters:**
    - job_id: Job ID to delete
    - delete_files: If true, also delete output files from storage

    **Note:** Cannot delete jobs that are currently processing
    """
    job = db.query(Job).filter(
        Job.job_id == job_id,
        Job.api_key_id == api_key.id
    ).first()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job not found: {job_id}"
        )

    # Prevent deletion of processing jobs
    if job.status == JobStatus.PROCESSING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete job while it is processing. Cancel the job first."
        )

    files_deleted = 0

    # Delete files if requested
    if delete_files:
        # TODO: Implement file deletion from MinIO
        pass

    # Delete job from database
    db.delete(job)
    db.commit()

    message = f"Job '{job_id}' deleted successfully"
    if delete_files:
        message += f" ({files_deleted} files removed)"

    return {"job_id": job_id, "deleted": True, "message": message}


@router.post("/{job_id}/cancel")
async def cancel_job(
    job_id: str,
    api_key: APIKey = Depends(get_api_key),
    db: Session = Depends(get_db),
):
    """
    Cancel a running job.

    **Behavior:**
    - Jobs in 'pending' or 'queued' status are cancelled immediately
    - Jobs in 'processing' status are marked for cancellation
    - Completed, failed, or already cancelled jobs cannot be cancelled
    """
    job = db.query(Job).filter(
        Job.job_id == job_id,
        Job.api_key_id == api_key.id
    ).first()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job not found: {job_id}"
        )

    # Check if job can be cancelled
    if job.status in [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot cancel job with status '{job.status.value}'"
        )

    # Cancel the job
    job.status = JobStatus.CANCELLED
    job.updated_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(job)

    return {
        "job_id": job_id,
        "status": job.status.value,
        "message": f"Job '{job_id}' has been cancelled"
    }


@router.post("/{job_id}/retry")
async def retry_failed_job(
    job_id: str,
    api_key: APIKey = Depends(get_api_key),
    db: Session = Depends(get_db),
):
    """
    Retry a failed job.

    **Behavior:**
    - Only failed jobs can be retried
    - Job status is reset to 'pending'
    - Retry count is incremented
    """
    job = db.query(Job).filter(
        Job.job_id == job_id,
        Job.api_key_id == api_key.id
    ).first()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job not found: {job_id}"
        )

    # Only failed jobs can be retried
    if job.status != JobStatus.FAILED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot retry job with status '{job.status.value}'. Only failed jobs can be retried."
        )

    # Reset job status
    job.status = JobStatus.PENDING
    job.retry_count += 1
    job.error_message = None
    job.processing_started_at = None
    job.processing_completed_at = None
    job.processing_duration_seconds = None
    job.updated_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(job)

    return {
        "job_id": job_id,
        "status": job.status.value,
        "retry_count": job.retry_count,
        "message": f"Job '{job_id}' has been queued for retry (attempt #{job.retry_count})"
    }


@router.patch("/{job_id}/priority")
async def update_job_priority(
    job_id: str,
    priority: int,
    api_key: APIKey = Depends(get_api_key),
    db: Session = Depends(get_db),
):
    """
    Update job priority.

    **Priority Levels:**
    - 1-3: Low priority
    - 4-6: Normal priority
    - 7-10: High priority

    **Note:** Priority changes only affect jobs in 'pending' or 'queued' status
    """
    if not 1 <= priority <= 10:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Priority must be between 1 and 10"
        )

    job = db.query(Job).filter(
        Job.job_id == job_id,
        Job.api_key_id == api_key.id
    ).first()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job not found: {job_id}"
        )

    old_priority = job.priority

    # Update priority
    job.priority = priority
    job.updated_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(job)

    return {
        "job_id": job_id,
        "old_priority": old_priority,
        "new_priority": priority,
        "message": f"Job priority updated from {old_priority} to {priority}"
    }


@router.get("/stats")
async def get_job_statistics(
    from_date: Optional[datetime] = Query(None, description="Filter jobs created from this date"),
    to_date: Optional[datetime] = Query(None, description="Filter jobs created until this date"),
    api_key: APIKey = Depends(get_api_key),
    db: Session = Depends(get_db),
):
    """
    Get job statistics and metrics aggregation for the authenticated API key.

    Returns comprehensive statistics including:
    - Total job counts by status
    - Success rate percentage
    - Processing metrics (total time, average time, efficiency)
    - Storage usage information
    - Date range filters
    """
    # Build base query for this API key
    query = db.query(Job).filter(Job.api_key_id == api_key.id)

    # Apply date filters if provided
    if from_date:
        query = query.filter(Job.created_at >= from_date)

    if to_date:
        query = query.filter(Job.created_at <= to_date)

    # Calculate job counts by status
    status_counts = {}
    for status in [JobStatus.PENDING, JobStatus.QUEUED, JobStatus.PROCESSING,
                   JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED]:
        count = query.filter(Job.status == status).count()
        status_counts[status.value] = count

    # Get total job count
    total_jobs = query.count()

    # Calculate success rate
    success_rate = (
        (status_counts[JobStatus.COMPLETED.value] / total_jobs * 100)
        if total_jobs > 0 else 0
    )

    # Get completed jobs for processing metrics
    completed_jobs = query.filter(Job.status == JobStatus.COMPLETED).all()

    # Calculate processing metrics
    total_processing_time = sum(
        job.processing_duration_seconds or 0
        for job in completed_jobs
    )

    total_video_duration = sum(
        job.duration_seconds or 0
        for job in completed_jobs
    )

    avg_processing_time = (
        total_processing_time / len(completed_jobs)
        if completed_jobs else 0
    )

    # Calculate processing efficiency (video duration / processing time * 100)
    processing_efficiency = (
        (total_video_duration / total_processing_time * 100)
        if total_processing_time > 0 else 0
    )

    # Get storage usage from StorageQuotaManager
    from app.storage.quota import StorageQuotaManager
    quota_manager = StorageQuotaManager()

    try:
        storage_usage = quota_manager.get_usage(api_key.id)
    except Exception as e:
        # If storage check fails, return minimal info
        storage_usage = {
            "used_bytes": 0,
            "quota_bytes": api_key.quota_storage_gb * 1024 * 1024 * 1024 if api_key.quota_storage_gb else 0,
            "used_gb": 0,
            "quota_gb": api_key.quota_storage_gb or 0,
            "percentage_used": 0,
            "available_bytes": api_key.quota_storage_gb * 1024 * 1024 * 1024 if api_key.quota_storage_gb else 0,
            "error": str(e)
        }

    return {
        "total_jobs": total_jobs,
        "status_breakdown": status_counts,
        "success_rate": round(success_rate, 2),
        "processing_metrics": {
            "total_processing_time_seconds": total_processing_time,
            "total_processing_time_hours": round(total_processing_time / 3600, 2),
            "total_video_duration_seconds": total_video_duration,
            "total_video_duration_hours": round(total_video_duration / 3600, 2),
            "average_processing_time_seconds": round(avg_processing_time, 2),
            "processing_efficiency_percent": round(processing_efficiency, 2),
            "completed_jobs_count": len(completed_jobs)
        },
        "storage": storage_usage,
        "date_range": {
            "from": from_date.isoformat() if from_date else None,
            "to": to_date.isoformat() if to_date else None
        }
    }


@router.post("/batch/status")
async def get_batch_job_status(
    job_ids: List[str] = Body(..., description="List of job IDs to retrieve status for (max 100)"),
    api_key: APIKey = Depends(get_api_key),
    db: Session = Depends(get_db),
):
    """
    Get status for multiple jobs in a single request.

    This endpoint allows you to retrieve the status of up to 100 jobs at once,
    which is useful for dashboard monitoring or batch operations.

    Returns a dictionary mapping job_id to job status, or error information for jobs that don't exist.
    """
    # Limit batch size to prevent abuse
    if len(job_ids) > 100:
        raise HTTPException(
            status_code=400,
            detail="Maximum 100 job IDs allowed per batch request"
        )

    if not job_ids:
        raise HTTPException(
            status_code=400,
            detail="At least one job ID must be provided"
        )

    # Query all jobs matching the provided IDs for this API key
    jobs = db.query(Job).filter(
        Job.job_id.in_(job_ids),
        Job.api_key_id == api_key.id
    ).all()

    # Create a mapping of job_id to job object for quick lookup
    jobs_map = {job.job_id: job for job in jobs}

    # Build response with status for each requested job_id
    results = {}
    for job_id in job_ids:
        if job_id in jobs_map:
            job = jobs_map[job_id]
            results[job_id] = {
                "found": True,
                "status": job.status.value,
                "priority": job.priority,
                "progress": job.current_task_progress,
                "created_at": job.created_at.isoformat() if job.created_at else None,
                "updated_at": job.updated_at.isoformat() if job.updated_at else None,
                "processing_started_at": job.processing_started_at.isoformat() if job.processing_started_at else None,
                "processing_completed_at": job.processing_completed_at.isoformat() if job.processing_completed_at else None,
                "error_message": job.error_message if job.status == JobStatus.FAILED else None
            }
        else:
            results[job_id] = {
                "found": False,
                "error": f"Job '{job_id}' not found or access denied"
            }

    # Return summary and detailed results
    found_count = sum(1 for r in results.values() if r["found"])
    not_found_count = len(job_ids) - found_count

    return {
        "total_requested": len(job_ids),
        "found": found_count,
        "not_found": not_found_count,
        "jobs": results
    }


@router.get("/search")
async def search_jobs(
    search: Optional[str] = Query(None, description="Search term for filename matching"),
    status: Optional[str] = Query(None, description="Filter by job status"),
    priority_min: Optional[int] = Query(None, description="Minimum priority"),
    priority_max: Optional[int] = Query(None, description="Maximum priority"),
    from_date: Optional[datetime] = Query(None, description="Filter jobs created from this date"),
    to_date: Optional[datetime] = Query(None, description="Filter jobs created until this date"),
    min_duration: Optional[float] = Query(None, description="Minimum video duration in seconds"),
    max_duration: Optional[float] = Query(None, description="Maximum video duration in seconds"),
    sort_by: str = Query("created_at", description="Field to sort by"),
    sort_order: str = Query("desc", description="Sort order (asc/desc)"),
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page"),
    api_key: APIKey = Depends(get_api_key),
    db: Session = Depends(get_db),
):
    """
    Advanced job search with multiple filter options.

    Allows searching and filtering jobs by:
    - Filename search (case-insensitive)
    - Job status
    - Priority range
    - Date range (created_at)
    - Video duration range
    - Sorting by any field
    - Pagination

    Returns paginated results with metadata.
    """
    # Build base query for this API key
    query = db.query(Job).filter(Job.api_key_id == api_key.id)

    # Apply search filter (filename)
    if search:
        query = query.filter(Job.source_filename.ilike(f"%{search}%"))

    # Apply status filter
    if status:
        try:
            status_enum = JobStatus(status)
            query = query.filter(Job.status == status_enum)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status: {status}. Valid values: {[s.value for s in JobStatus]}"
            )

    # Apply priority filters
    if priority_min is not None:
        query = query.filter(Job.priority >= priority_min)
    if priority_max is not None:
        query = query.filter(Job.priority <= priority_max)

    # Apply date range filters
    if from_date:
        query = query.filter(Job.created_at >= from_date)
    if to_date:
        query = query.filter(Job.created_at <= to_date)

    # Apply duration filters
    if min_duration is not None:
        query = query.filter(Job.source_duration_seconds >= min_duration)
    if max_duration is not None:
        query = query.filter(Job.source_duration_seconds <= max_duration)

    # Count total results
    total = query.count()

    # Apply sorting
    valid_sort_fields = [
        "created_at", "updated_at", "priority", "status",
        "source_filename", "source_duration_seconds", "source_size_bytes"
    ]
    if sort_by not in valid_sort_fields:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid sort_by field: {sort_by}. Valid values: {valid_sort_fields}"
        )

    if sort_order == "desc":
        query = query.order_by(getattr(Job, sort_by).desc())
    elif sort_order == "asc":
        query = query.order_by(getattr(Job, sort_by).asc())
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid sort_order: {sort_order}. Valid values: asc, desc"
        )

    # Apply pagination
    offset = (page - 1) * per_page
    jobs = query.offset(offset).limit(per_page).all()

    # Build response
    return {
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": (total + per_page - 1) // per_page if total > 0 else 0,
        "filters_applied": {
            "search": search,
            "status": status,
            "priority_min": priority_min,
            "priority_max": priority_max,
            "from_date": from_date.isoformat() if from_date else None,
            "to_date": to_date.isoformat() if to_date else None,
            "min_duration": min_duration,
            "max_duration": max_duration,
            "sort_by": sort_by,
            "sort_order": sort_order
        },
        "jobs": [
            {
                "job_id": job.job_id,
                "status": job.status.value,
                "priority": job.priority,
                "source_filename": job.source_filename,
                "source_duration_seconds": float(job.source_duration_seconds) if job.source_duration_seconds else None,
                "source_size_bytes": job.source_size_bytes,
                "source_resolution": job.source_resolution,
                "created_at": job.created_at.isoformat() if job.created_at else None,
                "updated_at": job.updated_at.isoformat() if job.updated_at else None,
                "processing_started_at": job.processing_started_at.isoformat() if job.processing_started_at else None,
                "processing_completed_at": job.processing_completed_at.isoformat() if job.processing_completed_at else None,
                "error_message": job.error_message if job.status == JobStatus.FAILED else None
            }
            for job in jobs
        ]
    }


@router.get("/export")
async def export_jobs(
    format: str = Query("json", description="Export format: json or csv"),
    search: Optional[str] = Query(None, description="Search term for filename matching"),
    status: Optional[str] = Query(None, description="Filter by job status"),
    from_date: Optional[datetime] = Query(None, description="Filter jobs created from this date"),
    to_date: Optional[datetime] = Query(None, description="Filter jobs created until this date"),
    limit: int = Query(1000, ge=1, le=10000, description="Maximum number of jobs to export"),
    api_key: APIKey = Depends(get_api_key),
    db: Session = Depends(get_db),
):
    """
    Export jobs to CSV or JSON format.

    Supports:
    - JSON format: Returns array of job objects
    - CSV format: Returns spreadsheet-compatible CSV file
    - Filtering by search, status, date range
    - Maximum 10,000 jobs per export

    Returns file download with appropriate Content-Type and filename.
    """
    # Validate format
    if format not in ["json", "csv"]:
        raise HTTPException(
            status_code=400,
            detail="Invalid format. Valid values: json, csv"
        )

    # Build query with filters (reuse search endpoint logic)
    query = db.query(Job).filter(Job.api_key_id == api_key.id)

    if search:
        query = query.filter(Job.source_filename.ilike(f"%{search}%"))

    if status:
        try:
            status_enum = JobStatus(status)
            query = query.filter(Job.status == status_enum)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status: {status}. Valid values: {[s.value for s in JobStatus]}"
            )

    if from_date:
        query = query.filter(Job.created_at >= from_date)
    if to_date:
        query = query.filter(Job.created_at <= to_date)

    # Order by created_at descending and limit
    query = query.order_by(Job.created_at.desc()).limit(limit)
    jobs = query.all()

    # Generate timestamp for filename
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    if format == "json":
        # Export as JSON
        jobs_data = [
            {
                "job_id": job.job_id,
                "status": job.status.value,
                "priority": job.priority,
                "source_filename": job.source_filename,
                "source_size_bytes": job.source_size_bytes,
                "source_duration_seconds": float(job.source_duration_seconds) if job.source_duration_seconds else None,
                "source_resolution": job.source_resolution,
                "source_codec": job.source_codec,
                "source_bitrate": job.source_bitrate,
                "source_fps": float(job.source_fps) if job.source_fps else None,
                "target_resolutions": job.target_resolutions,
                "enable_hls": job.enable_hls,
                "enable_audio_extraction": job.enable_audio_extraction,
                "enable_transcription": job.enable_transcription,
                "output_path": job.output_path,
                "output_formats": job.output_formats,
                "hls_manifest_url": job.hls_manifest_url,
                "audio_file_url": job.audio_file_url,
                "transcription_url": job.transcription_url,
                "thumbnail_url": job.thumbnail_url,
                "processing_started_at": job.processing_started_at.isoformat() if job.processing_started_at else None,
                "processing_completed_at": job.processing_completed_at.isoformat() if job.processing_completed_at else None,
                "processing_duration_seconds": job.processing_duration_seconds,
                "compression_ratio": float(job.compression_ratio) if job.compression_ratio else None,
                "output_total_size_bytes": job.output_total_size_bytes,
                "error_message": job.error_message,
                "retry_count": job.retry_count,
                "created_at": job.created_at.isoformat() if job.created_at else None,
                "updated_at": job.updated_at.isoformat() if job.updated_at else None
            }
            for job in jobs
        ]

        # Create JSON string
        json_content = json_lib.dumps(jobs_data, indent=2)

        # Return as streaming response
        return StreamingResponse(
            io.BytesIO(json_content.encode('utf-8')),
            media_type="application/json",
            headers={
                "Content-Disposition": f"attachment; filename=jobs_export_{timestamp}.json"
            }
        )

    elif format == "csv":
        # Export as CSV
        output = io.StringIO()

        # Define CSV columns
        fieldnames = [
            "job_id", "status", "priority", "source_filename",
            "source_size_bytes", "source_duration_seconds", "source_resolution",
            "source_codec", "source_bitrate", "source_fps",
            "target_resolutions", "enable_hls", "enable_audio_extraction",
            "enable_transcription", "output_path", "hls_manifest_url",
            "audio_file_url", "transcription_url", "thumbnail_url",
            "processing_started_at", "processing_completed_at",
            "processing_duration_seconds", "compression_ratio",
            "output_total_size_bytes", "error_message", "retry_count",
            "created_at", "updated_at"
        ]

        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()

        for job in jobs:
            writer.writerow({
                "job_id": job.job_id,
                "status": job.status.value,
                "priority": job.priority,
                "source_filename": job.source_filename,
                "source_size_bytes": job.source_size_bytes,
                "source_duration_seconds": float(job.source_duration_seconds) if job.source_duration_seconds else "",
                "source_resolution": job.source_resolution or "",
                "source_codec": job.source_codec or "",
                "source_bitrate": job.source_bitrate or "",
                "source_fps": float(job.source_fps) if job.source_fps else "",
                "target_resolutions": json_lib.dumps(job.target_resolutions) if job.target_resolutions else "",
                "enable_hls": job.enable_hls,
                "enable_audio_extraction": job.enable_audio_extraction,
                "enable_transcription": job.enable_transcription,
                "output_path": job.output_path or "",
                "hls_manifest_url": job.hls_manifest_url or "",
                "audio_file_url": job.audio_file_url or "",
                "transcription_url": job.transcription_url or "",
                "thumbnail_url": job.thumbnail_url or "",
                "processing_started_at": job.processing_started_at.isoformat() if job.processing_started_at else "",
                "processing_completed_at": job.processing_completed_at.isoformat() if job.processing_completed_at else "",
                "processing_duration_seconds": job.processing_duration_seconds or "",
                "compression_ratio": float(job.compression_ratio) if job.compression_ratio else "",
                "output_total_size_bytes": job.output_total_size_bytes or "",
                "error_message": job.error_message or "",
                "retry_count": job.retry_count,
                "created_at": job.created_at.isoformat() if job.created_at else "",
                "updated_at": job.updated_at.isoformat() if job.updated_at else ""
            })

        # Return CSV as streaming response
        csv_content = output.getvalue()
        return StreamingResponse(
            io.BytesIO(csv_content.encode('utf-8')),
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename=jobs_export_{timestamp}.csv"
            }
        )
