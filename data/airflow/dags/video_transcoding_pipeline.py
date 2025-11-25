"""
Airflow DAG for Video Transcoding Pipeline

Handles complete video processing workflow from upload to delivery.
This is the main DAG file that orchestrates all tasks.

ARCHITECTURE NOTE (2025-11):
Transcription is now handled by a separate `transcription_pipeline` DAG.
This allows video processing to complete faster without waiting for
CPU-intensive Whisper transcription. The main pipeline marks jobs with
`transcription_status='pending'` and the transcription_pipeline picks
them up asynchronously.

Task modules are organized in the transcode_pipeline package:
- validation_tasks: Video validation and thumbnail generation
- transcoding_tasks: Video transcoding (360p, 720p) and audio extraction
- hls_tasks: HLS segmentation preparation
- storage_tasks: MinIO upload operations
- database_tasks: Database updates and cleanup
- notification_tasks: Webhook notifications
"""
from airflow import DAG
from airflow.providers.standard.operators.python import PythonOperator
from datetime import datetime, timedelta
import sys
import os

# Add app to Python path for imports
sys.path.insert(0, '/code/app')

# Add DAGs folder to Python path for transcode_pipeline imports
dags_folder = os.path.dirname(os.path.abspath(__file__))
if dags_folder not in sys.path:
    sys.path.insert(0, dags_folder)

# Import task functions from modular structure
from transcode_pipeline.validation_tasks import (
    validate_video_task,
    generate_thumbnail_task
    )
from transcode_pipeline.transcoding_tasks import (
    transcode_360p_task,
    transcode_720p_task,
    extract_audio_mp3_task,
    # transcribe_audio_task removed - now handled by separate transcription_pipeline DAG
    )
from transcode_pipeline.hls_tasks import prepare_hls_task
from transcode_pipeline.storage_tasks import (
    upload_to_minio_task,
    upload_outputs_task
    )
from transcode_pipeline.database_tasks import (
    update_database_task,
    cleanup_temp_files_task
    )
from transcode_pipeline.notification_tasks import send_notification_task

import logging

logger = logging.getLogger(__name__)


def mark_transcription_pending_task(**context):
    """
    Mark job for transcription by the decoupled transcription_pipeline DAG.

    If enable_transcription is True, sets transcription_status to 'pending'
    so the transcription_pipeline can pick it up.
    """
    from app.db import SessionLocal
    from app.models.job import Job, TranscriptionStatus

    job_id = context['dag_run'].conf.get('job_id')
    logger.info(f"[Transcription Handoff] Checking transcription flag for job {job_id}")

    db = SessionLocal()
    try:
        job = db.query(Job).filter(Job.job_id == job_id).first()
        if not job:
            logger.warning(f"[Transcription Handoff] Job {job_id} not found")
            return

        if job.enable_transcription:
            job.transcription_status = TranscriptionStatus.PENDING
            db.commit()
            logger.info(f"[Transcription Handoff] Job {job_id} marked PENDING for transcription_pipeline")
            context['task_instance'].xcom_push(key='transcription_queued', value=True)
        else:
            job.transcription_status = TranscriptionStatus.DISABLED
            db.commit()
            logger.info(f"[Transcription Handoff] Transcription disabled for job {job_id}")
            context['task_instance'].xcom_push(key='transcription_queued', value=False)

    except Exception as e:
        logger.error(f"[Transcription Handoff] Error: {e}")
        raise
    finally:
        db.close()


# ============================================================================
# DAG CONFIGURATION
# ============================================================================

default_args = {
    'owner': 'transcode-flow',
    'depends_on_past': False,
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 3,
    'retry_delay': timedelta(minutes=5),
    'retry_exponential_backoff': True,
    'max_retry_delay': timedelta(minutes=30),
    'execution_timeout': timedelta(hours=4),
}

