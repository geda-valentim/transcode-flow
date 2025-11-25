"""
HLS Tasks

Tasks related to HLS (HTTP Live Streaming) preparation.
"""
import os
import logging
import subprocess
from pathlib import Path

# Import FFmpeg progress helper from transcoding tasks
from transcode_pipeline.transcoding_tasks import run_ffmpeg_with_progress

logger = logging.getLogger(__name__)


def prepare_hls_task(**context):
    """
    Prepare HLS segments from transcoded video

    This function is reusable for different resolutions.
    - Creates .m3u8 playlist
    - Generates .ts segments (10 second chunks)
    - Saves to /data/temp/{job_id}/hls/{resolution}/
    - Heartbeat logging every 30 seconds with progress

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

    task_name = f"prepare_hls_{resolution}"
    logger.info(f"[{task_name}] ═══ STARTING HLS SEGMENTATION ═══")
    logger.info(f"[{task_name}] Job ID: {job_id}")
    logger.info(f"[{task_name}] Resolution: {resolution}")

    db = SessionLocal()
    try:
        job = db.query(Job).filter(Job.job_id == job_id).first()
        if not job:
            raise ValueError(f"Job {job_id} not found")

        # Get video duration for progress tracking
        video_duration = job.source_duration_seconds

        # Determine source task based on resolution
        source_task = f'transcode_{resolution}'

        # Get input video path from XCom
        input_path = context['task_instance'].xcom_pull(key=input_path_key, task_ids=source_task)
        if not input_path or not os.path.exists(input_path):
            raise ValueError(f"Input video not found: {input_path}")

        # Get input file size for logging
        input_size_mb = os.path.getsize(input_path) / (1024 * 1024)
        logger.info(f"[{task_name}] Input file: {input_path}")
        logger.info(f"[{task_name}] Input size: {input_size_mb:.2f} MB")

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
            '-y',
            str(playlist_path)
        ]

        logger.info(f"[{task_name}] Command: {' '.join(cmd)}")

        # Execute with progress logging (heartbeat every 30s)
        result = run_ffmpeg_with_progress(
            cmd=cmd,
            task_name=task_name,
            job_id=job_id,
            total_duration_seconds=video_duration,
            heartbeat_interval=30
        )

        if result.returncode != 0:
            logger.error(f"[{task_name}] FFmpeg error output:\n{result.stderr[-2000:]}")
            raise RuntimeError(f"HLS preparation failed for {resolution}")

        # Count generated segments and calculate total size
        segments = list(hls_dir.glob("*.ts"))
        total_segments_size = sum(s.stat().st_size for s in segments) / (1024 * 1024)

        logger.info(f"[{task_name}] ═══ HLS SEGMENTATION COMPLETED ═══")
        logger.info(f"[{task_name}] Output directory: {hls_dir}")
        logger.info(f"[{task_name}] Segments created: {len(segments)}")
        logger.info(f"[{task_name}] Total segments size: {total_segments_size:.2f} MB")
        logger.info(f"[{task_name}] Playlist: {playlist_path}")

        # Store HLS directory path in XCom
        context['task_instance'].xcom_push(key=output_key, value=str(hls_dir))

    except Exception as e:
        logger.error(f"[{task_name}] ❌ FAILED: {e}")
        raise
    finally:
        db.close()
