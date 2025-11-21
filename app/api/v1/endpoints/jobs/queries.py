"""
Job query and search endpoints.
Handles job listing, searching, batch status retrieval, and statistics.
"""
from typing import Optional, List
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, Body
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.job import Job, JobStatus
from app.models.api_key import APIKey
from app.schemas.job import JobResponse
from app.core.security import get_api_key

router = APIRouter()


@router.get("/", response_model=dict)
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
