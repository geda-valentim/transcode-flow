"""
Metadata service for managing job metadata and JSONB fields.
"""
import json
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


class MetadataService:
    """Service for handling metadata operations."""

    @staticmethod
    def validate_metadata(metadata: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Validate and sanitize metadata.

        Args:
            metadata: Raw metadata dictionary

        Returns:
            dict: Validated metadata

        Raises:
            ValueError: If metadata is invalid
        """
        if metadata is None:
            return {}

        if not isinstance(metadata, dict):
            raise ValueError("Metadata must be a dictionary")

        # Check size (max 10KB as per config)
        metadata_json = json.dumps(metadata)
        if len(metadata_json) > 10240:
            raise ValueError("Metadata exceeds 10KB limit")

        # Sanitize - remove any non-serializable values
        sanitized = {}
        for key, value in metadata.items():
            if isinstance(value, (str, int, float, bool, list, dict, type(None))):
                sanitized[key] = value
            else:
                logger.warning(f"Skipping non-serializable metadata field: {key}")

        return sanitized

    @staticmethod
    def merge_metadata(
        existing: Optional[Dict[str, Any]],
        new_data: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Merge new metadata with existing metadata.

        Args:
            existing: Existing metadata dictionary
            new_data: New metadata to merge

        Returns:
            dict: Merged metadata
        """
        if existing is None:
            existing = {}
        if new_data is None:
            new_data = {}

        # Deep merge
        merged = existing.copy()
        merged.update(new_data)

        return merged

    @staticmethod
    def extract_video_metadata(validation_result) -> Dict[str, Any]:
        """
        Extract metadata from video validation result.

        Args:
            validation_result: VideoValidationResult object

        Returns:
            dict: Metadata dictionary
        """
        from app.schemas.job import VideoValidationResult

        if not isinstance(validation_result, VideoValidationResult):
            return {}

        metadata = {
            "validation": {
                "is_valid": validation_result.is_valid,
                "validated_at": None,  # Will be set by caller
            },
            "source_file": {
                "filename": validation_result.filename,
                "size_bytes": validation_result.size_bytes,
                "format": validation_result.format,
            },
        }

        if validation_result.duration_seconds:
            metadata["source_file"]["duration_seconds"] = float(
                validation_result.duration_seconds
            )

        if validation_result.resolution:
            metadata["source_file"]["resolution"] = validation_result.resolution

        if validation_result.codec:
            metadata["source_file"]["codec"] = validation_result.codec

        if validation_result.bitrate:
            metadata["source_file"]["bitrate"] = validation_result.bitrate

        if validation_result.fps:
            metadata["source_file"]["fps"] = float(validation_result.fps)

        if validation_result.errors:
            metadata["validation"]["errors"] = validation_result.errors

        if validation_result.warnings:
            metadata["validation"]["warnings"] = validation_result.warnings

        return metadata

    @staticmethod
    def add_processing_metadata(
        metadata: Dict[str, Any],
        stage: str,
        info: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Add processing stage metadata.

        Args:
            metadata: Existing metadata
            stage: Processing stage name (e.g., "upload", "validation", "transcoding")
            info: Stage-specific information

        Returns:
            dict: Updated metadata
        """
        from datetime import datetime, timezone

        if "processing_history" not in metadata:
            metadata["processing_history"] = []

        metadata["processing_history"].append(
            {
                "stage": stage,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "info": info,
            }
        )

        return metadata

    @staticmethod
    def get_output_metadata(job) -> Dict[str, Any]:
        """
        Generate output metadata from completed job.

        Args:
            job: Job model instance

        Returns:
            dict: Output metadata
        """
        from app.models.job import Job

        if not isinstance(job, Job):
            return {}

        output_meta = {
            "job_id": job.job_id,
            "status": job.status.value if job.status else None,
            "outputs": {},
        }

        if job.output_formats:
            output_meta["outputs"]["formats"] = job.output_formats

        if job.hls_manifest_url:
            output_meta["outputs"]["hls_manifest"] = job.hls_manifest_url

        if job.audio_file_url:
            output_meta["outputs"]["audio"] = job.audio_file_url

        if job.transcription_url:
            output_meta["outputs"]["transcription"] = job.transcription_url

        if job.thumbnail_url:
            output_meta["outputs"]["thumbnail"] = job.thumbnail_url

        if job.processing_duration_seconds:
            output_meta["processing"] = {
                "duration_seconds": job.processing_duration_seconds,
                "started_at": (
                    job.processing_started_at.isoformat()
                    if job.processing_started_at
                    else None
                ),
                "completed_at": (
                    job.processing_completed_at.isoformat()
                    if job.processing_completed_at
                    else None
                ),
            }

        if job.compression_ratio:
            output_meta["compression"] = {
                "ratio": float(job.compression_ratio),
                "original_size_bytes": job.source_size_bytes,
                "output_size_bytes": job.output_total_size_bytes,
            }

        return output_meta


# Global instance
metadata_service = MetadataService()
