"""
Download API Endpoints

Sprint 4: Storage & File Management

Provides secure download endpoints using presigned URLs for:
- Job outputs (videos, audio, transcriptions)
- HLS streaming manifests
- Thumbnails
- Individual files
"""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from datetime import timedelta
from pydantic import BaseModel

from app.core.config import settings
from app.core.minio_client import get_minio_client
from app.storage.presigned import PresignedURLGenerator

router = APIRouter(prefix="/downloads", tags=["downloads"])


# ============================================================================
# Response Models
# ============================================================================

class PresignedURLResponse(BaseModel):
    """Response model for presigned URL"""
    url: str
    object_name: str
    expires_in_seconds: int
    created_at: str
    expires_at: str


class JobOutputURLsResponse(BaseModel):
    """Response model for job output URLs"""
    job_id: str
    urls: dict


class HLSManifestResponse(BaseModel):
    """Response model for HLS manifest URLs"""
    job_id: str
    resolution: str
    playlist_url: str
    segments: dict


# ============================================================================
# Endpoints
# ============================================================================

@router.get("/job/{job_id}/outputs", response_model=JobOutputURLsResponse)
async def get_job_output_urls(
    job_id: str,
    expires_hours: int = Query(default=1, ge=1, le=24, description="URL expiration in hours")
):
    """
    Get presigned URLs for all outputs of a job

    Returns URLs for:
    - 360p and 720p videos
    - Audio (MP3)
    - Thumbnail
    - HLS playlists
    - Transcription files (TXT, SRT, VTT, JSON)

    **Parameters:**
    - job_id: The job ID
    - expires_hours: URL expiration time (1-24 hours)

    **Returns:**
    Dictionary with presigned URLs for each available output
    """
    client = get_minio_client()

    url_generator = PresignedURLGenerator(
        client,
        settings.MINIO_BUCKET_NAME,
        default_download_expiry=timedelta(hours=expires_hours)
    )

    try:
        urls = url_generator.generate_video_outputs_urls(
            job_id,
            expires=timedelta(hours=expires_hours)
        )

        if not urls:
            raise HTTPException(
                status_code=404,
                detail=f"No outputs found for job '{job_id}'"
            )

        return JobOutputURLsResponse(
            job_id=job_id,
            urls=urls
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate URLs: {str(e)}"
        )


@router.get("/job/{job_id}/video/{resolution}", response_model=PresignedURLResponse)
async def get_video_download_url(
    job_id: str,
    resolution: str,
    expires_hours: int = Query(default=1, ge=1, le=24),
    download: bool = Query(default=False, description="Force download instead of inline view")
):
    """
    Get presigned URL for downloading a specific video resolution

    **Parameters:**
    - job_id: The job ID
    - resolution: Video resolution ('360p' or '720p')
    - expires_hours: URL expiration time (1-24 hours)
    - download: If true, force browser download instead of inline playback

    **Returns:**
    Presigned URL for the requested video
    """
    if resolution not in ['360p', '720p']:
        raise HTTPException(
            status_code=400,
            detail="Resolution must be '360p' or '720p'"
        )

    client = get_minio_client()

    url_generator = PresignedURLGenerator(
        client,
        settings.MINIO_BUCKET_NAME
    )

    object_name = f'jobs/{job_id}/outputs/{resolution}.mp4'

    try:
        if download:
            presigned_url = url_generator.get_direct_download_url(
                object_name,
                filename=f"{job_id}_{resolution}.mp4",
                expires=timedelta(hours=expires_hours)
            )
        else:
            presigned_url = url_generator.get_inline_view_url(
                object_name,
                content_type='video/mp4',
                expires=timedelta(hours=expires_hours)
            )

        return PresignedURLResponse(**presigned_url.to_dict())

    except Exception as e:
        raise HTTPException(
            status_code=404,
            detail=f"Video not found or failed to generate URL: {str(e)}"
        )


@router.get("/job/{job_id}/audio", response_model=PresignedURLResponse)
async def get_audio_download_url(
    job_id: str,
    expires_hours: int = Query(default=1, ge=1, le=24)
):
    """
    Get presigned URL for downloading job audio (MP3)

    **Parameters:**
    - job_id: The job ID
    - expires_hours: URL expiration time (1-24 hours)

    **Returns:**
    Presigned URL for the audio file
    """
    client = get_minio_client()

    url_generator = PresignedURLGenerator(
        client,
        settings.MINIO_BUCKET_NAME
    )

    object_name = f'jobs/{job_id}/outputs/audio.mp3'

    try:
        presigned_url = url_generator.get_direct_download_url(
            object_name,
            filename=f"{job_id}_audio.mp3",
            expires=timedelta(hours=expires_hours)
        )

        return PresignedURLResponse(**presigned_url.to_dict())

    except Exception as e:
        raise HTTPException(
            status_code=404,
            detail=f"Audio file not found: {str(e)}"
        )


