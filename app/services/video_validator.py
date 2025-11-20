"""
Video validation service using FFprobe.
Validates video files and extracts metadata.
"""
import json
import subprocess
import os
from typing import Optional, Dict, Any
from decimal import Decimal
import logging

from app.core.config import settings
from app.schemas.job import VideoValidationResult

logger = logging.getLogger(__name__)


class VideoValidator:
    """Video file validator using FFprobe."""

    def __init__(self):
        self.ffprobe_path = settings.FFPROBE_PATH

    def validate_file(self, file_path: str) -> VideoValidationResult:
        """
        Validate a video file and extract metadata.

        Args:
            file_path: Path to the video file

        Returns:
            VideoValidationResult: Validation result with metadata
        """
        errors = []
        warnings = []

        # Check if file exists
        if not os.path.exists(file_path):
            return VideoValidationResult(
                is_valid=False,
                filename=os.path.basename(file_path),
                size_bytes=0,
                errors=[f"File not found: {file_path}"],
            )

        # Get file size
        try:
            size_bytes = os.path.getsize(file_path)
        except Exception as e:
            return VideoValidationResult(
                is_valid=False,
                filename=os.path.basename(file_path),
                size_bytes=0,
                errors=[f"Failed to get file size: {str(e)}"],
            )

        # Check file size limits
        if size_bytes > settings.MAX_UPLOAD_SIZE:
            max_gb = settings.MAX_UPLOAD_SIZE / (1024 ** 3)
            actual_gb = size_bytes / (1024 ** 3)
            errors.append(
                f"File size {actual_gb:.2f}GB exceeds maximum allowed {max_gb:.2f}GB"
            )

        if size_bytes == 0:
            errors.append("File is empty (0 bytes)")

        # Extract metadata using FFprobe
        metadata = self._extract_metadata(file_path)

        if metadata is None:
            errors.append("Failed to extract video metadata with FFprobe")
            return VideoValidationResult(
                is_valid=False,
                filename=os.path.basename(file_path),
                size_bytes=size_bytes,
                errors=errors,
                warnings=warnings,
            )

        # Validate duration
        duration = metadata.get("duration")
        if duration is not None:
            if duration < settings.MIN_VIDEO_DURATION:
                errors.append(
                    f"Video duration {duration}s is below minimum {settings.MIN_VIDEO_DURATION}s"
                )
            if duration > settings.MAX_VIDEO_DURATION:
                errors.append(
                    f"Video duration {duration}s exceeds maximum {settings.MAX_VIDEO_DURATION}s"
                )

        # Validate resolution
        width = metadata.get("width")
        height = metadata.get("height")

        if width and height:
            if width < settings.MIN_VIDEO_WIDTH or height < settings.MIN_VIDEO_HEIGHT:
                errors.append(
                    f"Video resolution {width}x{height} is below minimum "
                    f"{settings.MIN_VIDEO_WIDTH}x{settings.MIN_VIDEO_HEIGHT}"
                )

            if width > settings.MAX_VIDEO_WIDTH or height > settings.MAX_VIDEO_HEIGHT:
                warnings.append(
                    f"Video resolution {width}x{height} is very high. "
                    f"Processing may take longer."
                )

        # Check codec
        codec = metadata.get("codec")
        if codec and codec.lower() not in ["h264", "h265", "hevc", "vp8", "vp9", "av1"]:
            warnings.append(f"Codec '{codec}' may require additional processing")

        # Construct result
        is_valid = len(errors) == 0

        return VideoValidationResult(
            is_valid=is_valid,
            filename=os.path.basename(file_path),
            size_bytes=size_bytes,
            duration_seconds=metadata.get("duration"),
            resolution=metadata.get("resolution"),
            width=width,
            height=height,
            codec=codec,
            bitrate=metadata.get("bitrate"),
            fps=metadata.get("fps"),
            format=metadata.get("format"),
            errors=errors,
            warnings=warnings,
        )

    def _extract_metadata(self, file_path: str) -> Optional[Dict[str, Any]]:
        """
        Extract metadata from video file using FFprobe.

        Args:
            file_path: Path to the video file

        Returns:
            dict: Metadata dictionary or None if extraction failed
        """
        try:
            # Run FFprobe
            cmd = [
                self.ffprobe_path,
                "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                "-show_streams",
                file_path,
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0:
                logger.error(f"FFprobe failed: {result.stderr}")
                return None

            # Parse JSON output
            data = json.loads(result.stdout)

            # Find video stream
            video_stream = None
            for stream in data.get("streams", []):
                if stream.get("codec_type") == "video":
                    video_stream = stream
                    break

            if not video_stream:
                logger.error("No video stream found in file")
                return None

            # Extract relevant metadata
            format_info = data.get("format", {})

            # Duration
            duration_str = format_info.get("duration") or video_stream.get("duration")
            duration = Decimal(duration_str) if duration_str else None

            # Resolution
            width = video_stream.get("width")
            height = video_stream.get("height")
            resolution = f"{width}x{height}" if width and height else None

            # FPS (frames per second)
            fps_str = video_stream.get("r_frame_rate", "0/0")
            try:
                if "/" in fps_str:
                    num, den = fps_str.split("/")
                    fps = Decimal(num) / Decimal(den) if int(den) != 0 else None
                else:
                    fps = Decimal(fps_str)
            except:
                fps = None

            # Bitrate
            bitrate_str = format_info.get("bit_rate") or video_stream.get("bit_rate")
            bitrate = int(bitrate_str) if bitrate_str else None

            # Codec
            codec = video_stream.get("codec_name")

            # Format
            format_name = format_info.get("format_name")

            metadata = {
                "duration": duration,
                "width": width,
                "height": height,
                "resolution": resolution,
                "fps": fps,
                "bitrate": bitrate,
                "codec": codec,
                "format": format_name,
            }

            logger.info(f"Extracted metadata from {file_path}: {metadata}")
            return metadata

        except subprocess.TimeoutExpired:
            logger.error(f"FFprobe timeout for file: {file_path}")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse FFprobe JSON output: {e}")
            return None
        except Exception as e:
            logger.error(f"Error extracting metadata: {e}")
            return None

    def validate_uploaded_file(
        self,
        file_content: bytes,
        filename: str,
        content_type: str,
    ) -> VideoValidationResult:
        """
        Validate an uploaded file (in memory or temp file).

        Args:
            file_content: File content bytes
            filename: Original filename
            content_type: MIME type

        Returns:
            VideoValidationResult: Validation result
        """
        errors = []
        warnings = []

        # Check content type
        if content_type not in settings.ALLOWED_VIDEO_FORMATS:
            errors.append(
                f"Invalid file type '{content_type}'. "
                f"Allowed: {', '.join(settings.ALLOWED_VIDEO_FORMATS)}"
            )

        # Check file size
        size_bytes = len(file_content)
        if size_bytes > settings.MAX_UPLOAD_SIZE:
            max_gb = settings.MAX_UPLOAD_SIZE / (1024 ** 3)
            actual_gb = size_bytes / (1024 ** 3)
            errors.append(
                f"File size {actual_gb:.2f}GB exceeds maximum {max_gb:.2f}GB"
            )

        if size_bytes == 0:
            errors.append("File is empty (0 bytes)")

        # If basic validation failed, return early
        if errors:
            return VideoValidationResult(
                is_valid=False,
                filename=filename,
                size_bytes=size_bytes,
                errors=errors,
                warnings=warnings,
            )

        # Save to temp file for FFprobe analysis
        import tempfile
        temp_path = None

        try:
            with tempfile.NamedTemporaryFile(
                delete=False,
                suffix=os.path.splitext(filename)[1],
                dir=settings.TEMP_DIR,
            ) as temp_file:
                temp_file.write(file_content)
                temp_path = temp_file.name

            # Validate with FFprobe
            result = self.validate_file(temp_path)
            return result

        finally:
            # Clean up temp file
            if temp_path and os.path.exists(temp_path):
                try:
                    os.unlink(temp_path)
                except Exception as e:
                    logger.warning(f"Failed to delete temp file {temp_path}: {e}")


# Global instance
video_validator = VideoValidator()
