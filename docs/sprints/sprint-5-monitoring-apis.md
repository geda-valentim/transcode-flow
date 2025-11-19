# Sprint 5: Job Status & Monitoring APIs (Week 6)

**Goal:** Implement comprehensive job monitoring and status APIs

**Duration:** 1 week
**Team Size:** 2 developers

---

## Tasks

- [ ] Implement GET /jobs/{job_id} endpoint
- [ ] Implement GET /jobs (list with filtering/pagination)
- [ ] Implement DELETE /jobs/{job_id} endpoint
- [ ] Implement POST /jobs/{job_id}/cancel endpoint
- [ ] Add real-time progress tracking endpoint (SSE or WebSocket)
- [ ] Implement job statistics endpoint
- [ ] Add batch job status endpoint
- [ ] Implement job retry functionality
- [ ] Add job priority update endpoint
- [ ] Implement webhook notifications
- [ ] Add job search with filters (status, date range, priority)
- [ ] Implement job export (CSV, JSON)
- [ ] Add API usage statistics endpoint
- [ ] Implement rate limiting enforcement
- [ ] Add health check endpoint with detailed status

---

## Deliverables

- ✅ Complete job monitoring API
- ✅ Real-time progress updates working
- ✅ Webhook notifications functional
- ✅ Job search and filtering working
- ✅ Health check endpoint comprehensive

---

## Acceptance Criteria

- [ ] Can retrieve job status and progress
- [ ] Can list jobs with pagination (100 items per page)
- [ ] Can filter jobs by status, date, priority
- [ ] Can cancel running jobs
- [ ] Real-time progress updates available
- [ ] Webhooks fire on job completion/failure
- [ ] Health check returns all service statuses
- [ ] Rate limiting blocks excessive requests

---

## Technical Details

### Job Status Endpoint

