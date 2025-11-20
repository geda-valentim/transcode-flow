"""
Database Tasks

Tasks related to database updates and cleanup operations.
"""
import os
import logging
import shutil
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)


def update_database_task(**context):
    """
    Task 10: Update job status to COMPLETED

    - Marks job as completed
    - Stores all MinIO output paths in job metadata
    - Records completion timestamp
    - Updates task statistics
    """
    from app.db import SessionLocal
    from app.models.job import Job, JobStatus

    job_id = context['dag_run'].conf.get('job_id')
    logger.info(f"[Task 10] Updating database for job {job_id}")

    db = SessionLocal()
    try:
        job = db.query(Job).filter(Job.job_id == job_id).first()
        if not job:
            raise ValueError(f"Job {job_id} not found")

        # Get uploaded file paths from XCom
        uploaded_files = context['task_instance'].xcom_pull(key='uploaded_files')

        # Update job status
        job.status = JobStatus.COMPLETED
        job.processing_completed_at = datetime.utcnow()

        # Store output paths in job metadata
        if not job.job_metadata:
            job.job_metadata = {}

        job.job_metadata['outputs'] = uploaded_files
        job.job_metadata['completed_at'] = job.processing_completed_at.isoformat()

        # Calculate processing time
        if job.processing_started_at:
            processing_time = (job.processing_completed_at - job.processing_started_at).total_seconds()
            job.job_metadata['processing_time_seconds'] = processing_time
            logger.info(f"[Task 10] Processing time: {processing_time:.2f}s")

        db.commit()
        logger.info(f"[Task 10] Job {job_id} marked as COMPLETED")

    except Exception as e:
        logger.error(f"[Task 10] Database update failed: {e}")
        raise
    finally:
        db.close()


def cleanup_temp_files_task(**context):
    """
    Task 11: Clean up temporary files

    - Removes all files in /data/temp/{job_id}/
    - Keeps MinIO storage intact
    - Logs cleanup statistics
    """
    job_id = context['dag_run'].conf.get('job_id')
    logger.info(f"[Task 11] Cleaning up temporary files for job {job_id}")

    try:
        temp_dir = Path(f"/data/temp/{job_id}")

        if not temp_dir.exists():
            logger.warning(f"[Task 11] Temp directory does not exist: {temp_dir}")
            return

        # Calculate total size before cleanup
        total_size = sum(
            f.stat().st_size for f in temp_dir.rglob('*') if f.is_file()
        )
        total_size_mb = total_size / (1024 * 1024)

        # Count files
        file_count = sum(1 for f in temp_dir.rglob('*') if f.is_file())

        # Remove directory and all contents
        shutil.rmtree(temp_dir)

        logger.info(
            f"[Task 11] Cleaned up {file_count} files "
            f"({total_size_mb:.2f} MB) from {temp_dir}"
        )

    except Exception as e:
        logger.error(f"[Task 11] Cleanup failed: {e}")
        # Don't raise - cleanup failure shouldn't fail the entire pipeline
        logger.warning("[Task 11] Continuing despite cleanup failure")
