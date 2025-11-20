"""
Whisper Transcriber Service

Handles audio transcription using OpenAI's Whisper model.
Sprint 3: FFmpeg & Whisper Integration
"""
import os
import json
import logging
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from datetime import timedelta

logger = logging.getLogger(__name__)


@dataclass
class TranscriptionResult:
    """
    Transcription result with metadata
    """
    text: str
    language: str
    duration: float
    segments: List[Dict[str, Any]]
    word_timestamps: Optional[List[Dict[str, Any]]] = None


class WhisperTranscriber:
    """
    Whisper transcription service with adaptive model selection

    Features:
    - Automatic model selection based on video duration
    - Multiple output formats (TXT, SRT, VTT, JSON)
    - Language detection and override
    - Word-level timestamps
    - Progress tracking
    """

    # Model selection based on duration and quality requirements
    MODEL_SELECTION = {
        'tiny': {'max_duration': 180, 'speed': 'fastest', 'quality': 'low'},
        'base': {'max_duration': 600, 'speed': 'fast', 'quality': 'medium'},
        'small': {'max_duration': 1800, 'speed': 'moderate', 'quality': 'good'},
        'medium': {'max_duration': 3600, 'speed': 'slow', 'quality': 'high'},
        'large': {'max_duration': float('inf'), 'speed': 'slowest', 'quality': 'best'},
    }

    def __init__(
        self,
        model_name: Optional[str] = None,
        device: str = "cpu",
        compute_type: str = "int8",
        output_dir: Optional[Path] = None
    ):
        """
        Initialize Whisper transcriber

        Args:
            model_name: Whisper model ('tiny', 'base', 'small', 'medium', 'large')
                       If None, model is auto-selected based on video duration
            device: Device to run on ('cpu' or 'cuda')
            compute_type: Compute type ('int8', 'float16', 'float32')
            output_dir: Directory to save transcription outputs
        """
        self.model_name = model_name
        self.device = device
        self.compute_type = compute_type
        self.output_dir = output_dir

        logger.info(
            f"WhisperTranscriber initialized: "
            f"model={model_name or 'auto'}, device={device}, compute_type={compute_type}"
        )

    def select_model(self, duration_seconds: float) -> str:
        """
        Select appropriate Whisper model based on video duration

        Args:
            duration_seconds: Video duration in seconds

        Returns:
            Model name ('tiny', 'base', 'small', 'medium', 'large')
        """
        if self.model_name:
            return self.model_name

        # Select model based on duration thresholds
        for model, specs in self.MODEL_SELECTION.items():
            if duration_seconds <= specs['max_duration']:
                logger.info(
                    f"Auto-selected model '{model}' for {duration_seconds:.1f}s video "
                    f"(speed: {specs['speed']}, quality: {specs['quality']})"
                )
                return model

        return 'medium'  # Default fallback

    def transcribe(
        self,
        audio_path: str,
        duration_seconds: Optional[float] = None,
        language: Optional[str] = None,
        output_formats: Optional[List[str]] = None,
        word_timestamps: bool = True
    ) -> TranscriptionResult:
        """
        Transcribe audio file using Whisper

        Args:
            audio_path: Path to audio/video file
            duration_seconds: Duration for model selection (if None, detected from file)
            language: Language code ('en', 'pt', etc.) or None for auto-detect
            output_formats: List of formats to generate ['txt', 'srt', 'vtt', 'json']
            word_timestamps: Enable word-level timestamps

        Returns:
            TranscriptionResult with text and metadata
        """
        audio_path = Path(audio_path)
        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        # Detect duration if not provided
        if duration_seconds is None:
            duration_seconds = self._get_duration(audio_path)

        # Select model
        model = self.select_model(duration_seconds)

        # Set output formats
        if output_formats is None:
            output_formats = ['txt', 'srt', 'vtt', 'json']

        # Prepare output directory
        output_dir = self.output_dir or audio_path.parent / "transcription"
        output_dir.mkdir(parents=True, exist_ok=True)

        logger.info(
            f"Starting transcription: audio={audio_path.name}, "
            f"model={model}, language={language or 'auto'}, "
            f"duration={duration_seconds:.1f}s"
        )

        # Build whisper command
        cmd = [
            'whisper',
            str(audio_path),
            '--model', model,
            '--output_dir', str(output_dir),
            '--device', self.device,
            '--output_format', 'all',  # Generate all formats (txt, vtt, srt, tsv, json)
        ]

        if language:
            cmd.extend(['--language', language])

        if word_timestamps:
            cmd.append('--word_timestamps')
            cmd.append('True')

        # Note: --compute_type is not supported by the standard Whisper CLI
        # It's only available in faster-whisper library
        # The standard CLI uses FP16 by default on CUDA, FP32 on CPU

        # Execute transcription
        try:
            logger.info(f"Running command: {' '.join(cmd)}")
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True
            )

            logger.info(f"Transcription completed: {result.stdout}")

            # Parse JSON output for detailed results
            json_file = output_dir / f"{audio_path.stem}.json"
            if json_file.exists():
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                return TranscriptionResult(
                    text=data.get('text', ''),
                    language=data.get('language', language or 'unknown'),
                    duration=duration_seconds,
                    segments=data.get('segments', []),
                    word_timestamps=data.get('words') if word_timestamps else None
                )
            else:
                # Fallback: read TXT file
                txt_file = output_dir / f"{audio_path.stem}.txt"
                if txt_file.exists():
                    with open(txt_file, 'r', encoding='utf-8') as f:
                        text = f.read()

                    return TranscriptionResult(
                        text=text,
                        language=language or 'unknown',
                        duration=duration_seconds,
                        segments=[],
                        word_timestamps=None
                    )
                else:
                    raise RuntimeError("No transcription output files found")

        except subprocess.CalledProcessError as e:
            logger.error(f"Whisper transcription failed: {e.stderr}")
            raise RuntimeError(f"Transcription failed: {e.stderr}")

    def _get_duration(self, audio_path: Path) -> float:
        """
        Get audio/video duration using ffprobe

        Args:
            audio_path: Path to audio/video file

        Returns:
            Duration in seconds
        """
        cmd = [
            'ffprobe',
            '-v', 'quiet',
            '-print_format', 'json',
            '-show_format',
            str(audio_path)
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            data = json.loads(result.stdout)
            duration = float(data['format']['duration'])
            return duration
        except (subprocess.CalledProcessError, KeyError, ValueError) as e:
            logger.warning(f"Failed to detect duration: {e}")
            return 600.0  # Default to 10 minutes

    @staticmethod
    def format_timestamp(seconds: float) -> str:
        """
        Format seconds to SRT timestamp (HH:MM:SS,mmm)

        Args:
            seconds: Time in seconds

        Returns:
            Formatted timestamp string
        """
        td = timedelta(seconds=seconds)
        hours = td.seconds // 3600
        minutes = (td.seconds % 3600) // 60
        secs = td.seconds % 60
        millis = td.microseconds // 1000
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

    def get_output_files(self, audio_path: Path) -> Dict[str, Path]:
        """
        Get paths to all generated transcription files

        Args:
            audio_path: Original audio file path

        Returns:
            Dictionary mapping format to file path
        """
        output_dir = self.output_dir or audio_path.parent / "transcription"
        stem = audio_path.stem

        return {
            'txt': output_dir / f"{stem}.txt",
            'srt': output_dir / f"{stem}.srt",
            'vtt': output_dir / f"{stem}.vtt",
            'json': output_dir / f"{stem}.json",
        }