```python
# api/routes/jobs.py

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional, List
from datetime import datetime
from models import Job
from schemas import JobDetailResponse, JobListResponse

router = APIRouter(prefix="/jobs", tags=["jobs"])

@router.get("/{job_id}", response_model=JobDetailResponse)
async def get_job_status(
    job_id: str,
    api_key: str = Depends(verify_api_key)
):
    """Get detailed job status and outputs"""

    job = db.query(Job).filter(Job.id == job_id).first()

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Verify ownership
    if job.api_key != api_key:
        raise HTTPException(status_code=403, detail="Access denied")

    return {
        "job_id": job.id,
        "status": job.status,
        "priority": job.priority,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
        "completed_at": job.completed_at,

        # Progress tracking
        "progress": {
            "current_task": job.current_task,
            "current_task_progress": job.current_task_progress,
            "overall_progress": calculate_overall_progress(job),
            "eta_seconds": estimate_eta(job)
        },

        # Source info
        "source": {
            "filename": job.original_filename,
            "size_bytes": job.source_size_bytes,
            "duration_seconds": job.duration_seconds,
            "resolution": f"{job.source_width}x{job.source_height}",
            "codec": job.source_codec,
            "file_hash": job.source_file_hash
        },

        # Outputs
        "outputs": {
            "360p": {
                "available": job.output_360p_path is not None,
                "size_bytes": job.output_360p_size_bytes,
                "compression_ratio": job.compression_ratio_360p,
                "download_url": f"/jobs/{job_id}/download/360p" if job.status == 'completed' else None
            },
            "720p": {
                "available": job.output_720p_path is not None,
                "size_bytes": job.output_720p_size_bytes,
                "compression_ratio": job.compression_ratio_720p,
                "download_url": f"/jobs/{job_id}/download/720p" if job.status == 'completed' else None
            },
            "audio": {
                "available": job.output_audio_path is not None,
                "size_bytes": job.output_audio_size_bytes,
                "download_url": f"/jobs/{job_id}/download/audio" if job.status == 'completed' else None
            },
            "transcription": {
                "available": job.transcription_txt_path is not None,
                "language": job.transcription_language,
                "word_count": job.transcription_word_count,
                "whisper_model": job.whisper_model,
                "formats": {
                    "txt": f"/jobs/{job_id}/download/transcript_txt" if job.status == 'completed' else None,
                    "srt": f"/jobs/{job_id}/download/transcript_srt" if job.status == 'completed' else None,
                    "vtt": f"/jobs/{job_id}/download/transcript_vtt" if job.status == 'completed' else None,
                    "json": f"/jobs/{job_id}/download/transcript_json" if job.status == 'completed' else None
                }
            },
            "hls": {
                "360p": {
                    "available": job.output_hls_360p_path is not None,
                    "segments_count": job.segments_360p_count,
                    "playlist_url": f"/stream/{job_id}/360p/playlist.m3u8" if job.status == 'completed' else None
                },
                "720p": {
                    "available": job.output_hls_720p_path is not None,
                    "segments_count": job.segments_720p_count,
                    "playlist_url": f"/stream/{job_id}/720p/playlist.m3u8" if job.status == 'completed' else None
                }
            }
        },

        # Processing metrics
        "processing_time": {
            "validation_seconds": job.validation_time_seconds,
            "transcode_360p_seconds": job.transcode_360p_time_seconds,
            "transcode_720p_seconds": job.transcode_720p_time_seconds,
            "audio_extraction_seconds": job.audio_extraction_time_seconds,
            "transcription_seconds": job.transcription_time_seconds,
            "total_seconds": job.total_processing_time_seconds
        },

        # User metadata
        "user_metadata": job.user_metadata,

        # Error info (if failed)
        "error": {
            "message": job.error_message,
            "failed_task": job.failed_task,
            "retry_count": job.retry_count
        } if job.status == 'failed' else None
    }

def calculate_overall_progress(job: Job) -> int:
    """Calculate overall progress percentage"""

    if job.status == 'completed':
        return 100

    if job.status in ['queued', 'pending']:
        return 0

    # Weight each task
    task_weights = {
        'validate_video': 5,
        'upload_to_minio': 5,
        'generate_thumbnail': 5,
        'transcode_360p': 25,
        'transcode_720p': 25,
        'extract_audio_mp3': 10,
        'transcribe_video': 15,
        'prepare_hls': 5,
        'upload_outputs': 5
    }

    # TODO: Implement based on completed tasks
    # For now, return current task progress
    return job.current_task_progress or 0

def estimate_eta(job: Job) -> Optional[int]:
    """Estimate remaining time in seconds"""

    if job.status == 'completed':
        return 0

    if not job.duration_seconds:
        return None

    # Rough estimate: processing time ≈ video duration
    # (Will be refined with actual metrics)
    estimated_total = job.duration_seconds * 1.5  # 1.5x video duration

    elapsed = (datetime.now() - job.created_at).total_seconds()
    remaining = max(0, estimated_total - elapsed)

    return int(remaining)
```

---

### List Jobs Endpoint

