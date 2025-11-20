"""
Job Monitoring & Status API Endpoints

Sprint 5: Job Status & Monitoring APIs

Provides comprehensive job monitoring including:
- Job status retrieval (individual and batch)
- Job listing with pagination and filtering
- Job cancellation and deletion
- Real-time progress tracking (Server-Sent Events)
- Job statistics and metrics
- Job retry and priority management
"""
from fastapi import APIRouter, HTTPException, Depends, Query, Path
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_
from typing import Optional, List
from datetime import datetime, timedelta
import logging
import asyncio
import json

from app.db import get_db
from app.core.security import get_api_key
from app.models.job import Job, JobStatus
from app.schemas.job import JobResponse
from app.storage.presigned import PresignedURLGenerator
from app.core.minio_client import get_minio_client
from app.core.config import settings

router = APIRouter(prefix="/jobs", tags=["jobs"])
logger = logging.getLogger(__name__)


# ============================================================================
# Response Models
# ============================================================================

from pydantic import BaseModel, Field
from decimal import Decimal


class JobDetailedResponse(BaseModel):
    """Detailed job status response with all information"""
    # Basic information
    id: int
    job_id: str
    status: JobStatus
    priority: int

    # Source video information
    source: dict = Field(description="Source video metadata")

    # Processing configuration
    configuration: dict = Field(description="Processing configuration")

    # Progress tracking
    progress: dict = Field(description="Current progress information")

    # Output URLs (when completed)
    outputs: Optional[dict] = Field(None, description="Output file URLs")

    # Processing metrics
    metrics: Optional[dict] = Field(None, description="Processing metrics")

    # Error information (if failed)
    error: Optional[dict] = Field(None, description="Error details")

    # Timestamps
    created_at: datetime
    updated_at: datetime


class JobListResponse(BaseModel):
    """Paginated job list response"""
    total: int = Field(description="Total number of jobs")
    page: int = Field(description="Current page number")
    page_size: int = Field(description="Items per page")
    total_pages: int = Field(description="Total number of pages")
    jobs: List[JobResponse] = Field(description="List of jobs")


class JobStatsResponse(BaseModel):
    """Job statistics response"""
    total_jobs: int
    jobs_by_status: dict
    jobs_today: int
    jobs_this_week: int
    jobs_this_month: int
    average_processing_time_seconds: Optional[float] = None
    total_processing_time_seconds: Optional[float] = None
    total_input_size_gb: Optional[float] = None
    total_output_size_gb: Optional[float] = None
    average_compression_ratio: Optional[float] = None
    success_rate_percent: Optional[float] = None


class JobCancelResponse(BaseModel):
    """Job cancellation response"""
    job_id: str
    status: JobStatus
    message: str


class JobDeleteResponse(BaseModel):
    """Job deletion response"""
    job_id: str
    deleted: bool
    files_deleted: Optional[int] = None
    message: str


class BatchJobStatusRequest(BaseModel):
    """Batch job status request"""
    job_ids: List[str] = Field(..., max_items=100, description="List of job IDs (max 100)")


class BatchJobStatusResponse(BaseModel):
    """Batch job status response"""
    total: int
    jobs: List[JobResponse]
    not_found: List[str] = Field(default_factory=list, description="Job IDs not found")


class JobRetryResponse(BaseModel):
    """Job retry response"""
    job_id: str
    status: JobStatus
    retry_count: int
    message: str


class JobPriorityUpdateRequest(BaseModel):
    """Job priority update request"""
    priority: int = Field(..., ge=1, le=10, description="New priority (1=lowest, 10=highest)")


class JobPriorityUpdateResponse(BaseModel):
    """Job priority update response"""
    job_id: str
    old_priority: int
    new_priority: int
    message: str


# ============================================================================
# Helper Functions
# ============================================================================

