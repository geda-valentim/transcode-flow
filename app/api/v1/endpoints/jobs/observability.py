"""
Job observability endpoints.
Provides real-time monitoring of job progress, transcription status, and metrics.
"""
from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
import requests
import os
from datetime import datetime, timezone, timedelta

from app.db import get_db
from app.models.job import Job
from app.models.api_key import APIKey
from app.core.security import get_api_key

router = APIRouter()

# Airflow API configuration
# NOTE: Airflow 3.x uses /api/v2 (v1 was removed) and requires JWT authentication
AIRFLOW_API_URL = os.getenv("AIRFLOW_API_URL", "http://airflow-webserver:8080/api/v2")
AIRFLOW_AUTH_URL = os.getenv("AIRFLOW_AUTH_URL", "http://airflow-webserver:8080/auth/token")
AIRFLOW_USERNAME = os.getenv("AIRFLOW_ADMIN_USER", "admin")
AIRFLOW_PASSWORD = os.getenv("AIRFLOW_ADMIN_PASSWORD", "admin")

# Cache JWT token
_jwt_token_cache = {"token": None, "expires": None}


def get_jwt_token() -> str:
    """
    Get JWT token for Airflow API authentication with caching.

    Returns:
        str: JWT access token
    """
    # Check cache
    if _jwt_token_cache["token"] and _jwt_token_cache["expires"]:
        if datetime.now(timezone.utc) < _jwt_token_cache["expires"]:
            return _jwt_token_cache["token"]

    # Generate new token
    try:
        response = requests.post(
            AIRFLOW_AUTH_URL,
            json={
                "username": AIRFLOW_USERNAME,
                "password": AIRFLOW_PASSWORD
            },
            headers={"Content-Type": "application/json"},
            timeout=5
        )

        if response.status_code in (200, 201):
            token_data = response.json()
            token = token_data.get("access_token")

            # Cache for 50 minutes
            _jwt_token_cache["token"] = token
            _jwt_token_cache["expires"] = datetime.now(timezone.utc) + timedelta(minutes=50)

            return token
        else:
            raise Exception(f"Failed to get JWT token: {response.status_code}")
    except Exception as e:
        raise Exception(f"Error getting JWT token: {str(e)}")