```python
@router.get("/", response_model=JobListResponse)
async def list_jobs(
    api_key: str = Depends(verify_api_key),
    status: Optional[str] = Query(None, description="Filter by status"),
    priority: Optional[int] = Query(None, description="Filter by priority"),
    from_date: Optional[datetime] = Query(None, description="Filter from date"),
    to_date: Optional[datetime] = Query(None, description="Filter to date"),
    search: Optional[str] = Query(None, description="Search filename"),
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(100, ge=1, le=500, description="Items per page"),
    sort_by: str = Query("created_at", description="Sort field"),
    sort_order: str = Query("desc", description="Sort order (asc/desc)")
):
    """List jobs with filtering, search, and pagination"""

    query = db.query(Job).filter(Job.api_key == api_key)

    # Apply filters
    if status:
        query = query.filter(Job.status == status)

    if priority:
        query = query.filter(Job.priority == priority)

    if from_date:
        query = query.filter(Job.created_at >= from_date)

    if to_date:
        query = query.filter(Job.created_at <= to_date)

    if search:
        query = query.filter(Job.original_filename.ilike(f"%{search}%"))

    # Count total
    total = query.count()

    # Apply sorting
    if sort_order == "desc":
        query = query.order_by(getattr(Job, sort_by).desc())
    else:
        query = query.order_by(getattr(Job, sort_by).asc())

    # Apply pagination
    offset = (page - 1) * per_page
    jobs = query.offset(offset).limit(per_page).all()

    return {
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": (total + per_page - 1) // per_page,
        "jobs": [
            {
                "job_id": job.id,
                "status": job.status,
                "priority": job.priority,
                "filename": job.original_filename,
                "duration_seconds": job.duration_seconds,
                "created_at": job.created_at,
                "completed_at": job.completed_at,
                "progress": job.current_task_progress
            }
            for job in jobs
        ]
    }
```

---

### Real-Time Progress Updates (Server-Sent Events)

```python
# api/routes/events.py

from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse
import asyncio

router = APIRouter(prefix="/events", tags=["events"])

@router.get("/{job_id}/progress")
async def stream_job_progress(
    job_id: str,
    api_key: str = Depends(verify_api_key)
):
    """Stream real-time job progress using Server-Sent Events"""

    # Verify job ownership
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job or job.api_key != api_key:
        raise HTTPException(status_code=403, detail="Access denied")

    async def event_generator():
        while True:
            # Fetch latest job status
            job = db.query(Job).filter(Job.id == job_id).first()

            if not job:
                break

            # Send progress update
            yield {
                "event": "progress",
                "data": json.dumps({
                    "job_id": job_id,
                    "status": job.status,
                    "current_task": job.current_task,
                    "progress": job.current_task_progress,
                    "overall_progress": calculate_overall_progress(job),
                    "updated_at": job.updated_at.isoformat()
                })
            }

            # Stop if job completed or failed
            if job.status in ['completed', 'failed', 'cancelled']:
                yield {
                    "event": "complete",
                    "data": json.dumps({
                        "job_id": job_id,
                        "status": job.status,
                        "completed_at": job.completed_at.isoformat() if job.completed_at else None
                    })
                }
                break

            # Wait before next update
            await asyncio.sleep(2)

    return EventSourceResponse(event_generator())
```

**Client Usage Example:**

```javascript
// JavaScript client
const eventSource = new EventSource(`/events/${jobId}/progress?api_key=${apiKey}`);

eventSource.addEventListener('progress', (event) => {
    const data = JSON.parse(event.data);
    console.log(`Progress: ${data.progress}%`);
    updateProgressBar(data.progress);
});

eventSource.addEventListener('complete', (event) => {
    const data = JSON.parse(event.data);
    console.log(`Job ${data.status}`);
    eventSource.close();
});
```

---

### Cancel Job Endpoint

```python
@router.post("/{job_id}/cancel")
async def cancel_job(
    job_id: str,
    api_key: str = Depends(verify_api_key)
):
    """Cancel a running job"""

    job = db.query(Job).filter(Job.id == job_id).first()

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.api_key != api_key:
        raise HTTPException(status_code=403, detail="Access denied")

    if job.status not in ['queued', 'processing', 'transcoding', 'uploading']:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel job with status: {job.status}"
        )

    # Update job status
    job.status = 'cancelled'
    job.updated_at = datetime.now()

    db.commit()

    # Try to stop Airflow DAG run
    try:
        airflow_client.cancel_dag_run(
            dag_id='video_transcoding_pipeline',
            run_id=job.airflow_run_id
        )
    except Exception as e:
        print(f"Failed to cancel Airflow DAG: {e}")

    return {
        "job_id": job_id,
        "status": "cancelled",
        "message": "Job cancellation requested"
    }
```

---

### Delete Job Endpoint