def build_job_detailed_response(job: Job, db: Session) -> JobDetailedResponse:
    """Build detailed job response with all information"""

    # Source video information
    source = {
        "filename": job.source_filename,
        "size_bytes": job.source_size_bytes,
        "size_mb": round(job.source_size_bytes / (1024**2), 2) if job.source_size_bytes else None,
        "duration_seconds": float(job.source_duration_seconds) if job.source_duration_seconds else None,
        "resolution": job.source_resolution,
        "codec": job.source_codec,
        "bitrate": job.source_bitrate,
        "fps": float(job.source_fps) if job.source_fps else None,
    }

    # Processing configuration
    configuration = {
        "target_resolutions": job.target_resolutions or [],
        "enable_hls": job.enable_hls,
        "enable_audio_extraction": job.enable_audio_extraction,
        "enable_transcription": job.enable_transcription,
        "transcription_language": job.transcription_language,
    }

    # Progress tracking
    progress = calculate_job_progress(job)

    # Output URLs (only for completed jobs)
    outputs = None
    if job.status == JobStatus.COMPLETED:
        outputs = build_output_urls(job)

    # Processing metrics
    metrics = None
    if job.processing_started_at:
        metrics = {
            "started_at": job.processing_started_at.isoformat(),
            "completed_at": job.processing_completed_at.isoformat() if job.processing_completed_at else None,
            "duration_seconds": job.processing_duration_seconds,
            "compression_ratio": float(job.compression_ratio) if job.compression_ratio else None,
            "input_size_mb": round(job.source_size_bytes / (1024**2), 2) if job.source_size_bytes else None,
            "output_size_mb": round(job.output_total_size_bytes / (1024**2), 2) if job.output_total_size_bytes else None,
        }

    # Error information
    error = None
    if job.status == JobStatus.FAILED:
        error = {
            "message": job.error_message,
            "retry_count": job.retry_count,
        }

    return JobDetailedResponse(
        id=job.id,
        job_id=job.job_id,
        status=job.status,
        priority=job.priority,
        source=source,
        configuration=configuration,
        progress=progress,
        outputs=outputs,
        metrics=metrics,
        error=error,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


def calculate_job_progress(job: Job) -> dict:
    """Calculate job progress based on status and processing time"""

    progress_map = {
        JobStatus.PENDING: 0,
        JobStatus.QUEUED: 5,
        JobStatus.PROCESSING: 50,  # Will be updated based on actual progress
        JobStatus.COMPLETED: 100,
        JobStatus.FAILED: 0,
        JobStatus.CANCELLED: 0,
    }

    progress_percent = progress_map.get(job.status, 0)

    # Calculate ETA for processing jobs
    eta_seconds = None
    if job.status == JobStatus.PROCESSING and job.processing_started_at:
        elapsed = (datetime.utcnow() - job.processing_started_at.replace(tzinfo=None)).total_seconds()
        # Rough estimate: assume 50% done after half expected time
        # Expected time based on source duration (rough heuristic: 2x source duration)
        if job.source_duration_seconds:
            expected_total = float(job.source_duration_seconds) * 2
            eta_seconds = max(0, expected_total - elapsed)

    current_task = get_current_task(job.status)

    return {
        "percent": progress_percent,
        "current_task": current_task,
        "eta_seconds": eta_seconds,
    }


def get_current_task(status: JobStatus) -> str:
    """Get current task description based on job status"""
    task_map = {
        JobStatus.PENDING: "Waiting to start",
        JobStatus.QUEUED: "Queued for processing",
        JobStatus.PROCESSING: "Transcoding video",
        JobStatus.COMPLETED: "Completed",
        JobStatus.FAILED: "Failed",
        JobStatus.CANCELLED: "Cancelled",
    }
    return task_map.get(status, "Unknown")


def build_output_urls(job: Job) -> dict:
    """Build output URLs using presigned URLs"""
    client = get_minio_client()

    url_generator = PresignedURLGenerator(
        client,
        settings.MINIO_BUCKET_NAME
    )

    outputs = {}

    # Video outputs
    if job.target_resolutions:
        outputs["videos"] = {}
        for resolution in job.target_resolutions:
            try:
                video_url = url_generator.get_inline_view_url(
                    f"jobs/{job.job_id}/outputs/{resolution}.mp4",
                    content_type="video/mp4"
                )
                outputs["videos"][resolution] = video_url.url
            except Exception as e:
                logger.warning(f"Failed to generate URL for {resolution}: {e}")

    # HLS manifests
    if job.enable_hls:
        outputs["hls"] = {}
        for resolution in job.target_resolutions or []:
            try:
                hls_urls = url_generator.generate_hls_manifest_urls(
                    job.job_id,
                    resolution
                )
                if "playlist" in hls_urls:
                    outputs["hls"][resolution] = hls_urls["playlist"]
            except Exception as e:
                logger.warning(f"Failed to generate HLS URL for {resolution}: {e}")

    # Audio file
    if job.enable_audio_extraction and job.audio_file_url:
        try:
            audio_url = url_generator.get_direct_download_url(
                f"jobs/{job.job_id}/outputs/audio.mp3",
                filename=f"{job.job_id}_audio.mp3"
            )
            outputs["audio"] = audio_url.url
        except Exception as e:
            logger.warning(f"Failed to generate audio URL: {e}")

    # Transcription files
    if job.enable_transcription and job.transcription_url:
        outputs["transcription"] = {}
        for format in ["txt", "srt", "vtt", "json"]:
            try:
                trans_url = url_generator.get_direct_download_url(
                    f"jobs/{job.job_id}/outputs/transcription/audio.{format}",
                    filename=f"{job.job_id}_transcription.{format}"
                )
                outputs["transcription"][format] = trans_url.url
            except Exception as e:
                logger.debug(f"Transcription format {format} not available: {e}")

    # Thumbnail
    if job.thumbnail_url:
        try:
            thumb_url = url_generator.get_inline_view_url(
                f"jobs/{job.job_id}/outputs/thumbnail.jpg",
                content_type="image/jpeg"
            )
            outputs["thumbnail"] = thumb_url.url
        except Exception as e:
            logger.warning(f"Failed to generate thumbnail URL: {e}")

    return outputs


# ============================================================================
# Endpoints
# ============================================================================

@router.get("/{job_id}", response_model=JobDetailedResponse)
async def get_job_status(
    job_id: str = Path(..., description="Job ID"),
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key)
):
    """
    Get detailed status for a specific job

    Returns comprehensive information including:
    - Source video metadata
    - Processing configuration
    - Current progress and ETA
    - Output file URLs (when completed)
    - Processing metrics
    - Error details (if failed)

    **Authentication:** Requires valid API key
    """
    job = db.query(Job).filter(Job.job_id == job_id).first()

    if not job:
        raise HTTPException(
            status_code=404,
            detail=f"Job '{job_id}' not found"
        )

    return build_job_detailed_response(job, db)


