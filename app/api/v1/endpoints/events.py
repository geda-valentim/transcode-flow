"""
Server-Sent Events (SSE) endpoints for real-time job progress updates.
"""
import asyncio
import json
from fastapi import APIRouter, Depends, HTTPException
from sse_starlette.sse import EventSourceResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.job import Job, JobStatus
from app.models.api_key import APIKey
from app.core.security import get_api_key

router = APIRouter()


@router.get("/{job_id}/progress")
async def stream_job_progress(
    job_id: str,
    api_key: APIKey = Depends(get_api_key),
    db: Session = Depends(get_db),
):
    """
    Stream real-time job progress using Server-Sent Events (SSE).

    This endpoint establishes a persistent connection and streams progress updates
    every 2 seconds until the job completes, fails, or is cancelled.

    **Connection stays open** until job reaches terminal state.

    **Events sent:**
    - `progress`: Regular status updates with progress percentage
    - `complete`: Final event when job finishes (completed/failed/cancelled)

    **Usage Example (JavaScript):**
    ```javascript
    const eventSource = new EventSource('/api/v1/events/{job_id}/progress');

    eventSource.addEventListener('progress', (event) => {
        const data = JSON.parse(event.data);
        console.log(`Progress: ${data.progress}%`);
    });

    eventSource.addEventListener('complete', (event) => {
        const data = JSON.parse(event.data);
        console.log(`Job ${data.status}`);
        eventSource.close();
    });
    ```
    """
    # Verify job ownership
    job = db.query(Job).filter(
        Job.job_id == job_id,
        Job.api_key_id == api_key.id
    ).first()

    if not job:
        raise HTTPException(
            status_code=404,
            detail=f"Job '{job_id}' not found or access denied"
        )

    async def event_generator():
        """
        Generate Server-Sent Events for job progress.
        Polls database every 2 seconds until job completes.
        """
        try:
            while True:
                # Fetch latest job status (create new session for each query)
                from app.db import SessionLocal
                db_session = SessionLocal()

                try:
                    job = db_session.query(Job).filter(
                        Job.job_id == job_id,
                        Job.api_key_id == api_key.id
                    ).first()

                    if not job:
                        # Job was deleted
                        yield {
                            "event": "error",
                            "data": json.dumps({
                                "job_id": job_id,
                                "error": "Job not found or was deleted"
                            })
                        }
                        break

                    # Calculate overall progress based on status
                    overall_progress = calculate_overall_progress(job)

                    # Send progress update
                    yield {
                        "event": "progress",
                        "data": json.dumps({
                            "job_id": job_id,
                            "status": job.status.value,
                            "priority": job.priority,
                            "progress": overall_progress,
                            "source_filename": job.source_filename,
                            "source_duration_seconds": float(job.source_duration_seconds) if job.source_duration_seconds else None,
                            "processing_started_at": job.processing_started_at.isoformat() if job.processing_started_at else None,
                            "updated_at": job.updated_at.isoformat() if job.updated_at else None,
                        })
                    }

                    # Check if job reached terminal state
                    if job.status in [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED]:
                        # Send final completion event
                        completion_data = {
                            "job_id": job_id,
                            "status": job.status.value,
                            "processing_completed_at": job.processing_completed_at.isoformat() if job.processing_completed_at else None,
                            "processing_duration_seconds": job.processing_duration_seconds,
                        }

                        if job.status == JobStatus.COMPLETED:
                            completion_data["outputs"] = {
                                "hls_manifest_url": job.hls_manifest_url,
                                "audio_file_url": job.audio_file_url,
                                "transcription_url": job.transcription_url,
                                "thumbnail_url": job.thumbnail_url,
                            }
                        elif job.status == JobStatus.FAILED:
                            completion_data["error_message"] = job.error_message
                            completion_data["retry_count"] = job.retry_count

                        yield {
                            "event": "complete",
                            "data": json.dumps(completion_data)
                        }

                        break

                finally:
                    db_session.close()

                # Wait 2 seconds before next update
                await asyncio.sleep(2)

        except asyncio.CancelledError:
            # Client disconnected
            pass
        except Exception as e:
            # Log error and send error event
            print(f"❌ SSE error for job {job_id}: {str(e)}")
            yield {
                "event": "error",
                "data": json.dumps({
                    "job_id": job_id,
                    "error": "Internal server error"
                })
            }

    return EventSourceResponse(event_generator())


def calculate_overall_progress(job: Job) -> float:
    """
    Calculate overall progress percentage based on job status.

    Progress estimation:
    - PENDING: 0%
    - QUEUED: 5%
    - PROCESSING: 10-90% (depends on processing stage)
    - COMPLETED: 100%
    - FAILED/CANCELLED: Last known progress
    """
    if job.status == JobStatus.PENDING:
        return 0.0
    elif job.status == JobStatus.QUEUED:
        return 5.0
    elif job.status == JobStatus.PROCESSING:
        # Base processing progress at 10%
        # Could be enhanced with actual task progress if available
        return 50.0  # Mid-point estimate
    elif job.status == JobStatus.COMPLETED:
        return 100.0
    elif job.status in [JobStatus.FAILED, JobStatus.CANCELLED]:
        # Return last known progress or 0
        return 0.0
    else:
        return 0.0