```python
@router.delete("/{job_id}")
async def delete_job(
    job_id: str,
    api_key: str = Depends(verify_api_key),
    delete_files: bool = Query(True, description="Delete output files from storage")
):
    """Delete a job and optionally its output files"""

    job = db.query(Job).filter(Job.id == job_id).first()

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.api_key != api_key:
        raise HTTPException(status_code=403, detail="Access denied")

    # Delete files from MinIO
    if delete_files:
        objects = minio_client.list_objects(
            "videos",
            prefix=f"processed/{job_id}/",
            recursive=True
        )

        deleted_count = 0
        for obj in objects:
            minio_client.remove_object("videos", obj.object_name)
            deleted_count += 1

    # Delete job from database
    db.delete(job)
    db.commit()

    return {
        "job_id": job_id,
        "deleted": True,
        "files_deleted": deleted_count if delete_files else 0
    }
```

---

### Webhook Notifications

```python
# webhooks/notifications.py

import requests
from models import ApiKey, Job

class WebhookNotifier:
    def __init__(self, db_session):
        self.db = db_session

    def send_notification(self, job: Job, event: str):
        """
        Send webhook notification

        Events: job.completed, job.failed, job.progress
        """

        # Get API key webhook URL
        api_key = self.db.query(ApiKey).filter(
            ApiKey.key_hash == job.api_key
        ).first()

        if not api_key.webhook_url:
            return  # No webhook configured

        # Prepare payload
        payload = {
            "event": event,
            "job_id": job.id,
            "status": job.status,
            "timestamp": datetime.now().isoformat(),
            "data": {
                "filename": job.original_filename,
                "duration_seconds": job.duration_seconds,
                "progress": job.current_task_progress
            }
        }

        if event == "job.completed":
            payload["data"]["outputs"] = {
                "360p": f"/jobs/{job.id}/download/360p",
                "720p": f"/jobs/{job.id}/download/720p",
                "audio": f"/jobs/{job.id}/download/audio",
                "transcription": {
                    "txt": f"/jobs/{job.id}/download/transcript_txt",
                    "srt": f"/jobs/{job.id}/download/transcript_srt",
                    "vtt": f"/jobs/{job.id}/download/transcript_vtt"
                }
            }

        if event == "job.failed":
            payload["data"]["error"] = job.error_message

        # Send webhook
        try:
            response = requests.post(
                api_key.webhook_url,
                json=payload,
                headers={
                    "X-Webhook-Signature": self.generate_signature(payload, api_key.webhook_secret),
                    "Content-Type": "application/json"
                },
                timeout=10
            )

            response.raise_for_status()

            print(f"✅ Webhook sent: {event} for job {job.id}")

        except Exception as e:
            print(f"❌ Webhook failed: {e}")
            # Log webhook failure but don't raise exception

    def generate_signature(self, payload: dict, secret: str) -> str:
        """Generate HMAC signature for webhook verification"""

        import hmac
        import hashlib

        message = json.dumps(payload, sort_keys=True).encode()
        signature = hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()

        return signature
```

**Update API Key Table:**

```sql
ALTER TABLE api_keys
ADD COLUMN webhook_url TEXT DEFAULT NULL,
ADD COLUMN webhook_secret VARCHAR(64) DEFAULT NULL,
ADD COLUMN webhook_events TEXT[] DEFAULT ARRAY['job.completed', 'job.failed'];
```

**Usage in DAG:**

```python
# In update_database task
def update_database_task(**context):
    job_id = context['dag_run'].conf['job_id']
    job = get_job(job_id)

    # Update job status
    job.status = 'completed'
    job.completed_at = datetime.now()
    db.commit()

    # Send webhook notification
    notifier = WebhookNotifier(db)
    notifier.send_notification(job, 'job.completed')
```

---

### Statistics Endpoint

