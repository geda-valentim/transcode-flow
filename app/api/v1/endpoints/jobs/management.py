"""
Job management and control endpoints.
Handles job status retrieval, cancellation, retry, priority updates, and deletion.
"""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.job import Job, JobStatus
from app.models.api_key import APIKey
from app.schemas.job import JobResponse
from app.core.security import get_api_key

router = APIRouter()


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