@router.get("", response_model=JobListResponse)
async def list_jobs(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(100, ge=1, le=100, description="Items per page (max 100)"),
    status: Optional[JobStatus] = Query(None, description="Filter by status"),
    priority_min: Optional[int] = Query(None, ge=1, le=10, description="Minimum priority"),
    priority_max: Optional[int] = Query(None, ge=1, le=10, description="Maximum priority"),
    created_after: Optional[datetime] = Query(None, description="Filter jobs created after this date"),
    created_before: Optional[datetime] = Query(None, description="Filter jobs created before this date"),
    sort_by: str = Query("created_at", description="Sort field (created_at, updated_at, priority)"),
    sort_order: str = Query("desc", description="Sort order (asc, desc)"),
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key)
):
    """
    List jobs with pagination and filtering

    **Pagination:**
    - Default: 100 items per page
    - Maximum: 100 items per page

    **Filtering:**
    - By status (pending, queued, processing, completed, failed, cancelled)
    - By priority range (1-10)
    - By creation date range

    **Sorting:**
    - By created_at, updated_at, or priority
    - Ascending or descending order

    **Authentication:** Requires valid API key
    """
    # Build query with filters
    query = db.query(Job)

    if status:
        query = query.filter(Job.status == status)

    if priority_min is not None:
        query = query.filter(Job.priority >= priority_min)

    if priority_max is not None:
        query = query.filter(Job.priority <= priority_max)

    if created_after:
        query = query.filter(Job.created_at >= created_after)

    if created_before:
        query = query.filter(Job.created_at <= created_before)

    # Get total count
    total = query.count()

    # Apply sorting
    sort_field = getattr(Job, sort_by, Job.created_at)
    if sort_order == "desc":
        query = query.order_by(sort_field.desc())
    else:
        query = query.order_by(sort_field.asc())

    # Apply pagination
    offset = (page - 1) * page_size
    jobs = query.offset(offset).limit(page_size).all()

    # Calculate total pages
    total_pages = (total + page_size - 1) // page_size

    return JobListResponse(
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        jobs=[JobResponse.from_orm(job) for job in jobs]
    )