```python
@router.get("/stats")
async def get_statistics(
    api_key: str = Depends(verify_api_key),
    from_date: Optional[datetime] = Query(None),
    to_date: Optional[datetime] = Query(None)
):
    """Get job statistics for this API key"""

    query = db.query(Job).filter(Job.api_key == api_key)

    if from_date:
        query = query.filter(Job.created_at >= from_date)

    if to_date:
        query = query.filter(Job.created_at <= to_date)

    # Job counts by status
    status_counts = {}
    for status in ['queued', 'processing', 'completed', 'failed', 'cancelled']:
        count = query.filter(Job.status == status).count()
        status_counts[status] = count

    # Total processing time
    completed_jobs = query.filter(Job.status == 'completed').all()

    total_processing_time = sum(
        job.total_processing_time_seconds or 0
        for job in completed_jobs
    )

    total_video_duration = sum(
        job.duration_seconds or 0
        for job in completed_jobs
    )

    # Storage usage
    quota_manager = StorageQuotaManager(db)
    storage_usage = quota_manager.get_usage(api_key)

    # Average processing time
    avg_processing_time = (
        total_processing_time / len(completed_jobs)
        if completed_jobs else 0
    )

    return {
        "total_jobs": query.count(),
        "status_breakdown": status_counts,
        "success_rate": (
            status_counts['completed'] / query.count() * 100
            if query.count() > 0 else 0
        ),
        "processing_metrics": {
            "total_processing_time_seconds": total_processing_time,
            "total_processing_time_hours": round(total_processing_time / 3600, 2),
            "total_video_duration_seconds": total_video_duration,
            "total_video_duration_hours": round(total_video_duration / 3600, 2),
            "average_processing_time_seconds": round(avg_processing_time, 2),
            "processing_efficiency": round(
                total_video_duration / total_processing_time * 100
                if total_processing_time > 0 else 0,
                2
            )
        },
        "storage": storage_usage,
        "date_range": {
            "from": from_date.isoformat() if from_date else None,
            "to": to_date.isoformat() if to_date else None
        }
    }
```

---

### Health Check Endpoint

```python
# api/routes/health.py

from fastapi import APIRouter
import psycopg2
import redis

router = APIRouter(prefix="/health", tags=["health"])

@router.get("/")
async def health_check():
    """Basic health check"""
    return {"status": "healthy"}

@router.get("/detailed")
async def detailed_health_check():
    """Detailed health check of all services"""

    status = {
        "overall": "healthy",
        "services": {}
    }

    # Check PostgreSQL
    try:
        conn = psycopg2.connect(
            host=os.getenv("POSTGRES_HOST"),
            database=os.getenv("POSTGRES_DB"),
            user=os.getenv("POSTGRES_USER"),
            password=os.getenv("POSTGRES_PASSWORD")
        )
        conn.close()
        status["services"]["postgresql"] = {"status": "healthy"}
    except Exception as e:
        status["services"]["postgresql"] = {"status": "unhealthy", "error": str(e)}
        status["overall"] = "degraded"

    # Check Redis
    try:
        r = redis.Redis(host='redis', port=6379, db=0)
        r.ping()
        status["services"]["redis"] = {"status": "healthy"}
    except Exception as e:
        status["services"]["redis"] = {"status": "unhealthy", "error": str(e)}
        status["overall"] = "degraded"

    # Check MinIO
    try:
        minio_client.list_buckets()
        status["services"]["minio"] = {"status": "healthy"}
    except Exception as e:
        status["services"]["minio"] = {"status": "unhealthy", "error": str(e)}
        status["overall"] = "degraded"

    # Check Airflow
    try:
        response = requests.get("http://airflow-webserver:8080/health")
        if response.status_code == 200:
            status["services"]["airflow"] = {"status": "healthy"}
        else:
            status["services"]["airflow"] = {"status": "unhealthy"}
            status["overall"] = "degraded"
    except Exception as e:
        status["services"]["airflow"] = {"status": "unhealthy", "error": str(e)}
        status["overall"] = "degraded"

    # Check disk space
    disk_usage = shutil.disk_usage("/data")
    free_percent = disk_usage.free / disk_usage.total * 100

    status["services"]["disk"] = {
        "status": "healthy" if free_percent > 10 else "warning",
        "total_gb": round(disk_usage.total / (1024**3), 2),
        "used_gb": round(disk_usage.used / (1024**3), 2),
        "free_gb": round(disk_usage.free / (1024**3), 2),
        "free_percent": round(free_percent, 2)
    }

    if free_percent < 10:
        status["overall"] = "warning"

    return status
```