with DAG(
    'video_transcoding_pipeline',
    default_args=default_args,
    description='Complete video transcoding and processing pipeline',
    schedule=None,  # Triggered externally via API (changed from schedule_interval in Airflow 3)
    start_date=datetime(2025, 1, 1),
    catchup=False,
    tags=['video', 'transcoding', 'ffmpeg', 'hls'],
    max_active_runs=8,
    ) as dag:

    # ============================================================================
    # TASK DEFINITIONS
    # ============================================================================

    # Task 1: Validate video file
    validate_video = PythonOperator(
        task_id='validate_video',
        python_callable=validate_video_task,
    )

    # Task 2: Upload source video to MinIO
    upload_to_minio = PythonOperator(
        task_id='upload_to_minio',
        python_callable=upload_to_minio_task,
    )

    # Task 3: Generate thumbnails
    generate_thumbnail = PythonOperator(
        task_id='generate_thumbnail',
        python_callable=generate_thumbnail_task,
    )

    # Task 4: Transcode to 360p
    transcode_360p = PythonOperator(
        task_id='transcode_360p',
        python_callable=transcode_360p_task,
    )

    # Task 5: Transcode to 720p
    transcode_720p = PythonOperator(
        task_id='transcode_720p',
        python_callable=transcode_720p_task,
    )

    # Task 6: Extract audio to MP3
    extract_audio_mp3 = PythonOperator(
        task_id='extract_audio_mp3',
        python_callable=extract_audio_mp3_task,
    )

    # Task 6b: Mark job for transcription (handoff to transcription_pipeline DAG)
    # Transcription is now handled by a separate, decoupled DAG for better performance
    mark_transcription_pending = PythonOperator(
        task_id='mark_transcription_pending',
        python_callable=mark_transcription_pending_task,
    )

    # Task 7: Prepare HLS segments for 360p
    prepare_hls_360p = PythonOperator(
        task_id='prepare_hls_360p',
        python_callable=prepare_hls_task,
        params={
        'resolution': '360p',
        'input_path_key': '360p_path',
        'output_key': 'hls_360p_dir'
    },
    )

    # Task 8: Prepare HLS segments for 720p
    prepare_hls_720p = PythonOperator(
        task_id='prepare_hls_720p',
        python_callable=prepare_hls_task,
        params={
        'resolution': '720p',
        'input_path_key': '720p_path',
        'output_key': 'hls_720p_dir'
    },
    )

    # Task 9: Upload all processed outputs to MinIO
    upload_outputs = PythonOperator(
        task_id='upload_outputs',
        python_callable=upload_outputs_task,
    )

    # Task 10: Update database with completion status
    update_database = PythonOperator(
        task_id='update_database',
        python_callable=update_database_task,
    )

    # Task 11: Clean up temporary files
    cleanup_temp_files = PythonOperator(
        task_id='cleanup_temp_files',
        python_callable=cleanup_temp_files_task,
    )

    # Task 12: Send completion notification
    send_notification = PythonOperator(
        task_id='send_notification',
        python_callable=send_notification_task,
    )


    # ============================================================================
    # TASK DEPENDENCIES
    # ============================================================================

    # Validation first
    validate_video >> upload_to_minio >> generate_thumbnail

    # Parallel processing: Transcode 360p, 720p, and extract audio
    # Note: transcribe_audio removed - now handled by separate transcription_pipeline DAG
    validate_video >> [transcode_360p, transcode_720p, extract_audio_mp3]

    # Mark job for transcription after validation (runs in parallel with transcoding)
    # The transcription_pipeline DAG will pick up pending jobs independently
    validate_video >> mark_transcription_pending

    # HLS preparation for each resolution
    transcode_360p >> prepare_hls_360p >> upload_outputs
    transcode_720p >> prepare_hls_720p >> upload_outputs

    # Audio goes directly to upload
    extract_audio_mp3 >> upload_outputs

    # Thumbnails also go to upload
    generate_thumbnail >> upload_outputs

    # Final steps: Database update -> Cleanup -> Notification
    # Note: Video processing completes without waiting for transcription
    upload_outputs >> update_database >> cleanup_temp_files >> send_notification
