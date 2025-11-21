"""
Storage Tasks

Tasks related to MinIO storage operations.
"""
import os
import logging
from pathlib import Path
from minio import Minio
from minio.error import S3Error

logger = logging.getLogger(__name__)


def get_minio_client():
    """
    Create and return a MinIO client instance.

    Returns:
        Minio: Configured MinIO client
    """
    from app.core.config import settings

    return Minio(
        f"{settings.MINIO_HOST}:{settings.MINIO_PORT}",
        access_key=settings.MINIO_ACCESS_KEY,
        secret_key=settings.MINIO_SECRET_KEY,
        secure=settings.MINIO_SECURE
    )


def upload_to_minio_task(**context):
    """
    Task 2: Upload source video to MinIO

    - Uploads original video file to 'raw-videos' bucket
    - Stores MinIO path: {job_id}/original.{ext}
    - Updates job with MinIO path
    """
    from app.db import SessionLocal
    from app.models.job import Job

    job_id = context['dag_run'].conf.get('job_id')
    logger.info(f"[Task 2] Uploading source video to MinIO for job {job_id}")

    db = SessionLocal()
    try:
        job = db.query(Job).filter(Job.job_id == job_id).first()
        if not job:
            raise ValueError(f"Job {job_id} not found")

        # Get file extension
        source_path = Path(job.source_path)
        file_ext = source_path.suffix

        # MinIO object path
        object_name = f"{job_id}/original{file_ext}"
        bucket_name = "raw-videos"

        # Create MinIO client
        minio_client = get_minio_client()

        # Ensure bucket exists
        if not minio_client.bucket_exists(bucket_name):
            minio_client.make_bucket(bucket_name)
            logger.info(f"[Task 2] Created bucket: {bucket_name}")

        # Upload file
        logger.info(f"[Task 2] Uploading {source_path} to {bucket_name}/{object_name}")
        minio_client.fput_object(
            bucket_name,
            object_name,
            str(source_path)
        )

        logger.info(f"[Task 2] Upload completed: {bucket_name}/{object_name}")

        # Store MinIO path in XCom
        minio_path = f"s3://{bucket_name}/{object_name}"
        context['task_instance'].xcom_push(key='minio_raw_path', value=minio_path)

    except S3Error as e:
        logger.error(f"[Task 2] MinIO error: {e}")
        raise
    except Exception as e:
        logger.error(f"[Task 2] Upload to MinIO failed: {e}")
        raise
    finally:
        db.close()