@router.delete("/{job_id}", response_model=JobDeleteResponse)
async def delete_job(
    job_id: str = Path(..., description="Job ID"),
    delete_files: bool = Query(False, description="Also delete output files from storage"),
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key)
):
    """
    Delete a job from the database

    **Options:**
    - delete_files=true: Also delete all output files from MinIO storage
    - delete_files=false: Only delete database record (default)

    **Note:** Cannot delete jobs that are currently processing

    **Authentication:** Requires valid API key
    """
    job = db.query(Job).filter(Job.job_id == job_id).first()

    if not job:
        raise HTTPException(
            status_code=404,
            detail=f"Job '{job_id}' not found"
        )

    # Prevent deletion of processing jobs
    if job.status == JobStatus.PROCESSING:
        raise HTTPException(
            status_code=400,
            detail="Cannot delete job while it is processing. Cancel the job first."
        )

    files_deleted = 0

    # Delete files from storage if requested
    if delete_files:
        try:
                    client = get_minio_client()

            # List all objects for this job
            objects = client.list_objects(
                settings.MINIO_BUCKET_NAME,
                prefix=f"jobs/{job_id}/",
                recursive=True
            )

            # Delete each object
            for obj in objects:
                client.remove_object(settings.MINIO_BUCKET_NAME, obj.object_name)
                files_deleted += 1
                logger.info(f"Deleted file: {obj.object_name}")

        except Exception as e:
            logger.error(f"Failed to delete files for job {job_id}: {e}")
            # Continue with database deletion even if file deletion fails

    # Delete job from database
    db.delete(job)
    db.commit()

    message = f"Job '{job_id}' deleted successfully"
    if delete_files:
        message += f" ({files_deleted} files removed from storage)"

    return JobDeleteResponse(
        job_id=job_id,
        deleted=True,
        files_deleted=files_deleted if delete_files else None,
        message=message
    )


@router.post("/{job_id}/cancel", response_model=JobCancelResponse)
async def cancel_job(
    job_id: str = Path(..., description="Job ID"),
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key)
):
    """
    Cancel a running job

    **Behavior:**
    - Jobs in 'pending' or 'queued' status are cancelled immediately
    - Jobs in 'processing' status are marked for cancellation (worker will stop)
    - Completed, failed, or already cancelled jobs cannot be cancelled

    **Authentication:** Requires valid API key
    """
    job = db.query(Job).filter(Job.job_id == job_id).first()

    if not job:
        raise HTTPException(
            status_code=404,
            detail=f"Job '{job_id}' not found"
        )

    # Check if job can be cancelled
    if job.status in [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel job with status '{job.status.value}'"
        )

    # Cancel the job
    job.status = JobStatus.CANCELLED
    job.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(job)

    logger.info(f"Job {job_id} cancelled by API request")

    return JobCancelResponse(
        job_id=job_id,
        status=job.status,
        message=f"Job '{job_id}' has been cancelled"
    )


@router.get("/stats/summary", response_model=JobStatsResponse)
async def get_job_statistics(
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key)
):
    """
    Get job statistics and metrics

    Returns aggregated statistics including:
    - Total jobs and breakdown by status
    - Jobs created today, this week, this month
    - Average processing time
    - Total input/output sizes
    - Average compression ratio
    - Success rate

    **Authentication:** Requires valid API key
    """
    # Total jobs
    total_jobs = db.query(func.count(Job.id)).scalar()

    # Jobs by status
    status_counts = db.query(
        Job.status,
        func.count(Job.id)
    ).group_by(Job.status).all()

    jobs_by_status = {status.value: count for status, count in status_counts}

    # Time-based counts
    now = datetime.utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=now.weekday())
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    jobs_today = db.query(func.count(Job.id)).filter(
        Job.created_at >= today_start
    ).scalar()

    jobs_this_week = db.query(func.count(Job.id)).filter(
        Job.created_at >= week_start
    ).scalar()

    jobs_this_month = db.query(func.count(Job.id)).filter(
        Job.created_at >= month_start
    ).scalar()

    # Processing metrics (only for completed jobs)
    completed_jobs = db.query(Job).filter(
        Job.status == JobStatus.COMPLETED
    ).all()

    avg_processing_time = None
    total_processing_time = None
    total_input_size = None
    total_output_size = None
    avg_compression_ratio = None

    if completed_jobs:
        processing_times = [
            job.processing_duration_seconds
            for job in completed_jobs
            if job.processing_duration_seconds is not None
        ]

        if processing_times:
            avg_processing_time = sum(processing_times) / len(processing_times)
            total_processing_time = sum(processing_times)

        input_sizes = [
            job.source_size_bytes
            for job in completed_jobs
            if job.source_size_bytes is not None
        ]

        if input_sizes:
            total_input_size = sum(input_sizes) / (1024**3)  # GB

        output_sizes = [
            job.output_total_size_bytes
            for job in completed_jobs
            if job.output_total_size_bytes is not None
        ]

        if output_sizes:
            total_output_size = sum(output_sizes) / (1024**3)  # GB

        compression_ratios = [
            float(job.compression_ratio)
            for job in completed_jobs
            if job.compression_ratio is not None
        ]

        if compression_ratios:
            avg_compression_ratio = sum(compression_ratios) / len(compression_ratios)

    # Success rate
    success_rate = None
    if total_jobs > 0:
        completed_count = jobs_by_status.get(JobStatus.COMPLETED.value, 0)
        failed_count = jobs_by_status.get(JobStatus.FAILED.value, 0)
        finished_jobs = completed_count + failed_count

        if finished_jobs > 0:
            success_rate = (completed_count / finished_jobs) * 100

    return JobStatsResponse(
        total_jobs=total_jobs,
        jobs_by_status=jobs_by_status,
        jobs_today=jobs_today,
        jobs_this_week=jobs_this_week,
        jobs_this_month=jobs_this_month,
        average_processing_time_seconds=avg_processing_time,
        total_processing_time_seconds=total_processing_time,
        total_input_size_gb=round(total_input_size, 2) if total_input_size else None,
        total_output_size_gb=round(total_output_size, 2) if total_output_size else None,
        average_compression_ratio=round(avg_compression_ratio, 2) if avg_compression_ratio else None,
        success_rate_percent=round(success_rate, 2) if success_rate else None,
    )


