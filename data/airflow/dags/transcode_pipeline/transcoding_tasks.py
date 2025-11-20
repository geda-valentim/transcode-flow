"""
Transcoding Tasks

Tasks related to video and audio transcoding.
"""
import os
import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


def transcode_360p_task(**context):
    """
    Task 4: Transcode video to 360p resolution

    - Output: H.264 video codec, AAC audio codec
    - Resolution: 640x360 (16:9 aspect ratio)
    - Bitrate: ~500 Kbps video, 128 Kbps audio
    - Saves to /data/temp/{job_id}/outputs/360p.mp4
    """
    from app.db import SessionLocal
    from app.models.job import Job

    job_id = context['dag_run'].conf.get('job_id')
    logger.info(f"[Task 4] Transcoding video to 360p for job {job_id}")

    db = SessionLocal()
    try:
        job = db.query(Job).filter(Job.job_id == job_id).first()
        if not job:
            raise ValueError(f"Job {job_id} not found")

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

        logger.info(f"[Task 4] Starting 360p transcode: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            logger.error(f"FFmpeg error: {result.stderr}")
            raise RuntimeError("360p transcoding failed")

        logger.info(f"[Task 4] 360p transcode completed: {output_path}")

        # Store output path in XCom
        context['task_instance'].xcom_push(key='360p_path', value=str(output_path))

    except Exception as e:
        logger.error(f"[Task 4] 360p transcoding failed: {e}")
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
    """
    from app.db import SessionLocal
    from app.models.job import Job

    job_id = context['dag_run'].conf.get('job_id')
    logger.info(f"[Task 5] Transcoding video to 720p for job {job_id}")

    db = SessionLocal()
    try:
        job = db.query(Job).filter(Job.job_id == job_id).first()
        if not job:
            raise ValueError(f"Job {job_id} not found")

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

        logger.info(f"[Task 5] Starting 720p transcode: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            logger.error(f"FFmpeg error: {result.stderr}")
            raise RuntimeError("720p transcoding failed")

        logger.info(f"[Task 5] 720p transcode completed: {output_path}")

        # Store output path in XCom
        context['task_instance'].xcom_push(key='720p_path', value=str(output_path))

    except Exception as e:
        logger.error(f"[Task 5] 720p transcoding failed: {e}")
        raise
    finally:
        db.close()


def extract_audio_mp3_task(**context):
    """
    Task 6: Extract audio and convert to MP3

    - Output: MP3 audio (128 Kbps, 44.1 kHz)
    - Saves to /data/temp/{job_id}/outputs/audio.mp3
    - Used for audio-only playback or downloads
    """
    from app.db import SessionLocal
    from app.models.job import Job

    job_id = context['dag_run'].conf.get('job_id')
    logger.info(f"[Task 6] Extracting audio to MP3 for job {job_id}")

    db = SessionLocal()
    try:
        job = db.query(Job).filter(Job.job_id == job_id).first()
        if not job:
            raise ValueError(f"Job {job_id} not found")

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

        logger.info(f"[Task 6] Starting audio extraction: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            logger.error(f"FFmpeg error: {result.stderr}")
            raise RuntimeError("Audio extraction failed")

        logger.info(f"[Task 6] Audio extraction completed: {output_path}")

        # Store output path in XCom
        context['task_instance'].xcom_push(key='audio_mp3_path', value=str(output_path))

    except Exception as e:
        logger.error(f"[Task 6] Audio extraction failed: {e}")
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
    """
    from app.db import SessionLocal
    from app.models.job import Job
    from app.services.whisper_transcriber import WhisperTranscriber

    job_id = context['dag_run'].conf.get('job_id')
    logger.info(f"[Task 6b] Transcribing audio for job {job_id}")

    db = SessionLocal()
    try:
        job = db.query(Job).filter(Job.job_id == job_id).first()
        if not job:
            raise ValueError(f"Job {job_id} not found")

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
        result = subprocess.run(extract_cmd, capture_output=True, text=True)

        if result.returncode != 0:
            logger.error(f"FFmpeg audio extraction error: {result.stderr}")
            raise RuntimeError("Audio extraction for transcription failed")

        logger.info(f"[Task 6b] Audio extracted: {temp_audio}")

        # Initialize Whisper transcriber
        transcriber = WhisperTranscriber(
            model_name=None,  # Auto-select based on duration
            device='cpu',  # Use CPU (change to 'cuda' if GPU available)
            compute_type='int8',  # Faster inference on CPU
            output_dir=output_dir
        )

        # Perform transcription
        logger.info(f"[Task 6b] Starting Whisper transcription")
        transcription = transcriber.transcribe(
            audio_path=str(temp_audio),
            duration_seconds=job.source_duration_seconds,
            language=None,  # Auto-detect (or set 'en', 'pt', etc.)
            output_formats=['txt', 'srt', 'vtt', 'json'],
            word_timestamps=True
        )

        logger.info(
            f"[Task 6b] Transcription completed: "
            f"language={transcription.language}, "
            f"text_length={len(transcription.text)} chars"
        )

        # Store transcription metadata in XCom
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
        db.close()
