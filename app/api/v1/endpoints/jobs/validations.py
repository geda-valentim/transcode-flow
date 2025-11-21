"""
Shared validation functions for job operations.
"""
import uuid
import os
import json
from typing import Optional, Dict, Any
from datetime import datetime, timezone
from fastapi import HTTPException, status, UploadFile
from sqlalchemy.orm import Session

from app.models.api_key import APIKey
from app.core.security import (
    check_permission,
    check_storage_quota,
    check_jobs_quota,
    increment_jobs_usage,
    increment_storage_usage,
)
from app.core.rate_limit import check_rate_limit
from app.services.video_validator import video_validator
from app.schemas.job import VideoValidationResult
from app.services.metadata_service import metadata_service


def check_job_permissions(
    api_key: APIKey,
    enable_transcription: bool = False
) -> None:
    """
    Check if API key has required permissions for job creation.

    Args:
        api_key: API key to check
        enable_transcription: Whether transcription is enabled

    Raises:
        HTTPException: If permissions are insufficient
    """
    check_rate_limit(api_key)
    check_permission(api_key, "can_transcode")

    if enable_transcription:
        check_permission(api_key, "can_transcribe")


def check_upload_permissions(api_key: APIKey, enable_transcription: bool = False) -> None:
    """
    Check permissions for upload endpoint (includes upload permission).

    Args:
        api_key: API key to check
        enable_transcription: Whether transcription is enabled

    Raises:
        HTTPException: If permissions are insufficient
    """
    check_rate_limit(api_key)
    check_permission(api_key, "can_upload")
    check_permission(api_key, "can_transcode")

    if enable_transcription:
        check_permission(api_key, "can_transcribe")


async def validate_and_process_upload(
    video_file: UploadFile,
    api_key: APIKey,
) -> tuple[bytes, int, VideoValidationResult]:
    """
    Validate uploaded file and check quotas.

    Args:
        video_file: Uploaded file
        api_key: API key for quota checks

    Returns:
        Tuple of (file_content, file_size, validation_result)

    Raises:
        HTTPException: If validation fails or quotas exceeded
    """
    # Read file content
    file_content = await video_file.read()
    file_size = len(file_content)

    # Check storage quota
    check_storage_quota(api_key, file_size)

    # Validate video file
    validation_result = video_validator.validate_uploaded_file(
        file_content=file_content,
        filename=video_file.filename,
        content_type=video_file.content_type,
    )

    if not validation_result.is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": "Video validation failed",
                "errors": validation_result.errors,
                "warnings": validation_result.warnings,
            },
        )

    return file_content, file_size, validation_result


def validate_filesystem_path(source_path: str, api_key: APIKey) -> VideoValidationResult:
    """
    Validate file from filesystem path.

    Args:
        source_path: Path to video file
        api_key: API key for quota checks

    Returns:
        VideoValidationResult object

    Raises:
        HTTPException: If file not found, validation fails, or quotas exceeded
    """
    # Validate that file exists
    if not os.path.exists(source_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File not found: {source_path}",
        )

    # Validate video file
    validation_result = video_validator.validate_file(source_path)

    if not validation_result.is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": "Video validation failed",
                "errors": validation_result.errors,
                "warnings": validation_result.warnings,
            },
        )

    # Check storage quota
    check_storage_quota(api_key, validation_result.size_bytes)

    return validation_result


def parse_metadata(metadata: Optional[str]) -> Optional[Dict[str, Any]]:
    """
    Parse and validate JSON metadata string.

    Args:
        metadata: JSON string containing metadata

    Returns:
        Parsed and validated metadata dict or None

    Raises:
        HTTPException: If JSON is invalid
    """
    if not metadata:
        return None

    try:
        parsed = json.loads(metadata)
        return metadata_service.validate_metadata(parsed)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON in metadata field",
        )


def build_job_metadata(
    validation_result: VideoValidationResult,
    custom_metadata: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Build complete job metadata from validation result and custom data.

    Args:
        validation_result: Video validation result
        custom_metadata: Optional custom metadata to merge

    Returns:
        Complete metadata dictionary
    """
    video_metadata = metadata_service.extract_video_metadata(validation_result)
    video_metadata["validation"]["validated_at"] = datetime.now(timezone.utc).isoformat()

    if custom_metadata:
        video_metadata = metadata_service.merge_metadata(video_metadata, custom_metadata)

    return video_metadata


def increment_usage_counters(
    db: Session,
    api_key: APIKey,
    file_size: int
) -> None:
    """
    Increment job and storage usage counters.

    Args:
        db: Database session
        api_key: API key to update
        file_size: Size of file in bytes
    """
    increment_jobs_usage(db, api_key)
    increment_storage_usage(db, api_key, file_size)