@router.post("/batch/status", response_model=BatchJobStatusResponse)
async def get_batch_job_status(
    request: BatchJobStatusRequest,
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key)
):
    """
    Get status for multiple jobs at once

    **Limits:**
    - Maximum 100 job IDs per request

    **Returns:**
    - List of found jobs
    - List of job IDs that were not found

    **Authentication:** Requires valid API key
    """
    # Query all jobs in the list
    jobs = db.query(Job).filter(Job.job_id.in_(request.job_ids)).all()

    # Find which job IDs were not found
    found_ids = {job.job_id for job in jobs}
    not_found = [jid for jid in request.job_ids if jid not in found_ids]

    return BatchJobStatusResponse(
        total=len(jobs),
        jobs=[JobResponse.from_orm(job) for job in jobs],
        not_found=not_found
    )


@router.post("/{job_id}/retry", response_model=JobRetryResponse)
async def retry_failed_job(
    job_id: str = Path(..., description="Job ID"),
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key)
):
    """
    Retry a failed job

    **Behavior:**
    - Only failed jobs can be retried
    - Job status is reset to 'pending'
    - Retry count is incremented
    - Job will be picked up by workers

    **Authentication:** Requires valid API key
    """
    job = db.query(Job).filter(Job.job_id == job_id).first()

    if not job:
        raise HTTPException(
            status_code=404,
            detail=f"Job '{job_id}' not found"
        )

    # Only failed jobs can be retried
    if job.status != JobStatus.FAILED:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot retry job with status '{job.status.value}'. Only failed jobs can be retried."
        )

    # Reset job status
    job.status = JobStatus.PENDING
    job.retry_count += 1
    job.error_message = None
    job.processing_started_at = None
    job.processing_completed_at = None
    job.processing_duration_seconds = None
    job.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(job)

    logger.info(f"Job {job_id} retried (attempt #{job.retry_count})")

    return JobRetryResponse(
        job_id=job_id,
        status=job.status,
        retry_count=job.retry_count,
        message=f"Job '{job_id}' has been queued for retry (attempt #{job.retry_count})"
    )


@router.patch("/{job_id}/priority", response_model=JobPriorityUpdateResponse)
async def update_job_priority(
    job_id: str = Path(..., description="Job ID"),
    request: JobPriorityUpdateRequest = ...,
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key)
):
    """
    Update job priority

    **Priority Levels:**
    - 1-3: Low priority
    - 4-6: Normal priority
    - 7-10: High priority

    **Note:** Priority changes only affect jobs in 'pending' or 'queued' status

    **Authentication:** Requires valid API key
    """
    job = db.query(Job).filter(Job.job_id == job_id).first()

    if not job:
        raise HTTPException(
            status_code=404,
            detail=f"Job '{job_id}' not found"
        )

    old_priority = job.priority

    # Update priority
    job.priority = request.priority
    job.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(job)

    logger.info(f"Job {job_id} priority changed from {old_priority} to {request.priority}")

    return JobPriorityUpdateResponse(
        job_id=job_id,
        old_priority=old_priority,
        new_priority=request.priority,
        message=f"Job priority updated from {old_priority} to {request.priority}"
    )
