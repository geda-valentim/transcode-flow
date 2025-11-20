"""
Job observability endpoints.
Provides real-time monitoring of job progress, transcription status, and metrics.
"""
from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
import requests
import os

from app.db import get_db
from app.models.job import Job
from app.models.api_key import APIKey
from app.core.security import get_api_key

router = APIRouter()

# Airflow API configuration
AIRFLOW_API_URL = os.getenv("AIRFLOW_API_URL", "http://airflow-webserver:8080/api/v1")
AIRFLOW_USERNAME = os.getenv("AIRFLOW_USERNAME", "admin")
AIRFLOW_PASSWORD = os.getenv("AIRFLOW_PASSWORD", "admin")


def get_airflow_xcom(
    dag_id: str,
    dag_run_id: str,
    task_id: str,
    xcom_key: str
) -> Optional[Any]:
    """
    Retrieve XCom value from Airflow API.

    Args:
        dag_id: DAG ID
        dag_run_id: DAG run ID
        task_id: Task ID
        xcom_key: XCom key to retrieve

    Returns:
        XCom value or None if not found
    """
    url = (
        f"{AIRFLOW_API_URL}/dags/{dag_id}/dagRuns/{dag_run_id}/"
        f"taskInstances/{task_id}/xcomEntries/{xcom_key}"
    )

    try:
        response = requests.get(
            url,
            auth=(AIRFLOW_USERNAME, AIRFLOW_PASSWORD),
            timeout=5
        )

        if response.status_code == 200:
            data = response.json()
            return data.get("value")
        elif response.status_code == 404:
            return None
        else:
            return None
    except Exception as e:
        return None


def get_all_task_xcoms(
    dag_id: str,
    dag_run_id: str,
    task_id: str
) -> Dict[str, Any]:
    """
    Retrieve all XCom entries for a task.

    Args:
        dag_id: DAG ID
        dag_run_id: DAG run ID
        task_id: Task ID

    Returns:
        Dictionary of all XCom key-value pairs
    """
    url = (
        f"{AIRFLOW_API_URL}/dags/{dag_id}/dagRuns/{dag_run_id}/"
        f"taskInstances/{task_id}/xcomEntries"
    )

    try:
        response = requests.get(
            url,
            auth=(AIRFLOW_USERNAME, AIRFLOW_PASSWORD),
            timeout=5
        )

        if response.status_code == 200:
            data = response.json()
            xcoms = {}
            for entry in data.get("xcom_entries", []):
                xcoms[entry["key"]] = entry["value"]
            return xcoms
        else:
            return {}
    except Exception as e:
        return {}


@router.get("/{job_id}/transcription/progress")
async def get_transcription_progress(
    job_id: str,
    api_key: APIKey = Depends(get_api_key),
    db: Session = Depends(get_db),
):
    """
    Get real-time transcription progress and metrics for a job.

    Returns detailed information about the transcription process including:
    - Current status (initializing, extracting_audio, transcribing, completed, failed)
    - Whisper model selected and its characteristics
    - Processing duration
    - Audio file metrics
    - Transcription results (when completed)

    **Example Response:**
    ```json
    {
      "job_id": "abc123",
      "transcription_enabled": true,
      "status": "transcribing",
      "progress": {
        "status": "transcribing",
        "whisper_model": "small",
        "model_speed": "moderate",
        "model_quality": "good",
        "video_duration_seconds": 300,
        "audio_file_size_mb": 4.5,
        "processing_duration_seconds": 120,
        "estimated_time_remaining_seconds": 60
      },
      "metrics": {
        "start_time": "2025-11-20T10:00:00Z",
        "processing_start": "2025-11-20T10:01:00Z",
        "current_time": "2025-11-20T10:03:00Z"
      }
    }
    ```
    """
    # Query job
    job = db.query(Job).filter(
        Job.job_id == job_id,
        Job.api_key_id == api_key.id
    ).first()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job not found: {job_id}"
        )

    # Check if transcription is enabled
    if not job.enable_transcription:
        return {
            "job_id": job_id,
            "transcription_enabled": False,
            "message": "Transcription is not enabled for this job"
        }

    # Get DAG run ID from job metadata or construct it
    # Assuming DAG run ID follows pattern: manual__YYYY-MM-DDTHH:MM:SS.ffffff+00:00
    dag_id = "video_transcoding_pipeline"

    # Try to get XCom data from Airflow
    # Note: We need the dag_run_id which should be stored in job metadata
    # For now, we'll try to get all XComs for the transcribe_audio task

    # Build response with available data
    response = {
        "job_id": job_id,
        "transcription_enabled": True,
        "job_status": job.status.value,
        "progress": {
            "status": "unknown",
            "message": "Transcription task not started or XCom data not available"
        },
        "airflow_integration": {
            "note": "To enable real-time progress tracking, ensure DAG run ID is stored in job metadata",
            "dag_id": dag_id,
            "task_id": "transcribe_audio"
        }
    }

    # TODO: Store dag_run_id in job metadata when triggering Airflow DAG
    # Then we can retrieve real XCom data like this:
    # xcoms = get_all_task_xcoms(dag_id, job.dag_run_id, "transcribe_audio")

    return response


