"""
Validation Tasks

Tasks related to video validation and thumbnail generation.
"""
import os
import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


def validate_video_task(**context):
    """
    Task 1: Validate video file using FFprobe

    - Checks if file exists
    - Validates format, codec, resolution
    - Updates job status to PROCESSING
    - Stores video metadata in database
    """
    from datetime import datetime, timezone
    from pathlib import Path
    from app.db import SessionLocal
    from app.models.job import Job, JobStatus
    from app.services.video_validator import VideoValidator

    job_id = context['dag_run'].conf.get('job_id')
    video_path = context['dag_run'].conf.get('video_path')

    # Translate host path to container path if needed
    # Host: /home/transcode-flow/data/temp/ -> Container: /data/temp/
    if video_path.startswith('/home/transcode-flow/data/temp/'):
        container_path = video_path.replace('/home/transcode-flow/data/temp/', '/data/temp/')
        logger.info(f"[Task 1] Translated path: {video_path} -> {container_path}")
        video_path = container_path

    logger.info(f"[Task 1] Validating video for job {job_id}")

    db = SessionLocal()
    try:
        job = db.query(Job).filter(Job.job_id == job_id).first()
        if not job:
            # Create job if it doesn't exist (DAG creates job automatically)
            logger.info(f"[Task 1] Creating job {job_id} in database")
            job = Job(
                job_id=job_id,
                source_path=video_path,
                source_filename=Path(video_path).name,
                status=JobStatus.PENDING,
                created_at=datetime.now(timezone.utc)
            )
            db.add(job)
            db.commit()
            db.refresh(job)

        # Update status to processing
        job.status = JobStatus.PROCESSING
        db.commit()

        # Validate video file
        validator = VideoValidator()
        validation_result = validator.validate_file(job.source_path)

        if not validation_result.is_valid:
            job.status = JobStatus.FAILED
            error_msgs = ', '.join(validation_result.errors) if validation_result.errors else 'Video validation failed'
            job.error_message = error_msgs
            db.commit()
            raise ValueError(f"Video validation failed: {job.error_message}")

        # Update job with video info
        job.source_duration_seconds = validation_result.duration_seconds
        job.source_resolution = validation_result.resolution or f"{validation_result.width}x{validation_result.height}"
        job.source_size_bytes = validation_result.size_bytes
        job.source_codec = validation_result.codec if hasattr(validation_result, 'codec') else None
        job.source_bitrate = validation_result.bitrate if hasattr(validation_result, 'bitrate') else None
        job.source_fps = validation_result.fps if hasattr(validation_result, 'fps') else None

        db.commit()
        logger.info(f"[Task 1] Video validated successfully: {job.source_resolution}, {job.source_duration_seconds}s")

        # Store video path in XCom for other tasks
        context['task_instance'].xcom_push(key='source_path', value=job.source_path)
        context['task_instance'].xcom_push(key='job_id', value=str(job.job_id))

    except Exception as e:
        logger.error(f"[Task 1] Validation failed: {e}")
        if 'job' in locals() and job is not None:
            job.status = JobStatus.FAILED
            job.error_message = str(e)
            db.commit()
        raise
    finally:
        db.close()


def generate_thumbnail_task(**context):
    """
    Task 3: Generate thumbnails from video

    - Generates 5 thumbnails at different timestamps (0%, 25%, 50%, 75%, 100%)
    - Saves to /data/temp/{job_id}/thumbnails/
    - Stores paths in XCom for upload task
    """
    from app.db import SessionLocal
    from app.models.job import Job

    job_id = context['dag_run'].conf.get('job_id')
    logger.info(f"[Task 3] Generating thumbnails for job {job_id}")

    db = SessionLocal()
    try:
        job = db.query(Job).filter(Job.job_id == job_id).first()
        if not job:
            raise ValueError(f"Job {job_id} not found")

        # Create thumbnail directory
        thumbnail_dir = Path(f"/data/temp/{job_id}/thumbnails")
        thumbnail_dir.mkdir(parents=True, exist_ok=True)

        # Get video duration
        duration = job.source_duration_seconds
        if not duration:
            raise ValueError("Video duration not available")

        # Convert duration to float for calculations
        duration_float = float(duration)

        # Generate thumbnails at 0%, 25%, 50%, 75%, 95% positions
        # Note: Using 95% instead of 100% to avoid FFmpeg errors at exact video end
        thumbnail_paths = []
        positions = [0.0, 0.25, 0.5, 0.75, 0.95]

        for i, position in enumerate(positions):
            timestamp = duration_float * position
            output_path = thumbnail_dir / f"thumbnail_{i+1}.jpg"

            # FFmpeg command to extract frame
            cmd = [
                'ffmpeg',
                '-ss', str(timestamp),
                '-i', job.source_path,
                '-vframes', '1',
                '-q:v', '2',  # Quality (2 is high)
                '-vf', 'scale=640:-1',  # Scale to 640px width, maintain aspect ratio
                '-y',  # Overwrite output
                str(output_path)
            ]

            logger.info(f"[Task 3] Generating thumbnail {i+1}/5 at {timestamp:.2f}s")
            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode != 0:
                logger.error(f"FFmpeg error: {result.stderr}")
                raise RuntimeError(f"Failed to generate thumbnail {i+1}")

            thumbnail_paths.append(str(output_path))

        logger.info(f"[Task 3] Generated {len(thumbnail_paths)} thumbnails")

        # Store paths in XCom
        context['task_instance'].xcom_push(key='thumbnail_paths', value=thumbnail_paths)

    except Exception as e:
        logger.error(f"[Task 3] Thumbnail generation failed: {e}")
        raise
    finally:
        db.close()