def get_airflow_xcom(
    dag_id: str,
    dag_run_id: str,
    task_id: str,
    xcom_key: str
) -> Optional[Any]:
    """
    Retrieve XCom value from Airflow API using JWT authentication.

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
        token = get_jwt_token()
        response = requests.get(
            url,
            headers={"Authorization": f"Bearer {token}"},
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
    Retrieve all XCom entries for a task using JWT authentication.

    In Airflow 3.x API v2, XCom values must be fetched individually per key.

    Args:
        dag_id: DAG ID
        dag_run_id: DAG run ID
        task_id: Task ID

    Returns:
        Dictionary of all XCom key-value pairs
    """
    # First get list of XCom keys
    list_url = (
        f"{AIRFLOW_API_URL}/dags/{dag_id}/dagRuns/{dag_run_id}/"
        f"taskInstances/{task_id}/xcomEntries"
    )

    try:
        token = get_jwt_token()
        response = requests.get(
            list_url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=5
        )

        if response.status_code != 200:
            return {}

        data = response.json()
        xcoms = {}

        # Fetch each XCom value individually
        for entry in data.get("xcom_entries", []):
            key = entry.get("key")
            if not key:
                continue

            # Fetch individual XCom value
            value_url = (
                f"{AIRFLOW_API_URL}/dags/{dag_id}/dagRuns/{dag_run_id}/"
                f"taskInstances/{task_id}/xcomEntries/{key}"
            )

            try:
                value_response = requests.get(
                    value_url,
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=5
                )

                if value_response.status_code == 200:
                    value_data = value_response.json()
                    xcoms[key] = value_data.get("value")
            except:
                # Skip individual XCom if fetch fails
                continue

        return xcoms
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

    # Get DAG run ID from job metadata
    dag_id = "video_transcoding_pipeline"
    task_id = "transcribe_audio"

    # Check if dag_run_id is stored in job metadata
    dag_run_id = None
    if job.job_metadata and isinstance(job.job_metadata, dict):
        dag_run_id = job.job_metadata.get("dag_run_id")

    if not dag_run_id:
        return {
            "job_id": job_id,
            "transcription_enabled": True,
            "job_status": job.status.value,
            "progress": {
                "status": "not_started",
                "message": "DAG not triggered yet or dag_run_id not available"
            },
            "airflow_integration": {
                "dag_id": dag_id,
                "task_id": task_id,
                "note": "DAG run ID not found in job metadata"
            }
        }

    # Retrieve XCom data from Airflow
    xcoms = get_all_task_xcoms(dag_id, dag_run_id, task_id)

    # Parse XCom data to build progress response
    status_value = xcoms.get("transcription_status", "unknown")

    progress_data = {
        "status": status_value
    }

    # Helper function to extract numeric value from potential Decimal objects
    def extract_numeric_value(value):
        """Extract numeric value from Decimal objects or return as-is."""
        if isinstance(value, dict) and "__data__" in value:
            # Handle serialized Decimal from Airflow XCom
            return float(value["__data__"])
        return value

    # Add model information if available
    if "whisper_model_selected" in xcoms:
        progress_data["whisper_model"] = xcoms["whisper_model_selected"]
        progress_data["model_speed"] = xcoms.get("whisper_model_speed")
        progress_data["model_quality"] = xcoms.get("whisper_model_quality")

    # Add duration and processing metrics
    if "video_duration_seconds" in xcoms:
        progress_data["video_duration_seconds"] = extract_numeric_value(xcoms["video_duration_seconds"])

    if "audio_file_size_mb" in xcoms:
        progress_data["audio_file_size_mb"] = extract_numeric_value(xcoms["audio_file_size_mb"])

    # Calculate processing duration if available
    if status_value in ["transcribing", "completed"]:
        from datetime import datetime
        start_time_str = xcoms.get("transcription_processing_start")
        if start_time_str:
            try:
                start_time = datetime.fromisoformat(start_time_str.replace('Z', '+00:00'))

                if status_value == "completed":
                    end_time_str = xcoms.get("transcription_processing_end")
                    if end_time_str:
                        end_time = datetime.fromisoformat(end_time_str.replace('Z', '+00:00'))
                        duration = (end_time - start_time).total_seconds()
                        progress_data["processing_duration_seconds"] = round(duration, 2)
                else:
                    # Still processing - calculate elapsed time
                    from datetime import timezone
                    now = datetime.now(timezone.utc)
                    elapsed = (now - start_time).total_seconds()
                    progress_data["processing_duration_seconds"] = round(elapsed, 2)

                    # Estimate time remaining based on video duration
                    video_duration = progress_data.get("video_duration_seconds")
                    if video_duration:
                        # Whisper tiny typically processes at ~15x realtime
                        estimated_total = video_duration / 15
                        remaining = max(0, estimated_total - elapsed)
                        progress_data["estimated_time_remaining_seconds"] = round(remaining, 2)
            except:
                pass

    # Add completion metrics if available
    if status_value == "completed":
        if "transcription_text_length" in xcoms:
            progress_data["text_length_characters"] = xcoms["transcription_text_length"]
        if "transcription_segments_count" in xcoms:
            progress_data["segments_count"] = xcoms["transcription_segments_count"]
        if "transcription_detected_language" in xcoms:
            progress_data["detected_language"] = xcoms["transcription_detected_language"]

    # Build metrics section
    metrics = {}
    if "transcription_start_time" in xcoms:
        metrics["start_time"] = xcoms["transcription_start_time"]
    if "transcription_processing_start" in xcoms:
        metrics["processing_start"] = xcoms["transcription_processing_start"]
    if status_value == "completed" and "transcription_processing_end" in xcoms:
        metrics["processing_end"] = xcoms["transcription_processing_end"]

    response = {
        "job_id": job_id,
        "transcription_enabled": True,
        "job_status": job.status.value,
        "progress": progress_data,
        "airflow_integration": {
            "dag_id": dag_id,
            "dag_run_id": dag_run_id,
            "task_id": task_id
        }
    }

    if metrics:
        response["metrics"] = metrics

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
