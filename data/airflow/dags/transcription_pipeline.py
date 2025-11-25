"""
Airflow DAG for Decoupled Transcription Pipeline

This DAG handles audio transcription independently from the main video processing pipeline.
It polls the database for jobs with transcription_status='pending' and processes them.

Benefits:
- Transcription doesn't block video processing completion
- Independent scaling of transcription workload
- Better resource allocation for CPU-intensive Whisper tasks
- Retry transcription without re-processing video
"""
from airflow import DAG
from airflow.providers.standard.operators.python import PythonOperator
from airflow.providers.common.sql.sensors.sql import SqlSensor
from datetime import datetime, timedelta
import sys
import os
import logging

logger = logging.getLogger(__name__)

# Add app to Python path for imports
sys.path.insert(0, '/code/app')

# Add DAGs folder to Python path
dags_folder = os.path.dirname(os.path.abspath(__file__))
if dags_folder not in sys.path:
    sys.path.insert(0, dags_folder)

# ============================================================================
# DAG CONFIGURATION
# ============================================================================

default_args = {
    'owner': 'transcode-flow',
    'depends_on_past': False,
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 3,
    'retry_delay': timedelta(minutes=2),
    'retry_exponential_backoff': True,
    'max_retry_delay': timedelta(minutes=15),
    'execution_timeout': timedelta(hours=3),  # Longer for transcription
}

# Database connection ID (configured in Airflow UI)
POSTGRES_CONN_ID = 'postgres_default'


# ============================================================================
# TASK FUNCTIONS
# ============================================================================

def fetch_pending_job_task(**context):
    """
    Fetch the next pending transcription job from the database.
    Updates status to 'queued' to prevent duplicate processing.

    Returns job_id via XCom.
    """
    from app.db import SessionLocal
    from app.models.job import Job, TranscriptionStatus
    from datetime import datetime, timezone

    logger.info("[Transcription] Fetching pending transcription job")

    db = SessionLocal()
    try:
        # Get oldest pending job (FIFO order)
        job = db.query(Job).filter(
            Job.transcription_status == TranscriptionStatus.PENDING
        ).order_by(Job.created_at.asc()).first()

        if not job:
            logger.info("[Transcription] No pending jobs found")
            raise ValueError("No pending transcription jobs")

        # Update status to queued
        job.transcription_status = TranscriptionStatus.QUEUED
        job.transcription_dag_run_id = context['dag_run'].run_id
        db.commit()

        logger.info(f"[Transcription] Fetched job {job.job_id} for transcription")

        # Push job info to XCom
        context['task_instance'].xcom_push(key='job_id', value=job.job_id)
        context['task_instance'].xcom_push(key='source_path', value=job.source_path)
        context['task_instance'].xcom_push(key='source_duration', value=float(job.source_duration_seconds) if job.source_duration_seconds else None)
        context['task_instance'].xcom_push(key='transcription_language', value=job.transcription_language)

        return job.job_id

    except Exception as e:
        logger.error(f"[Transcription] Error fetching pending job: {e}")
        raise
    finally:
        db.close()


def update_status_processing_task(**context):
    """
    Update job transcription_status to 'processing' and record start time.
    """
    from app.db import SessionLocal
    from app.models.job import Job, TranscriptionStatus
    from datetime import datetime, timezone

    job_id = context['task_instance'].xcom_pull(key='job_id', task_ids='fetch_pending_job')

    logger.info(f"[Transcription] Updating job {job_id} status to PROCESSING")

    db = SessionLocal()
    try:
        job = db.query(Job).filter(Job.job_id == job_id).first()
        if job:
            job.transcription_status = TranscriptionStatus.PROCESSING
            job.transcription_started_at = datetime.now(timezone.utc)
            db.commit()
            logger.info(f"[Transcription] Job {job_id} marked as PROCESSING")
    except Exception as e:
        logger.error(f"[Transcription] Error updating status: {e}")
        raise
    finally:
        db.close()