def upload_outputs_task(**context):
    """
    Task 9: Upload all processed outputs to MinIO

    Uploads the following to 'processed-videos' bucket:
    - Thumbnails (5 images)
    - 360p transcoded video
    - 720p transcoded video
    - MP3 audio
    - HLS segments (360p and 720p)

    Stores all MinIO paths in job metadata.
    """
    from app.db import SessionLocal
    from app.models.job import Job

    job_id = context['dag_run'].conf.get('job_id')
    logger.info(f"[Task 9] Uploading processed outputs to MinIO for job {job_id}")

    db = SessionLocal()
    try:
        job = db.query(Job).filter(Job.job_id == job_id).first()
        if not job:
            raise ValueError(f"Job {job_id} not found")

        # Create MinIO client
        minio_client = get_minio_client()
        bucket_name = "processed-videos"

        # Ensure bucket exists
        if not minio_client.bucket_exists(bucket_name):
            minio_client.make_bucket(bucket_name)
            logger.info(f"[Task 9] Created bucket: {bucket_name}")

        uploaded_files = {}

        # 1. Upload thumbnails
        thumbnail_paths = context['task_instance'].xcom_pull(key='thumbnail_paths', task_ids='generate_thumbnail')
        if thumbnail_paths:
            uploaded_files['thumbnails'] = []
            total_thumbs = len(thumbnail_paths)
            for i, thumb_path in enumerate(thumbnail_paths):
                # Skip if file doesn't exist
                if not os.path.exists(thumb_path):
                    logger.warning(f"[Task 9] Thumbnail not found, skipping: {thumb_path}")
                    continue

                object_name = f"{job_id}/thumbnails/thumbnail_{i+1}.jpg"
                minio_client.fput_object(bucket_name, object_name, thumb_path)
                uploaded_files['thumbnails'].append(f"s3://{bucket_name}/{object_name}")
                logger.info(f"[Task 9] Uploaded thumbnail {i+1}/{total_thumbs}")

        # 2. Upload 360p video
        video_360p_path = context['task_instance'].xcom_pull(key='360p_path', task_ids='transcode_360p')
        if video_360p_path and os.path.exists(video_360p_path):
            object_name = f"{job_id}/videos/360p.mp4"
            minio_client.fput_object(bucket_name, object_name, video_360p_path)
            uploaded_files['video_360p'] = f"s3://{bucket_name}/{object_name}"
            logger.info(f"[Task 9] Uploaded 360p video")

        # 3. Upload 720p video
        video_720p_path = context['task_instance'].xcom_pull(key='720p_path', task_ids='transcode_720p')
        if video_720p_path and os.path.exists(video_720p_path):
            object_name = f"{job_id}/videos/720p.mp4"
            minio_client.fput_object(bucket_name, object_name, video_720p_path)
            uploaded_files['video_720p'] = f"s3://{bucket_name}/{object_name}"
            logger.info(f"[Task 9] Uploaded 720p video")

        # 4. Upload MP3 audio
        audio_mp3_path = context['task_instance'].xcom_pull(key='audio_mp3_path', task_ids='extract_audio_mp3')
        if audio_mp3_path and os.path.exists(audio_mp3_path):
            object_name = f"{job_id}/audio/audio.mp3"
            minio_client.fput_object(bucket_name, object_name, audio_mp3_path)
            uploaded_files['audio_mp3'] = f"s3://{bucket_name}/{object_name}"
            logger.info(f"[Task 9] Uploaded MP3 audio")

        # 5. Upload HLS 360p segments
        hls_360p_dir = context['task_instance'].xcom_pull(key='hls_360p_dir', task_ids='prepare_hls_360p')
        if hls_360p_dir and os.path.exists(hls_360p_dir):
            uploaded_files['hls_360p'] = []
            for file_path in Path(hls_360p_dir).rglob("*"):
                if file_path.is_file():
                    object_name = f"{job_id}/hls/360p/{file_path.name}"
                    minio_client.fput_object(bucket_name, object_name, str(file_path))
                    uploaded_files['hls_360p'].append(f"s3://{bucket_name}/{object_name}")
            logger.info(f"[Task 9] Uploaded HLS 360p ({len(uploaded_files['hls_360p'])} files)")

        # 6. Upload HLS 720p segments
        hls_720p_dir = context['task_instance'].xcom_pull(key='hls_720p_dir', task_ids='prepare_hls_720p')
        if hls_720p_dir and os.path.exists(hls_720p_dir):
            uploaded_files['hls_720p'] = []
            for file_path in Path(hls_720p_dir).rglob("*"):
                if file_path.is_file():
                    object_name = f"{job_id}/hls/720p/{file_path.name}"
                    minio_client.fput_object(bucket_name, object_name, str(file_path))
                    uploaded_files['hls_720p'].append(f"s3://{bucket_name}/{object_name}")
            logger.info(f"[Task 9] Uploaded HLS 720p ({len(uploaded_files['hls_720p'])} files)")

        logger.info(f"[Task 9] All outputs uploaded to MinIO")

        # Store uploaded paths in XCom for database update task
        context['task_instance'].xcom_push(key='uploaded_files', value=uploaded_files)

    except S3Error as e:
        logger.error(f"[Task 9] MinIO error: {e}")
        raise
    except Exception as e:
        logger.error(f"[Task 9] Upload outputs failed: {e}")
        raise
    finally:
        db.close()