@router.get("/job/{job_id}/thumbnail", response_model=PresignedURLResponse)
async def get_thumbnail_url(
    job_id: str,
    expires_hours: int = Query(default=1, ge=1, le=24)
):
    """
    Get presigned URL for job thumbnail

    **Parameters:**
    - job_id: The job ID
    - expires_hours: URL expiration time (1-24 hours)

    **Returns:**
    Presigned URL for the thumbnail image
    """
    client = get_minio_client()

    url_generator = PresignedURLGenerator(
        client,
        settings.MINIO_BUCKET_NAME
    )

    object_name = f'jobs/{job_id}/outputs/thumbnail.jpg'

    try:
        presigned_url = url_generator.get_inline_view_url(
            object_name,
            content_type='image/jpeg',
            expires=timedelta(hours=expires_hours)
        )

        return PresignedURLResponse(**presigned_url.to_dict())

    except Exception as e:
        raise HTTPException(
            status_code=404,
            detail=f"Thumbnail not found: {str(e)}"
        )


@router.get("/job/{job_id}/transcription/{format}", response_model=PresignedURLResponse)
async def get_transcription_url(
    job_id: str,
    format: str,
    expires_hours: int = Query(default=1, ge=1, le=24)
):
    """
    Get presigned URL for transcription file

    **Parameters:**
    - job_id: The job ID
    - format: Transcription format ('txt', 'srt', 'vtt', 'json')
    - expires_hours: URL expiration time (1-24 hours)

    **Returns:**
    Presigned URL for the transcription file
    """
    if format not in ['txt', 'srt', 'vtt', 'json']:
        raise HTTPException(
            status_code=400,
            detail="Format must be one of: txt, srt, vtt, json"
        )

    client = get_minio_client()

    url_generator = PresignedURLGenerator(
        client,
        settings.MINIO_BUCKET_NAME
    )

    object_name = f'jobs/{job_id}/outputs/transcription/audio.{format}'

    # Set content type based on format
    content_types = {
        'txt': 'text/plain',
        'srt': 'text/plain',
        'vtt': 'text/vtt',
        'json': 'application/json'
    }

    try:
        presigned_url = url_generator.generate_download_url(
            object_name,
            expires=timedelta(hours=expires_hours),
            response_headers={
                'response-content-type': content_types[format],
                'response-content-disposition': f'attachment; filename="{job_id}_transcription.{format}"'
            }
        )

        return PresignedURLResponse(**presigned_url.to_dict())

    except Exception as e:
        raise HTTPException(
            status_code=404,
            detail=f"Transcription file not found: {str(e)}"
        )


@router.get("/job/{job_id}/hls/{resolution}", response_model=HLSManifestResponse)
async def get_hls_manifest_urls(
    job_id: str,
    resolution: str,
    expires_hours: int = Query(default=2, ge=1, le=24)
):
    """
    Get presigned URLs for HLS streaming (playlist + segments)

    **Parameters:**
    - job_id: The job ID
    - resolution: Video resolution ('360p' or '720p')
    - expires_hours: URL expiration time (1-24 hours)

    **Returns:**
    HLS playlist URL and all segment URLs
    """
    if resolution not in ['360p', '720p']:
        raise HTTPException(
            status_code=400,
            detail="Resolution must be '360p' or '720p'"
        )

    client = get_minio_client()

    url_generator = PresignedURLGenerator(
        client,
        settings.MINIO_BUCKET_NAME
    )

    try:
        hls_urls = url_generator.generate_hls_manifest_urls(
            job_id,
            resolution,
            expires=timedelta(hours=expires_hours)
        )

        if 'playlist' not in hls_urls:
            raise HTTPException(
                status_code=404,
                detail=f"HLS manifest not found for job '{job_id}' ({resolution})"
            )

        return HLSManifestResponse(
            job_id=job_id,
            resolution=resolution,
            playlist_url=hls_urls['playlist'],
            segments=hls_urls.get('segments', {})
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate HLS URLs: {str(e)}"
        )


@router.get("/object", response_model=PresignedURLResponse)
async def get_object_download_url(
    object_name: str = Query(..., description="Full object path in bucket"),
    expires_hours: int = Query(default=1, ge=1, le=24),
    filename: Optional[str] = Query(None, description="Custom download filename")
):
    """
    Get presigned URL for any object in the bucket

    **Parameters:**
    - object_name: Full path to object (e.g., 'jobs/abc123/outputs/360p.mp4')
    - expires_hours: URL expiration time (1-24 hours)
    - filename: Optional custom filename for download

    **Returns:**
    Presigned URL for the object

    **Note:** This is a generic endpoint. Prefer using specific endpoints for common file types.
    """
    client = get_minio_client()

    url_generator = PresignedURLGenerator(
        client,
        settings.MINIO_BUCKET_NAME
    )

    try:
        presigned_url = url_generator.get_direct_download_url(
            object_name,
            filename=filename,
            expires=timedelta(hours=expires_hours)
        )

        return PresignedURLResponse(**presigned_url.to_dict())

    except Exception as e:
        raise HTTPException(
            status_code=404,
            detail=f"Object not found: {str(e)}"
        )