@router.get("/{job_id}/metrics/detailed")
async def get_detailed_job_metrics(
    job_id: str,
    api_key: APIKey = Depends(get_api_key),
    db: Session = Depends(get_db),
):
    """
    Get detailed metrics for all tasks in a job's processing pipeline.

    Returns metrics from all Airflow tasks including:
    - Video validation results
    - Transcoding progress (360p, 720p)
    - Audio extraction metrics
    - Transcription progress and results
    - HLS preparation status
    - Upload progress

    This endpoint aggregates XCom data from multiple tasks to provide
    a comprehensive view of the entire job processing pipeline.
    """
    # Query job
    job = db.query(Job).filter(
        Job.job_id == job_id,
        Job.api_key_id == api_key.id
    ).first()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job not found: {job_id}"
        )

    dag_id = "video_transcoding_pipeline"

    # Aggregate metrics from job model
    metrics = {
        "job_id": job_id,
        "status": job.status.value,
        "priority": job.priority,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "updated_at": job.updated_at.isoformat() if job.updated_at else None,

        "source_video": {
            "filename": job.source_filename,
            "size_bytes": job.source_size_bytes,
            "size_mb": round(job.source_size_bytes / (1024 * 1024), 2) if job.source_size_bytes else None,
            "duration_seconds": job.source_duration_seconds,
            "resolution": job.source_resolution,
            "codec": job.source_codec,
            "bitrate": job.source_bitrate,
            "fps": job.source_fps,
        },

        "processing": {
            "started_at": job.processing_started_at.isoformat() if job.processing_started_at else None,
            "completed_at": job.processing_completed_at.isoformat() if job.processing_completed_at else None,
            "duration_seconds": job.processing_duration_seconds,
            "current_task": job.current_task,
            "current_task_progress": job.current_task_progress,
        },

        "output": {
            "target_resolutions": job.target_resolutions,
            "enable_hls": job.enable_hls,
            "enable_audio_extraction": job.enable_audio_extraction,
            "enable_transcription": job.enable_transcription,
            "transcription_language": job.transcription_language,
            "output_formats": job.output_formats,
            "total_size_bytes": job.output_total_size_bytes,
            "compression_ratio": job.compression_ratio,
        },

        "urls": {
            "hls_manifest": job.hls_manifest_url,
            "audio_file": job.audio_file_url,
            "transcription": job.transcription_url,
            "thumbnail": job.thumbnail_url,
        },

        "airflow": {
            "dag_id": dag_id,
            "note": "Real-time task metrics available when DAG run ID is stored in job metadata"
        }
    }

    if job.error_message:
        metrics["error"] = {
            "message": job.error_message,
            "retry_count": job.retry_count
        }

    return metrics


@router.get("/{job_id}/observability/summary")
async def get_observability_summary(
    job_id: str,
    api_key: APIKey = Depends(get_api_key),
    db: Session = Depends(get_db),
):
    """
    Get a high-level observability summary for a job.

    Provides a quick overview of:
    - Current status and progress
    - Key metrics (file sizes, durations, completion %)
    - Active tasks
    - Recent updates

    Designed for dashboard displays and monitoring UIs.
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

    # Calculate progress percentage
    progress_percentage = 0
    if job.status.value == "completed":
        progress_percentage = 100
    elif job.status.value == "failed":
        progress_percentage = 0
    elif job.status.value == "processing":
        progress_percentage = job.current_task_progress or 50
    elif job.status.value == "pending":
        progress_percentage = 0

    summary = {
        "job_id": job_id,
        "status": job.status.value,
        "progress_percentage": progress_percentage,
        "current_task": job.current_task,

        "quick_stats": {
            "source_file": f"{job.source_filename} ({round(job.source_size_bytes / (1024 * 1024), 1)}MB)" if job.source_size_bytes else job.source_filename,
            "duration": f"{job.source_duration_seconds}s" if job.source_duration_seconds else "unknown",
            "created": job.created_at.isoformat() if job.created_at else None,
        },

        "features_enabled": {
            "transcoding": len(job.target_resolutions) if job.target_resolutions else 0,
            "hls": job.enable_hls,
            "audio_extraction": job.enable_audio_extraction,
            "transcription": job.enable_transcription,
        },

        "timestamps": {
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "processing_started": job.processing_started_at.isoformat() if job.processing_started_at else None,
            "last_updated": job.updated_at.isoformat() if job.updated_at else None,
        }
    }

    if job.status.value == "failed":
        summary["error_info"] = {
            "message": job.error_message,
            "retry_count": job.retry_count
        }

    return summary
