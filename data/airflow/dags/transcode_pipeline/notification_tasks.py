"""
Notification Tasks

Tasks related to sending notifications and webhooks.
"""
import logging
import requests
from typing import Optional

logger = logging.getLogger(__name__)


def send_notification_task(**context):
    """
    Task 12: Send completion notification

    - Sends webhook to callback URL (if provided in job metadata)
    - Includes job_id, status, and output file paths
    - Non-blocking - failures don't affect job completion
    """
    from app.db import SessionLocal
    from app.models.job import Job

    job_id = context['dag_run'].conf.get('job_id')
    logger.info(f"[Task 12] Sending notification for job {job_id}")

    db = SessionLocal()
    try:
        job = db.query(Job).filter(Job.job_id == job_id).first()
        if not job:
            raise ValueError(f"Job {job_id} not found")

        # Check if callback URL is provided in job metadata
        callback_url = None
        if job.job_metadata and 'callback_url' in job.job_metadata:
            callback_url = job.job_metadata['callback_url']

        if not callback_url:
            logger.info(f"[Task 12] No callback URL provided for job {job_id}")
            return

        # Prepare notification payload
        payload = {
            'job_id': str(job.job_id),
            'status': job.status.value if hasattr(job.status, 'value') else str(job.status),
            'completed_at': job.processing_completed_at.isoformat() if job.processing_completed_at else None,
            'outputs': job.job_metadata.get('outputs', {}) if job.job_metadata else {},
            'processing_time_seconds': job.job_metadata.get('processing_time_seconds') if job.job_metadata else None,
            'video_info': {
                'duration_seconds': job.source_duration_seconds,
                'resolution': job.source_resolution,
                'size_bytes': job.source_size_bytes,
            }
        }

        # Send webhook notification
        logger.info(f"[Task 12] Sending webhook to {callback_url}")
        response = requests.post(
            callback_url,
            json=payload,
            timeout=10,
            headers={'Content-Type': 'application/json'}
        )

        if response.status_code in [200, 201, 202, 204]:
            logger.info(f"[Task 12] Webhook sent successfully: {response.status_code}")
        else:
            logger.warning(
                f"[Task 12] Webhook returned non-success status: "
                f"{response.status_code} - {response.text}"
            )

    except requests.RequestException as e:
        logger.error(f"[Task 12] Failed to send webhook: {e}")
        # Don't raise - notification failure shouldn't fail the job
        logger.warning("[Task 12] Continuing despite notification failure")
    except Exception as e:
        logger.error(f"[Task 12] Notification task failed: {e}")
        # Don't raise - notification failure shouldn't fail the job
        logger.warning("[Task 12] Continuing despite notification failure")
    finally:
        db.close()
