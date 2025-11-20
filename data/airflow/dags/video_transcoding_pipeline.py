"""
Airflow DAG for Video Transcoding Pipeline

Handles complete video processing workflow from upload to delivery.
This is the main DAG file that orchestrates all tasks.

Task modules are organized in the transcode_pipeline package:
- validation_tasks: Video validation and thumbnail generation
- transcoding_tasks: Video transcoding (360p, 720p) and audio extraction
- hls_tasks: HLS segmentation preparation
- storage_tasks: MinIO upload operations
- database_tasks: Database updates and cleanup
- notification_tasks: Webhook notifications
"""
from airflow import DAG
from airflow.operators.python import PythonOperator
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
    transcribe_audio_task
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

dag = DAG(
    'video_transcoding_pipeline',
    default_args=default_args,
    description='Complete video transcoding and processing pipeline',
    schedule=None,  # Triggered externally via API (changed from schedule_interval in Airflow 3)
    start_date=datetime(2025, 1, 1),
    catchup=False,
    tags=['video', 'transcoding', 'ffmpeg', 'hls'],
    max_active_runs=8,
)


# ============================================================================
# TASK DEFINITIONS
# ============================================================================

# Task 1: Validate video file
validate_video = PythonOperator(
    task_id='validate_video',
    python_callable=validate_video_task,
    dag=dag,
)

# Task 2: Upload source video to MinIO
upload_to_minio = PythonOperator(
    task_id='upload_to_minio',
    python_callable=upload_to_minio_task,
    dag=dag,
)

# Task 3: Generate thumbnails
generate_thumbnail = PythonOperator(
    task_id='generate_thumbnail',
    python_callable=generate_thumbnail_task,
    dag=dag,
)

# Task 4: Transcode to 360p
transcode_360p = PythonOperator(
    task_id='transcode_360p',
    python_callable=transcode_360p_task,
    dag=dag,
)

# Task 5: Transcode to 720p
transcode_720p = PythonOperator(
    task_id='transcode_720p',
    python_callable=transcode_720p_task,
    dag=dag,
)

# Task 6: Extract audio to MP3
extract_audio_mp3 = PythonOperator(
    task_id='extract_audio_mp3',
    python_callable=extract_audio_mp3_task,
    dag=dag,
)

# Task 6b: Transcribe audio using Whisper (Sprint 3)
transcribe_audio = PythonOperator(
    task_id='transcribe_audio',
    python_callable=transcribe_audio_task,
    dag=dag,
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
    dag=dag,
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
    dag=dag,
)

# Task 9: Upload all processed outputs to MinIO
upload_outputs = PythonOperator(
    task_id='upload_outputs',
    python_callable=upload_outputs_task,
    dag=dag,
)

# Task 10: Update database with completion status
update_database = PythonOperator(
    task_id='update_database',
    python_callable=update_database_task,
    dag=dag,
)

# Task 11: Clean up temporary files
cleanup_temp_files = PythonOperator(
    task_id='cleanup_temp_files',
    python_callable=cleanup_temp_files_task,
    dag=dag,
)

# Task 12: Send completion notification
send_notification = PythonOperator(
    task_id='send_notification',
    python_callable=send_notification_task,
    dag=dag,
)


# ============================================================================
# TASK DEPENDENCIES
# ============================================================================

# Validation first
validate_video >> upload_to_minio >> generate_thumbnail

# Parallel processing: Transcode 360p, 720p, extract audio, and transcribe simultaneously
validate_video >> [transcode_360p, transcode_720p, extract_audio_mp3, transcribe_audio]

# HLS preparation for each resolution
transcode_360p >> prepare_hls_360p >> upload_outputs
transcode_720p >> prepare_hls_720p >> upload_outputs

# Audio goes directly to upload
extract_audio_mp3 >> upload_outputs

# Transcription goes directly to upload (Sprint 3)
transcribe_audio >> upload_outputs

# Thumbnails also go to upload
generate_thumbnail >> upload_outputs

# Final steps: Database update -> Cleanup -> Notification
upload_outputs >> update_database >> cleanup_temp_files >> send_notification
