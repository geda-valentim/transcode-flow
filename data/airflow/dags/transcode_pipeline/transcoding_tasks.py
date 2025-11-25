"""
Transcoding Tasks

Tasks related to video and audio transcoding.
"""
import os
import re
import logging
import subprocess
import threading
import time
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, List, Callable

logger = logging.getLogger(__name__)


# ============================================================================
# FFMPEG PROGRESS LOGGING HELPER
# ============================================================================

def run_ffmpeg_with_progress(
    cmd: List[str],
    task_name: str,
    job_id: str,
    total_duration_seconds: Optional[float] = None,
    heartbeat_interval: int = 30,
    on_progress: Optional[Callable[[dict], None]] = None
) -> subprocess.CompletedProcess:
    """
    Execute FFmpeg command with real-time progress logging via heartbeats.

    Args:
        cmd: FFmpeg command as list of arguments
        task_name: Name for logging (e.g., 'transcode_360p', 'transcode_720p')
        job_id: Job ID for logging context
        total_duration_seconds: Total video duration for progress percentage
        heartbeat_interval: Seconds between heartbeat logs (default: 30)
        on_progress: Optional callback for progress updates

    Returns:
        subprocess.CompletedProcess with returncode and captured stderr

    Logs heartbeat every N seconds with:
        - Current frame processed
        - Time position in video
        - Encoding speed (e.g., 2.5x realtime)
        - Progress percentage (if duration known)
        - Bitrate
    """
    # Convert Decimal to float if needed (database returns Decimal)
    if total_duration_seconds is not None:
        total_duration_seconds = float(total_duration_seconds)

    # Ensure FFmpeg outputs progress to stderr (add -stats if not present)
    if '-stats' not in cmd:
        # Insert after 'ffmpeg'
        cmd = [cmd[0], '-stats'] + cmd[1:]

    # Progress tracking state
    progress_state = {
        'frame': 0,
        'fps': 0.0,
        'time': '00:00:00.00',
        'time_seconds': 0.0,
        'speed': '0x',
        'bitrate': 'N/A',
        'size': 'N/A',
        'last_update': time.time()
    }
    heartbeat_stop = threading.Event()
    start_time = time.time()
    stderr_lines = []

    def parse_ffmpeg_progress(line: str) -> bool:
        """Parse FFmpeg progress line and update state. Returns True if progress found."""
        # FFmpeg progress format: frame= 1234 fps= 30 ... time=00:01:23.45 ... speed=2.5x
        updated = False

        # Parse frame
        frame_match = re.search(r'frame=\s*(\d+)', line)
        if frame_match:
            progress_state['frame'] = int(frame_match.group(1))
            updated = True

        # Parse fps
        fps_match = re.search(r'fps=\s*([\d.]+)', line)
        if fps_match:
            progress_state['fps'] = float(fps_match.group(1))

        # Parse time
        time_match = re.search(r'time=(\d{2}:\d{2}:\d{2}\.\d+)', line)
        if time_match:
            progress_state['time'] = time_match.group(1)
            # Convert to seconds
            parts = time_match.group(1).split(':')
            progress_state['time_seconds'] = (
                float(parts[0]) * 3600 +
                float(parts[1]) * 60 +
                float(parts[2])
            )
            updated = True

        # Parse speed
        speed_match = re.search(r'speed=\s*([\d.]+)x', line)
        if speed_match:
            progress_state['speed'] = f"{speed_match.group(1)}x"

        # Parse bitrate
        bitrate_match = re.search(r'bitrate=\s*([\d.]+\w+/s)', line)
        if bitrate_match:
            progress_state['bitrate'] = bitrate_match.group(1)

        # Parse size
        size_match = re.search(r'size=\s*(\d+\w+)', line)
        if size_match:
            progress_state['size'] = size_match.group(1)

        if updated:
            progress_state['last_update'] = time.time()

        return updated

    def heartbeat_logger():
        """Log progress every heartbeat_interval seconds."""
        heartbeat_count = 0
        last_log_time = 0

        while not heartbeat_stop.is_set():
            time.sleep(1)  # Check every second

            current_time = time.time()
            elapsed = current_time - start_time

            # Log every heartbeat_interval seconds
            if current_time - last_log_time >= heartbeat_interval:
                heartbeat_count += 1
                last_log_time = current_time

                # Calculate progress percentage
                if total_duration_seconds and total_duration_seconds > 0:
                    progress_pct = min(99, (progress_state['time_seconds'] / total_duration_seconds) * 100)
                    remaining_seconds = (total_duration_seconds - progress_state['time_seconds'])
                    # Estimate ETA based on current speed
                    speed_num = float(progress_state['speed'].replace('x', '') or 1)
                    if speed_num > 0:
                        eta_seconds = remaining_seconds / speed_num
                        eta_min = int(eta_seconds // 60)
                        eta_sec = int(eta_seconds % 60)
                        eta_str = f"ETA: ~{eta_min}m{eta_sec}s"
                    else:
                        eta_str = "ETA: calculating..."
                    progress_str = f"progress={progress_pct:.1f}%"
                else:
                    progress_str = "progress=N/A"
                    eta_str = ""

                # Format elapsed time
                elapsed_min = int(elapsed // 60)
                elapsed_sec = int(elapsed % 60)

                # Build heartbeat message
                msg_parts = [
                    f"⏱️  Heartbeat #{heartbeat_count}",
                    f"time={progress_state['time']}",
                    f"speed={progress_state['speed']}",
                    progress_str,
                    f"frame={progress_state['frame']}",
                    f"size={progress_state['size']}",
                    f"elapsed={elapsed_min}m{elapsed_sec}s",
                ]
                if eta_str:
                    msg_parts.append(eta_str)

                logger.info(f"[{task_name}] {' | '.join(msg_parts)} | job={job_id}")

                # Call progress callback if provided
                if on_progress:
                    on_progress({
                        **progress_state,
                        'heartbeat': heartbeat_count,
                        'elapsed_seconds': elapsed,
                        'progress_percent': progress_pct if total_duration_seconds else None
                    })

    # Start heartbeat thread
    heartbeat_thread = threading.Thread(target=heartbeat_logger, daemon=True)
    heartbeat_thread.start()

    logger.info(f"[{task_name}] 🚀 Starting FFmpeg process | job={job_id}")
    if total_duration_seconds:
        logger.info(f"[{task_name}] 📊 Source duration: {int(total_duration_seconds//60)}m{int(total_duration_seconds%60)}s ({total_duration_seconds:.1f}s)")

    try:
        # Start FFmpeg process
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1  # Line buffered
        )

        # Read stderr in real-time (FFmpeg outputs progress to stderr)
        while True:
            line = process.stderr.readline()
            if not line and process.poll() is not None:
                break
            if line:
                stderr_lines.append(line)
                parse_ffmpeg_progress(line)

        # Get remaining output
        _, remaining_stderr = process.communicate()
        if remaining_stderr:
            stderr_lines.append(remaining_stderr)

        returncode = process.returncode

    finally:
        # Stop heartbeat thread
        heartbeat_stop.set()
        heartbeat_thread.join(timeout=2)

    # Calculate final stats
    total_elapsed = time.time() - start_time
    elapsed_min = int(total_elapsed // 60)
    elapsed_sec = int(total_elapsed % 60)

    if returncode == 0:
        logger.info(f"[{task_name}] ✅ FFmpeg completed successfully | "
                   f"total_time={elapsed_min}m{elapsed_sec}s | "
                   f"final_speed={progress_state['speed']} | "
                   f"output_size={progress_state['size']} | job={job_id}")
    else:
        logger.error(f"[{task_name}] ❌ FFmpeg failed with code {returncode} | job={job_id}")

    # Return CompletedProcess-like result
    return subprocess.CompletedProcess(
        args=cmd,
        returncode=returncode,
        stdout='',
        stderr=''.join(stderr_lines)
    )


def transcode_360p_task(**context):
    """
    Task 4: Transcode video to 360p resolution

    - Output: H.264 video codec, AAC audio codec
    - Resolution: 640x360 (16:9 aspect ratio)
    - Bitrate: ~500 Kbps video, 128 Kbps audio
    - Saves to /data/temp/{job_id}/outputs/360p.mp4
    - Heartbeat logging every 30 seconds with progress
    """
    from app.db import SessionLocal
    from app.models.job import Job

    job_id = context['dag_run'].conf.get('job_id')
    logger.info(f"[transcode_360p] ═══ STARTING 360P TRANSCODING ═══")
    logger.info(f"[transcode_360p] Job ID: {job_id}")

    db = SessionLocal()
    try:
        job = db.query(Job).filter(Job.job_id == job_id).first()
        if not job:
            raise ValueError(f"Job {job_id} not found")

        # Get video duration for progress tracking
        video_duration = job.source_duration_seconds

        # Create output directory
        output_dir = Path(f"/data/temp/{job_id}/outputs")
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / "360p.mp4"

        # FFmpeg transcoding command (Sprint 3 optimized)
        cmd = [
            'ffmpeg',
            '-i', job.source_path,
            '-vf', 'scale=-2:360',  # Maintain aspect ratio
            '-c:v', 'libx264',
            '-preset', 'medium',
            '-crf', '23',
            '-profile:v', 'main',
            '-level', '3.1',
            '-movflags', '+faststart',  # Enable streaming playback
            '-c:a', 'aac',
            '-b:a', '96k',
            '-ar', '44100',
            '-threads', '0',  # Use all available CPU threads
            '-y',
            str(output_path)
        ]

        logger.info(f"[transcode_360p] Command: {' '.join(cmd)}")

        # Execute with progress logging (heartbeat every 30s)
        result = run_ffmpeg_with_progress(
            cmd=cmd,
            task_name='transcode_360p',
            job_id=job_id,
            total_duration_seconds=video_duration,
            heartbeat_interval=30
        )

        if result.returncode != 0:
            logger.error(f"[transcode_360p] FFmpeg error output:\n{result.stderr[-2000:]}")
            raise RuntimeError("360p transcoding failed")

        # Verify output file exists and has content
        if output_path.exists():
            output_size_mb = output_path.stat().st_size / (1024 * 1024)
            logger.info(f"[transcode_360p] ═══ 360P TRANSCODING COMPLETED ═══")
            logger.info(f"[transcode_360p] Output: {output_path}")
            logger.info(f"[transcode_360p] Size: {output_size_mb:.2f} MB")
        else:
            raise RuntimeError(f"Output file not created: {output_path}")

        # Store output path in XCom
        context['task_instance'].xcom_push(key='360p_path', value=str(output_path))

    except Exception as e:
        logger.error(f"[transcode_360p] ❌ FAILED: {e}")
        raise
    finally:
        db.close()


def transcode_720p_task(**context):
    """
    Task 5: Transcode video to 720p resolution

    - Output: H.264 video codec, AAC audio codec
    - Resolution: 1280x720 (16:9 aspect ratio)
    - Bitrate: ~2000 Kbps video, 192 Kbps audio
    - Saves to /data/temp/{job_id}/outputs/720p.mp4
    - Heartbeat logging every 30 seconds with progress
    """
    from app.db import SessionLocal
    from app.models.job import Job

    job_id = context['dag_run'].conf.get('job_id')
    logger.info(f"[transcode_720p] ═══ STARTING 720P TRANSCODING ═══")
    logger.info(f"[transcode_720p] Job ID: {job_id}")

    db = SessionLocal()
    try:
        job = db.query(Job).filter(Job.job_id == job_id).first()
        if not job:
            raise ValueError(f"Job {job_id} not found")

        # Get video duration for progress tracking
        video_duration = job.source_duration_seconds

        # Create output directory
        output_dir = Path(f"/data/temp/{job_id}/outputs")
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / "720p.mp4"

        # FFmpeg transcoding command (Sprint 3 optimized)
        cmd = [
            'ffmpeg',
            '-i', job.source_path,
            '-vf', 'scale=-2:720',  # Maintain aspect ratio
            '-c:v', 'libx264',
            '-preset', 'medium',
            '-crf', '22',
            '-profile:v', 'high',
            '-level', '4.0',
            '-movflags', '+faststart',  # Enable streaming playback
            '-c:a', 'aac',
            '-b:a', '128k',
            '-ar', '48000',
            '-threads', '0',  # Use all available CPU threads
            '-y',
            str(output_path)
        ]

        logger.info(f"[transcode_720p] Command: {' '.join(cmd)}")

        # Execute with progress logging (heartbeat every 30s)
        result = run_ffmpeg_with_progress(
            cmd=cmd,
            task_name='transcode_720p',
            job_id=job_id,
            total_duration_seconds=video_duration,
            heartbeat_interval=30
        )

        if result.returncode != 0:
            logger.error(f"[transcode_720p] FFmpeg error output:\n{result.stderr[-2000:]}")
            raise RuntimeError("720p transcoding failed")

        # Verify output file exists and has content
        if output_path.exists():
            output_size_mb = output_path.stat().st_size / (1024 * 1024)
            logger.info(f"[transcode_720p] ═══ 720P TRANSCODING COMPLETED ═══")
            logger.info(f"[transcode_720p] Output: {output_path}")
            logger.info(f"[transcode_720p] Size: {output_size_mb:.2f} MB")
        else:
            raise RuntimeError(f"Output file not created: {output_path}")

        # Store output path in XCom
        context['task_instance'].xcom_push(key='720p_path', value=str(output_path))

    except Exception as e:
        logger.error(f"[transcode_720p] ❌ FAILED: {e}")
        raise
    finally:
        db.close()


def extract_audio_mp3_task(**context):
    """
    Task 6: Extract audio and convert to MP3

    - Output: MP3 audio (192 Kbps, 48 kHz)
    - Saves to /data/temp/{job_id}/outputs/audio.mp3
    - Used for audio-only playback or downloads
    - Heartbeat logging every 30 seconds with progress
    """
    from app.db import SessionLocal
    from app.models.job import Job

    job_id = context['dag_run'].conf.get('job_id')
    logger.info(f"[extract_audio] ═══ STARTING AUDIO EXTRACTION ═══")
    logger.info(f"[extract_audio] Job ID: {job_id}")

    db = SessionLocal()
    try:
        job = db.query(Job).filter(Job.job_id == job_id).first()
        if not job:
            raise ValueError(f"Job {job_id} not found")

        # Get video duration for progress tracking
        video_duration = job.source_duration_seconds

        # Create output directory
        output_dir = Path(f"/data/temp/{job_id}/outputs")
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / "audio.mp3"

        # FFmpeg audio extraction command (Sprint 3 optimized)
        cmd = [
            'ffmpeg',
            '-i', job.source_path,
            '-vn',  # No video
            '-acodec', 'libmp3lame',
            '-b:a', '192k',
            '-ar', '48000',
            '-q:a', '2',  # Quality setting (0-9, lower is better)
            '-y',
            str(output_path)
        ]

        logger.info(f"[extract_audio] Command: {' '.join(cmd)}")

        # Execute with progress logging (heartbeat every 30s)
        result = run_ffmpeg_with_progress(
            cmd=cmd,
            task_name='extract_audio',
            job_id=job_id,
            total_duration_seconds=video_duration,
            heartbeat_interval=30
        )

        if result.returncode != 0:
            logger.error(f"[extract_audio] FFmpeg error output:\n{result.stderr[-2000:]}")
            raise RuntimeError("Audio extraction failed")

        # Verify output file exists and has content
        if output_path.exists():
            output_size_mb = output_path.stat().st_size / (1024 * 1024)
            logger.info(f"[extract_audio] ═══ AUDIO EXTRACTION COMPLETED ═══")
            logger.info(f"[extract_audio] Output: {output_path}")
            logger.info(f"[extract_audio] Size: {output_size_mb:.2f} MB")
        else:
            raise RuntimeError(f"Output file not created: {output_path}")

        # Store output path in XCom
        context['task_instance'].xcom_push(key='audio_mp3_path', value=str(output_path))

    except Exception as e:
        logger.error(f"[extract_audio] ❌ FAILED: {e}")
        raise
    finally:
        db.close()


def transcribe_audio_task(**context):
    """
    Task 6b: Transcribe audio using Whisper

    - Extracts audio from source video
    - Transcribes using Whisper with auto-selected model
    - Generates multiple output formats (TXT, SRT, VTT, JSON)
    - Saves to /data/temp/{job_id}/outputs/transcription/
    - Sprint 3: FFmpeg & Whisper Integration
    - Sends heartbeats to prevent Airflow timeout
    """
    from app.db import SessionLocal
    from app.models.job import Job
    from app.services.whisper_transcriber import WhisperTranscriber
    import threading
    import time

    job_id = context['dag_run'].conf.get('job_id')
    logger.info(f"[Task 6b] ═══ TRANSCRIPTION TASK STARTED ═══")
    logger.info(f"[Task 6b] Job ID: {job_id}")

    # Heartbeat mechanism to keep Airflow task alive during long processing
    heartbeat_stop = threading.Event()
    heartbeat_start_time = time.time()
    heartbeat_phase = {"current": "initializing"}  # Shared state for phase tracking
    video_duration = {"seconds": 0}  # Shared state for video duration

    def send_heartbeat():
        """Send periodic heartbeats with detailed progress information"""
        counter = 0
        while not heartbeat_stop.is_set():
            try:
                counter += 1
                elapsed = time.time() - heartbeat_start_time
                elapsed_min = int(elapsed // 60)
                elapsed_sec = int(elapsed % 60)

                # Build progress message based on phase
                phase = heartbeat_phase.get("current", "processing")
                duration = video_duration.get("seconds", 0)

                if phase == "extracting_audio":
                    msg = f"⏳ Extracting audio from video ({elapsed_min}m {elapsed_sec}s elapsed)"
                elif phase == "transcribing":
                    # Estimate progress: Whisper typically processes at 10-30x realtime for tiny model
                    # Conservative estimate: 15x realtime
                    estimated_total_sec = duration / 15 if duration > 0 else 180
                    progress_pct = min(95, int((elapsed / estimated_total_sec) * 100)) if estimated_total_sec > 0 else 0
                    eta_sec = max(0, estimated_total_sec - elapsed)
                    eta_min = int(eta_sec // 60)
                    eta_sec_rem = int(eta_sec % 60)

                    msg = (f"🎙️  Transcribing audio (model: tiny) | "
                           f"Progress: ~{progress_pct}% | "
                           f"Elapsed: {elapsed_min}m {elapsed_sec}s | "
                           f"ETA: ~{eta_min}m {eta_sec_rem}s | "
                           f"Video: {duration:.0f}s")
                else:
                    msg = f"⚙️  {phase} ({elapsed_min}m {elapsed_sec}s elapsed)"

                logger.info(f"[Task 6b] Heartbeat {counter}: {msg} - Job: {job_id}")
                time.sleep(30)  # Send heartbeat every 30 seconds
            except Exception as e:
                logger.warning(f"[Task 6b] Heartbeat error: {e}")
                break

    # Start heartbeat thread
    heartbeat_thread = threading.Thread(target=send_heartbeat, daemon=True)
    heartbeat_thread.start()
    logger.info(f"[Task 6b] Started heartbeat thread")

    db = SessionLocal()
    try:
        job = db.query(Job).filter(Job.job_id == job_id).first()
        if not job:
            raise ValueError(f"Job {job_id} not found")

        # Check if transcription is enabled for this job
        if not job.enable_transcription:
            logger.info(f"[Task 6b] Transcription disabled for job {job_id}, skipping task")
            heartbeat_stop.set()  # Stop heartbeat before returning
            return  # Skip transcription

        logger.info(f"[Task 6b] Transcription enabled, proceeding with Whisper processing")

        # Push initial status to XCom for observability
        context['task_instance'].xcom_push(
            key='transcription_status',
            value='initializing'
        )
        context['task_instance'].xcom_push(
            key='transcription_start_time',
            value=datetime.now(timezone.utc).isoformat()
        )

        # Create output directory for transcription
        output_dir = Path(f"/data/temp/{job_id}/outputs/transcription")
        output_dir.mkdir(parents=True, exist_ok=True)

        # Extract audio first (temporary file for transcription)
        temp_audio = Path(f"/data/temp/{job_id}/temp_audio.mp3")

        # Extract audio using FFmpeg (fast extraction for Whisper)
        extract_cmd = [
            'ffmpeg',
            '-i', job.source_path,
            '-vn',  # No video
            '-acodec', 'libmp3lame',
            '-b:a', '128k',
            '-ar', '16000',  # 16kHz for Whisper (optimal)
            '-ac', '1',  # Mono audio
            '-y',
            str(temp_audio)
        ]

        logger.info(f"[Task 6b] Extracting audio for transcription: {' '.join(extract_cmd)}")

        # Update XCom status and heartbeat phase
        heartbeat_phase["current"] = "extracting_audio"
        context['task_instance'].xcom_push(
            key='transcription_status',
            value='extracting_audio'
        )

        result = subprocess.run(extract_cmd, capture_output=True, text=True)

        if result.returncode != 0:
            logger.error(f"FFmpeg audio extraction error: {result.stderr}")
            context['task_instance'].xcom_push(
                key='transcription_status',
                value='failed'
            )
            context['task_instance'].xcom_push(
                key='transcription_error',
                value=f"Audio extraction failed: {result.stderr[:500]}"
            )
            raise RuntimeError("Audio extraction for transcription failed")

        # Get audio file size for metrics
        audio_size_mb = temp_audio.stat().st_size / (1024 * 1024)
        logger.info(f"[Task 6b] Audio extracted: {temp_audio} ({audio_size_mb:.2f} MB)")

        context['task_instance'].xcom_push(
            key='audio_file_size_mb',
            value=round(audio_size_mb, 2)
        )

        # Initialize Whisper transcriber
        transcriber = WhisperTranscriber(
            model_name=None,  # Auto-select based on duration
            device='cpu',  # Use CPU (change to 'cuda' if GPU available)
            compute_type='int8',  # Faster inference on CPU
            output_dir=output_dir
        )

        # Select and push model info to XCom
        selected_model = transcriber.select_model(job.source_duration_seconds or 600)
        model_specs = transcriber.MODEL_SELECTION.get(selected_model, {})

        context['task_instance'].xcom_push(
            key='whisper_model_selected',
            value=selected_model
        )
        context['task_instance'].xcom_push(
            key='whisper_model_speed',
            value=model_specs.get('speed', 'unknown')
        )
        context['task_instance'].xcom_push(
            key='whisper_model_quality',
            value=model_specs.get('quality', 'unknown')
        )
        context['task_instance'].xcom_push(
            key='video_duration_seconds',
            value=job.source_duration_seconds
        )

        logger.info(
            f"[Task 6b] Selected Whisper model: {selected_model} "
            f"(speed: {model_specs.get('speed')}, quality: {model_specs.get('quality')})"
        )

        # Perform transcription
        heartbeat_phase["current"] = "transcribing"
        if job.source_duration_seconds:
            video_duration["seconds"] = float(job.source_duration_seconds)
            # Estimate processing time (Whisper tiny typically 10-30x realtime)
            estimated_min = int((video_duration["seconds"] / 15) / 60)
            estimated_sec = int((video_duration["seconds"] / 15) % 60)
            logger.info(f"[Task 6b] 🎙️  Starting Whisper transcription")
            logger.info(f"[Task 6b] Video duration: {video_duration['seconds']:.1f}s ({int(video_duration['seconds']//60)}m {int(video_duration['seconds']%60)}s)")
            logger.info(f"[Task 6b] Estimated processing time: ~{estimated_min}m {estimated_sec}s (using 'tiny' model)")
        else:
            logger.info(f"[Task 6b] Starting Whisper transcription")
        context['task_instance'].xcom_push(
            key='transcription_status',
            value='transcribing'
        )
        context['task_instance'].xcom_push(
            key='transcription_processing_start',
            value=datetime.now(timezone.utc).isoformat()
        )

        transcription = transcriber.transcribe(
            audio_path=str(temp_audio),
            duration_seconds=job.source_duration_seconds,
            language=None,  # Auto-detect (or set 'en', 'pt', etc.)
            output_formats=['txt', 'srt', 'vtt', 'json'],
            word_timestamps=True
        )

        # Calculate processing duration
        processing_end_time = datetime.now(timezone.utc)
        processing_start_time_str = context['task_instance'].xcom_pull(
            key='transcription_processing_start',
            task_ids='transcribe_audio'
        )
        if processing_start_time_str:
            processing_start_time = datetime.fromisoformat(processing_start_time_str)
            processing_duration = (processing_end_time - processing_start_time).total_seconds()
        else:
            processing_duration = 0

        # Calculate speed metrics
        realtime_factor = (float(video_duration.get("seconds", 0)) / processing_duration) if processing_duration > 0 else 0

        logger.info(f"[Task 6b] ═══ TRANSCRIPTION COMPLETED ═══")
        logger.info(f"[Task 6b] ✅ Language detected: {transcription.language}")
        logger.info(f"[Task 6b] ✅ Text length: {len(transcription.text)} characters")
        logger.info(f"[Task 6b] ✅ Segments: {len(transcription.segments)}")
        logger.info(f"[Task 6b] ✅ Processing time: {int(processing_duration//60)}m {int(processing_duration%60)}s")
        if realtime_factor > 0:
            logger.info(f"[Task 6b] ✅ Speed: {realtime_factor:.1f}x realtime")
        logger.info(f"[Task 6b] ═══════════════════════════════")

        # Push comprehensive metrics to XCom
        context['task_instance'].xcom_push(
            key='transcription_status',
            value='completed'
        )
        context['task_instance'].xcom_push(
            key='transcription_processing_end',
            value=processing_end_time.isoformat()
        )
        context['task_instance'].xcom_push(
            key='transcription_processing_duration_seconds',
            value=round(processing_duration, 2)
        )
        context['task_instance'].xcom_push(
            key='transcription_text_length',
            value=len(transcription.text)
        )
        context['task_instance'].xcom_push(
            key='transcription_segments_count',
            value=len(transcription.segments)
        )
        context['task_instance'].xcom_push(
            key='transcription_detected_language',
            value=transcription.language
        )

        # Store transcription metadata in XCom (backward compatibility)
        context['task_instance'].xcom_push(key='transcription_text', value=transcription.text)
        context['task_instance'].xcom_push(key='transcription_language', value=transcription.language)
        context['task_instance'].xcom_push(key='transcription_dir', value=str(output_dir))

        # Get output file paths
        output_files = transcriber.get_output_files(temp_audio)
        context['task_instance'].xcom_push(key='transcription_files', value={
            'txt': str(output_files['txt']),
            'srt': str(output_files['srt']),
            'vtt': str(output_files['vtt']),
            'json': str(output_files['json']),
        })

        # Clean up temporary audio file
        if temp_audio.exists():
            temp_audio.unlink()
            logger.info(f"[Task 6b] Cleaned up temporary audio file")

        logger.info(f"[Task 6b] Transcription task completed successfully")

    except Exception as e:
        logger.error(f"[Task 6b] Audio transcription failed: {e}")
        raise
    finally:
        # Stop heartbeat thread
        heartbeat_stop.set()
        logger.info(f"[Task 6b] Stopped heartbeat thread")
        db.close()
