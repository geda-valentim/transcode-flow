"""
HLS Tasks

Tasks related to HLS (HTTP Live Streaming) preparation.
"""
import os
import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


def prepare_hls_task(**context):
    """
    Prepare HLS segments from transcoded video

    This function is reusable for different resolutions.
    - Creates .m3u8 playlist
    - Generates .ts segments (10 second chunks)
    - Saves to /data/temp/{job_id}/hls/{resolution}/

    Args:
        resolution: Resolution identifier (e.g., "360p", "720p")
        input_path_key: XCom key for input video path
        output_key: XCom key for storing HLS directory path
    """
    from app.db import SessionLocal
    from app.models.job import Job

    job_id = context['dag_run'].conf.get('job_id')
    resolution = context['params'].get('resolution')  # e.g., "360p" or "720p"
    input_path_key = context['params'].get('input_path_key')  # e.g., "360p_path"
    output_key = context['params'].get('output_key')  # e.g., "hls_360p_dir"

    logger.info(f"[HLS Task] Preparing HLS for {resolution} - job {job_id}")

    db = SessionLocal()
    try:
        job = db.query(Job).filter(Job.job_id == job_id).first()
        if not job:
            raise ValueError(f"Job {job_id} not found")

        # Get input video path from XCom
        input_path = context['task_instance'].xcom_pull(key=input_path_key)
        if not input_path or not os.path.exists(input_path):
            raise ValueError(f"Input video not found: {input_path}")

        # Create HLS output directory
        hls_dir = Path(f"/data/temp/{job_id}/hls/{resolution}")
        hls_dir.mkdir(parents=True, exist_ok=True)

        # Output playlist file
        playlist_path = hls_dir / "playlist.m3u8"

        # FFmpeg HLS conversion command
        cmd = [
            'ffmpeg',
            '-i', input_path,
            '-codec', 'copy',  # Copy video/audio codecs (no re-encoding)
            '-start_number', '0',
            '-hls_time', '10',  # 10-second segments
            '-hls_list_size', '0',  # Include all segments in playlist
            '-f', 'hls',
            str(playlist_path)
        ]

        logger.info(f"[HLS Task] Starting HLS segmentation for {resolution}")
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            logger.error(f"FFmpeg error: {result.stderr}")
            raise RuntimeError(f"HLS preparation failed for {resolution}")

        # Count generated segments
        segments = list(hls_dir.glob("*.ts"))
        logger.info(f"[HLS Task] HLS prepared for {resolution}: {len(segments)} segments in {hls_dir}")

        # Store HLS directory path in XCom
        context['task_instance'].xcom_push(key=output_key, value=str(hls_dir))

    except Exception as e:
        logger.error(f"[HLS Task] HLS preparation failed for {resolution}: {e}")
        raise
    finally:
        db.close()