---

## Testing

```python
# tests/test_monitoring_apis.py

def test_get_job_status():
    """Test job status endpoint"""
    response = client.get(f"/jobs/{job_id}", headers={"X-API-Key": api_key})

    assert response.status_code == 200
    data = response.json()
    assert data["job_id"] == job_id
    assert "progress" in data
    assert "outputs" in data

def test_list_jobs_pagination():
    """Test job listing with pagination"""
    response = client.get("/jobs?page=1&per_page=10", headers={"X-API-Key": api_key})

    assert response.status_code == 200
    data = response.json()
    assert data["page"] == 1
    assert data["per_page"] == 10
    assert len(data["jobs"]) <= 10

def test_list_jobs_filtering():
    """Test job filtering"""
    response = client.get("/jobs?status=completed", headers={"X-API-Key": api_key})

    assert response.status_code == 200
    data = response.json()
    for job in data["jobs"]:
        assert job["status"] == "completed"

def test_cancel_job():
    """Test job cancellation"""
    response = client.post(f"/jobs/{job_id}/cancel", headers={"X-API-Key": api_key})

    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"

    # Verify in database
    job = db.query(Job).filter(Job.id == job_id).first()
    assert job.status == "cancelled"

def test_delete_job():
    """Test job deletion"""
    response = client.delete(f"/jobs/{job_id}", headers={"X-API-Key": api_key})

    assert response.status_code == 200

    # Verify job deleted
    job = db.query(Job).filter(Job.id == job_id).first()
    assert job is None

def test_webhook_notification():
    """Test webhook notification"""
    # Set webhook URL
    api_key_obj.webhook_url = "http://example.com/webhook"
    db.commit()

    # Complete a job
    job.status = 'completed'
    job.completed_at = datetime.now()
    db.commit()

    # Send notification
    notifier = WebhookNotifier(db)
    notifier.send_notification(job, 'job.completed')

    # Verify webhook was called (mock)
    # assert webhook_mock.called

def test_statistics():
    """Test statistics endpoint"""
    response = client.get("/jobs/stats", headers={"X-API-Key": api_key})

    assert response.status_code == 200
    data = response.json()
    assert "total_jobs" in data
    assert "status_breakdown" in data
    assert "processing_metrics" in data
    assert "storage" in data

def test_health_check():
    """Test health check endpoint"""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"

def test_detailed_health_check():
    """Test detailed health check"""
    response = client.get("/health/detailed")
    assert response.status_code == 200

    data = response.json()
    assert "overall" in data
    assert "services" in data
    assert "postgresql" in data["services"]
    assert "redis" in data["services"]
    assert "minio" in data["services"]
```

---

## Performance Targets

| Endpoint | Target Time | Max Time |
|----------|-------------|----------|
| GET /jobs/{job_id} | < 50ms | < 100ms |
| GET /jobs (list) | < 100ms | < 200ms |
| POST /jobs/{job_id}/cancel | < 100ms | < 200ms |
| DELETE /jobs/{job_id} | < 500ms | < 1s |
| GET /jobs/stats | < 200ms | < 500ms |
| GET /health | < 10ms | < 50ms |
| GET /health/detailed | < 200ms | < 500ms |

---

## Next Sprint

Sprint 6: Monitoring & Observability