def transcribe_audio_decoupled_task(**context):
    """
    Perform audio transcription using Whisper.

    This is a modified version of transcribe_audio_task that:
    - Gets job_id from XCom (not DAG conf)
    - Updates transcription_status fields
    - Handles errors gracefully
    """
    from app.db import SessionLocal
    from app.models.job import Job, TranscriptionStatus
    from app.services.whisper_transcriber import WhisperTranscriber
    from pathlib import Path
    from datetime import datetime, timezone
    import subprocess
    import threading
    import time

    job_id = context['task_instance'].xcom_pull(key='job_id', task_ids='fetch_pending_job')
    source_duration = context['task_instance'].xcom_pull(key='source_duration', task_ids='fetch_pending_job')

    logger.info(f"[Transcription] Starting transcription for job {job_id}")

    # Heartbeat mechanism
    heartbeat_stop = threading.Event()
    heartbeat_start_time = time.time()
    heartbeat_phase = {"current": "initializing"}

    def send_heartbeat():
        counter = 0
        while not heartbeat_stop.is_set():
            counter += 1
            elapsed = time.time() - heartbeat_start_time
            elapsed_min = int(elapsed // 60)
            elapsed_sec = int(elapsed % 60)
            phase = heartbeat_phase.get("current", "processing")
            logger.info(f"[Transcription] Heartbeat {counter}: {phase} ({elapsed_min}m {elapsed_sec}s) - Job: {job_id}")
            time.sleep(30)

    heartbeat_thread = threading.Thread(target=send_heartbeat, daemon=True)
    heartbeat_thread.start()

    db = SessionLocal()
    try:
        job = db.query(Job).filter(Job.job_id == job_id).first()
        if not job:
            raise ValueError(f"Job {job_id} not found")

        # Create output directory
        output_dir = Path(f"/data/temp/{job_id}/outputs/transcription")
        output_dir.mkdir(parents=True, exist_ok=True)

        # Extract audio for Whisper
        temp_audio = Path(f"/data/temp/{job_id}/temp_audio_transcription.mp3")
        heartbeat_phase["current"] = "extracting_audio"

        extract_cmd = [
            'ffmpeg',
            '-i', job.source_path,
            '-vn',
            '-acodec', 'libmp3lame',
            '-b:a', '128k',
            '-ar', '16000',
            '-ac', '1',
            '-y',
            str(temp_audio)
        ]

        logger.info(f"[Transcription] Extracting audio: {' '.join(extract_cmd)}")
        result = subprocess.run(extract_cmd, capture_output=True, text=True)

        if result.returncode != 0:
            raise RuntimeError(f"Audio extraction failed: {result.stderr[:500]}")

        # Initialize Whisper
        heartbeat_phase["current"] = "transcribing"
        transcriber = WhisperTranscriber(
            model_name=None,
            device='cpu',
            compute_type='int8',
            output_dir=output_dir
        )

        selected_model = transcriber.select_model(source_duration or 600)
        logger.info(f"[Transcription] Using Whisper model: {selected_model}")

        # Perform transcription
        transcription_start = datetime.now(timezone.utc)
        transcription = transcriber.transcribe(
            audio_path=str(temp_audio),
            duration_seconds=source_duration,
            language=job.transcription_language if job.transcription_language != 'auto' else None,
            output_formats=['txt', 'srt', 'vtt', 'json'],
            word_timestamps=True
        )
        transcription_end = datetime.now(timezone.utc)

        processing_duration = (transcription_end - transcription_start).total_seconds()

        logger.info(f"[Transcription] Completed for job {job_id}")
        logger.info(f"[Transcription] Language: {transcription.language}")
        logger.info(f"[Transcription] Text length: {len(transcription.text)} chars")
        logger.info(f"[Transcription] Duration: {int(processing_duration//60)}m {int(processing_duration%60)}s")

        # Push results to XCom
        context['task_instance'].xcom_push(key='transcription_text', value=transcription.text)
        context['task_instance'].xcom_push(key='transcription_language', value=transcription.language)
        context['task_instance'].xcom_push(key='transcription_dir', value=str(output_dir))
        context['task_instance'].xcom_push(key='transcription_segments_count', value=len(transcription.segments))
        context['task_instance'].xcom_push(key='processing_duration_seconds', value=round(processing_duration, 2))

        # Get output files
        output_files = transcriber.get_output_files(temp_audio)
        context['task_instance'].xcom_push(key='transcription_files', value={
            'txt': str(output_files['txt']),
            'srt': str(output_files['srt']),
            'vtt': str(output_files['vtt']),
            'json': str(output_files['json']),
        })

        # Clean up temp audio
        if temp_audio.exists():
            temp_audio.unlink()

    except Exception as e:
        logger.error(f"[Transcription] Failed for job {job_id}: {e}")
        # Update error in database
        try:
            job = db.query(Job).filter(Job.job_id == job_id).first()
            if job:
                job.transcription_status = TranscriptionStatus.FAILED
                job.transcription_error_message = str(e)[:2000]
                job.transcription_retry_count = (job.transcription_retry_count or 0) + 1
                db.commit()
        except:
            pass
        raise
    finally:
        heartbeat_stop.set()
        db.close()


def upload_transcription_task(**context):
    """
    Upload transcription outputs to MinIO.
    """
    from app.core.minio_client import get_minio_client
    from pathlib import Path

    job_id = context['task_instance'].xcom_pull(key='job_id', task_ids='fetch_pending_job')
    transcription_dir = context['task_instance'].xcom_pull(key='transcription_dir', task_ids='transcribe_audio')
    transcription_files = context['task_instance'].xcom_pull(key='transcription_files', task_ids='transcribe_audio')

    if not transcription_dir or not transcription_files:
        logger.warning(f"[Transcription] No transcription files to upload for job {job_id}")
        return

    logger.info(f"[Transcription] Uploading transcription files for job {job_id}")

    try:
        client = get_minio_client()
        bucket = 'processed-videos'

        uploaded_urls = {}

        for format_name, file_path in transcription_files.items():
            if Path(file_path).exists():
                object_name = f"{job_id}/transcription/transcription.{format_name}"
                client.fput_object(bucket, object_name, file_path)
                # Generate presigned URL (7 days)
                from datetime import timedelta
                url = client.presigned_get_object(bucket, object_name, expires=timedelta(days=7))
                uploaded_urls[format_name] = url
                logger.info(f"[Transcription] Uploaded {format_name}: {object_name}")

        context['task_instance'].xcom_push(key='transcription_urls', value=uploaded_urls)

    except Exception as e:
        logger.error(f"[Transcription] Failed to upload files: {e}")
        raise


def update_job_completed_task(**context):
    """
    Update job with transcription completion status and URLs.
    """
    from app.db import SessionLocal
    from app.models.job import Job, TranscriptionStatus
    from datetime import datetime, timezone

    job_id = context['task_instance'].xcom_pull(key='job_id', task_ids='fetch_pending_job')
    transcription_urls = context['task_instance'].xcom_pull(key='transcription_urls', task_ids='upload_transcription')
    transcription_language = context['task_instance'].xcom_pull(key='transcription_language', task_ids='transcribe_audio')

    logger.info(f"[Transcription] Marking job {job_id} as COMPLETED")

    db = SessionLocal()
    try:
        job = db.query(Job).filter(Job.job_id == job_id).first()
        if job:
            job.transcription_status = TranscriptionStatus.COMPLETED
            job.transcription_completed_at = datetime.now(timezone.utc)
            job.transcription_error_message = None  # Clear any previous errors

            # Store primary transcription URL (VTT format for web players)
            if transcription_urls:
                job.transcription_url = transcription_urls.get('vtt') or transcription_urls.get('srt')

            # Store all URLs in metadata
            if not job.job_metadata:
                job.job_metadata = {}
            job.job_metadata['transcription_urls'] = transcription_urls
            job.job_metadata['transcription_language_detected'] = transcription_language

            db.commit()
            logger.info(f"[Transcription] Job {job_id} completed successfully")
    except Exception as e:
        logger.error(f"[Transcription] Error updating completion status: {e}")
        raise
    finally:
        db.close()


def send_transcription_webhook_task(**context):
    """
    Send webhook notification for transcription completion.
    """
    from app.db import SessionLocal
    from app.models.job import Job
    import requests

    job_id = context['task_instance'].xcom_pull(key='job_id', task_ids='fetch_pending_job')
    transcription_urls = context['task_instance'].xcom_pull(key='transcription_urls', task_ids='upload_transcription')

    logger.info(f"[Transcription] Checking webhook for job {job_id}")

    db = SessionLocal()
    try:
        job = db.query(Job).filter(Job.job_id == job_id).first()
        if not job or not job.webhook_url:
            logger.info(f"[Transcription] No webhook configured for job {job_id}")
            return

        payload = {
            "event": "transcription_completed",
            "job_id": job_id,
            "transcription_status": "completed",
            "transcription_urls": transcription_urls,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        try:
            response = requests.post(
                job.webhook_url,
                json=payload,
                timeout=10,
                headers={"Content-Type": "application/json"}
            )
            logger.info(f"[Transcription] Webhook sent: {response.status_code}")
        except requests.RequestException as e:
            logger.warning(f"[Transcription] Webhook failed: {e}")

    finally:
        db.close()


# ============================================================================
# DAG DEFINITION
# ============================================================================

with DAG(
    'transcription_pipeline',
    default_args=default_args,
    description='Decoupled audio transcription pipeline using Whisper',
    schedule=timedelta(minutes=2),  # Poll every 2 minutes
    start_date=datetime(2025, 1, 1),
    catchup=False,
    tags=['transcription', 'whisper', 'audio'],
    max_active_runs=2,  # Limit concurrent transcriptions
) as dag:

    # Sensor: Check for pending transcription jobs
    # Uses SELECT 1 ... LIMIT 1 pattern - returns truthy value only if jobs exist
    # mode='reschedule' releases worker slot between pokes (more efficient)
    check_pending_jobs = SqlSensor(
        task_id='check_pending_jobs',
        conn_id=POSTGRES_CONN_ID,
        sql="""
            SELECT 1 FROM jobs
            WHERE transcription_status = 'pending'
            AND enable_transcription = true
            LIMIT 1
        """,
        mode='reschedule',  # Release worker between checks (more efficient)
        poke_interval=30,  # Check every 30 seconds
        timeout=90,  # Timeout after 90 seconds (before next DAG run at 2 min)
        soft_fail=True,  # Don't fail DAG if no jobs found, mark as skipped
    )

    # Task: Fetch and claim the next pending job
    fetch_pending_job = PythonOperator(
        task_id='fetch_pending_job',
        python_callable=fetch_pending_job_task,
    )

    # Task: Update status to processing
    update_status_processing = PythonOperator(
        task_id='update_status_processing',
        python_callable=update_status_processing_task,
    )

    # Task: Perform transcription
    transcribe_audio = PythonOperator(
        task_id='transcribe_audio',
        python_callable=transcribe_audio_decoupled_task,
        execution_timeout=timedelta(hours=2),
    )

    # Task: Upload transcription files to MinIO
    upload_transcription = PythonOperator(
        task_id='upload_transcription',
        python_callable=upload_transcription_task,
    )

    # Task: Update job completion status
    update_job_completed = PythonOperator(
        task_id='update_job_completed',
        python_callable=update_job_completed_task,
    )

    # Task: Send webhook notification
    send_transcription_webhook = PythonOperator(
        task_id='send_transcription_webhook',
        python_callable=send_transcription_webhook_task,
    )

    # Task dependencies
    check_pending_jobs >> fetch_pending_job >> update_status_processing >> transcribe_audio
    transcribe_audio >> upload_transcription >> update_job_completed >> send_transcription_webhook
