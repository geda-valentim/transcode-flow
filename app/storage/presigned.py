"""
Presigned URL Generator Service

Sprint 4: Storage & File Management

Generates temporary presigned URLs for secure file access without authentication.
Implements:
- Download URLs (GET)
- Upload URLs (PUT)
- Configurable expiration times
- URL validation
- Access logging
"""
import logging
from datetime import timedelta
from typing import Optional, Dict, Any
from dataclasses import dataclass
from datetime import datetime
from minio import Minio
from minio.error import S3Error

logger = logging.getLogger(__name__)


@dataclass
class PresignedURL:
    """
    Presigned URL with metadata
    """
    url: str
    object_name: str
    bucket_name: str
    method: str  # GET, PUT
    expires_in_seconds: int
    created_at: datetime
    expires_at: datetime

    def is_expired(self) -> bool:
        """Check if URL has expired"""
        return datetime.utcnow() > self.expires_at

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'url': self.url,
            'object_name': self.object_name,
            'bucket_name': self.bucket_name,
            'method': self.method,
            'expires_in_seconds': self.expires_in_seconds,
            'created_at': self.created_at.isoformat(),
            'expires_at': self.expires_at.isoformat(),
            'is_expired': self.is_expired()
        }


class PresignedURLGenerator:
    """
    MinIO presigned URL generator

    Features:
    - Secure temporary URLs for downloads and uploads
    - Configurable expiration times
    - Support for custom response headers
    - URL tracking and validation
    - Batch URL generation
    """

    # Default expiration times
    DEFAULT_DOWNLOAD_EXPIRY = timedelta(hours=1)
    DEFAULT_UPLOAD_EXPIRY = timedelta(minutes=15)
    MAX_EXPIRY = timedelta(days=7)

    def __init__(
        self,
        minio_client: Minio,
        bucket_name: str,
        default_download_expiry: Optional[timedelta] = None,
        default_upload_expiry: Optional[timedelta] = None
    ):
        """
        Initialize presigned URL generator

        Args:
            minio_client: MinIO client instance
            bucket_name: Target bucket name
            default_download_expiry: Default download URL expiration
            default_upload_expiry: Default upload URL expiration
        """
        self.client = minio_client
        self.bucket_name = bucket_name
        self.default_download_expiry = default_download_expiry or self.DEFAULT_DOWNLOAD_EXPIRY
        self.default_upload_expiry = default_upload_expiry or self.DEFAULT_UPLOAD_EXPIRY

        logger.info(
            f"PresignedURLGenerator initialized for bucket '{bucket_name}' "
            f"(download: {self.default_download_expiry}, upload: {self.default_upload_expiry})"
        )

    def generate_download_url(
        self,
        object_name: str,
        expires: Optional[timedelta] = None,
        response_headers: Optional[Dict[str, str]] = None
    ) -> PresignedURL:
        """
        Generate presigned URL for downloading an object

        Args:
            object_name: Object key in bucket
            expires: URL expiration time (default: 1 hour)
            response_headers: Optional headers to include in response
                             (e.g., {'response-content-type': 'application/octet-stream'})

        Returns:
            PresignedURL object with download URL

        Example:
            url = generator.generate_download_url(
                'videos/abc123/output.mp4',
                expires=timedelta(hours=2),
                response_headers={
                    'response-content-disposition': 'attachment; filename="video.mp4"'
                }
            )
        """
        expires = expires or self.default_download_expiry

        # Validate expiration
        if expires > self.MAX_EXPIRY:
            logger.warning(f"Expiry time {expires} exceeds maximum {self.MAX_EXPIRY}, capping")
            expires = self.MAX_EXPIRY

        try:
            # Generate presigned GET URL
            url = self.client.presigned_get_object(
                self.bucket_name,
                object_name,
                expires=expires,
                response_headers=response_headers
            )

            created_at = datetime.utcnow()
            expires_at = created_at + expires

            presigned_url = PresignedURL(
                url=url,
                object_name=object_name,
                bucket_name=self.bucket_name,
                method='GET',
                expires_in_seconds=int(expires.total_seconds()),
                created_at=created_at,
                expires_at=expires_at
            )

            logger.info(
                f"Generated download URL for '{object_name}' "
                f"(expires in {expires.total_seconds() / 3600:.1f}h)"
            )

            return presigned_url

        except S3Error as e:
            logger.error(f"Failed to generate download URL for '{object_name}': {e}")
            raise

    def generate_upload_url(
        self,
        object_name: str,
        expires: Optional[timedelta] = None
    ) -> PresignedURL:
        """
        Generate presigned URL for uploading an object

        Args:
            object_name: Object key in bucket
            expires: URL expiration time (default: 15 minutes)

        Returns:
            PresignedURL object with upload URL

        Example:
            url = generator.generate_upload_url(
                'uploads/user123/video.mp4',
                expires=timedelta(minutes=30)
            )
        """
        expires = expires or self.default_upload_expiry

        # Validate expiration
        if expires > self.MAX_EXPIRY:
            logger.warning(f"Expiry time {expires} exceeds maximum {self.MAX_EXPIRY}, capping")
            expires = self.MAX_EXPIRY

        try:
            # Generate presigned PUT URL
            url = self.client.presigned_put_object(
                self.bucket_name,
                object_name,
                expires=expires
            )

            created_at = datetime.utcnow()
            expires_at = created_at + expires

            presigned_url = PresignedURL(
                url=url,
                object_name=object_name,
                bucket_name=self.bucket_name,
                method='PUT',
                expires_in_seconds=int(expires.total_seconds()),
                created_at=created_at,
                expires_at=expires_at
            )

            logger.info(
                f"Generated upload URL for '{object_name}' "
                f"(expires in {expires.total_seconds() / 60:.1f}m)"
            )

            return presigned_url

        except S3Error as e:
            logger.error(f"Failed to generate upload URL for '{object_name}': {e}")
            raise

    def generate_batch_download_urls(
        self,
        object_names: list[str],
        expires: Optional[timedelta] = None,
        response_headers: Optional[Dict[str, str]] = None
    ) -> Dict[str, PresignedURL]:
        """
        Generate multiple download URLs at once

        Args:
            object_names: List of object keys
            expires: URL expiration time
            response_headers: Optional headers for all URLs

        Returns:
            Dictionary mapping object names to PresignedURL objects
        """
        urls = {}

        for object_name in object_names:
            try:
                url = self.generate_download_url(
                    object_name,
                    expires=expires,
                    response_headers=response_headers
                )
                urls[object_name] = url
            except Exception as e:
                logger.error(f"Failed to generate URL for '{object_name}': {e}")
                continue

        logger.info(f"Generated {len(urls)} download URLs from {len(object_names)} requests")

        return urls

    def generate_video_outputs_urls(
        self,
        job_id: str,
        expires: Optional[timedelta] = None
    ) -> Dict[str, str]:
        """
        Generate presigned URLs for all video outputs of a job

        Args:
            job_id: Job ID
            expires: URL expiration time

        Returns:
            Dictionary with URLs for each output type
        """
        outputs = {
            '360p_video': f'jobs/{job_id}/outputs/360p.mp4',
            '720p_video': f'jobs/{job_id}/outputs/720p.mp4',
            'audio': f'jobs/{job_id}/outputs/audio.mp3',
            'thumbnail': f'jobs/{job_id}/outputs/thumbnail.jpg',
            'hls_360p_playlist': f'jobs/{job_id}/outputs/hls/360p/playlist.m3u8',
            'hls_720p_playlist': f'jobs/{job_id}/outputs/hls/720p/playlist.m3u8',
            'transcription_txt': f'jobs/{job_id}/outputs/transcription/audio.txt',
            'transcription_srt': f'jobs/{job_id}/outputs/transcription/audio.srt',
            'transcription_vtt': f'jobs/{job_id}/outputs/transcription/audio.vtt',
            'transcription_json': f'jobs/{job_id}/outputs/transcription/audio.json',
        }

        urls = {}

        for output_type, object_name in outputs.items():
            try:
                # Check if object exists
                self.client.stat_object(self.bucket_name, object_name)

                # Generate URL
                presigned_url = self.generate_download_url(object_name, expires=expires)
                urls[output_type] = presigned_url.url

            except S3Error as e:
                if e.code == 'NoSuchKey':
                    logger.debug(f"Output not found: {object_name}")
                else:
                    logger.error(f"Error checking {object_name}: {e}")

        logger.info(f"Generated {len(urls)} output URLs for job '{job_id}'")

        return urls

    def generate_hls_manifest_urls(
        self,
        job_id: str,
        resolution: str,
        expires: Optional[timedelta] = None
    ) -> Dict[str, str]:
        """
        Generate URLs for HLS manifest and segments

        Args:
            job_id: Job ID
            resolution: '360p' or '720p'
            expires: URL expiration time

        Returns:
            Dictionary with playlist and segment URLs
        """
        base_path = f'jobs/{job_id}/outputs/hls/{resolution}'
        urls = {}

        try:
            # Generate playlist URL
            playlist_path = f'{base_path}/playlist.m3u8'
            playlist_url = self.generate_download_url(
                playlist_path,
                expires=expires,
                response_headers={'response-content-type': 'application/vnd.apple.mpegurl'}
            )
            urls['playlist'] = playlist_url.url

            # List all segment files
            objects = self.client.list_objects(
                self.bucket_name,
                prefix=f'{base_path}/',
                recursive=True
            )

            segment_urls = {}
            for obj in objects:
                if obj.object_name.endswith('.ts'):
                    segment_name = obj.object_name.split('/')[-1]
                    segment_url = self.generate_download_url(
                        obj.object_name,
                        expires=expires,
                        response_headers={'response-content-type': 'video/MP2T'}
                    )
                    segment_urls[segment_name] = segment_url.url

            urls['segments'] = segment_urls

            logger.info(
                f"Generated HLS URLs for job '{job_id}' {resolution}: "
                f"1 playlist + {len(segment_urls)} segments"
            )

        except S3Error as e:
            logger.error(f"Failed to generate HLS URLs for '{job_id}' {resolution}: {e}")

        return urls

    def get_direct_download_url(
        self,
        object_name: str,
        filename: Optional[str] = None,
        expires: Optional[timedelta] = None
    ) -> PresignedURL:
        """
        Generate download URL with content-disposition header for direct download

        Args:
            object_name: Object key in bucket
            filename: Optional custom filename for download
            expires: URL expiration time

        Returns:
            PresignedURL with attachment disposition
        """
        if not filename:
            filename = object_name.split('/')[-1]

        response_headers = {
            'response-content-disposition': f'attachment; filename="{filename}"'
        }

        return self.generate_download_url(
            object_name,
            expires=expires,
            response_headers=response_headers
        )

    def get_inline_view_url(
        self,
        object_name: str,
        content_type: Optional[str] = None,
        expires: Optional[timedelta] = None
    ) -> PresignedURL:
        """
        Generate URL for inline viewing (e.g., video player)

        Args:
            object_name: Object key in bucket
            content_type: Optional content type (e.g., 'video/mp4')
            expires: URL expiration time

        Returns:
            PresignedURL with inline disposition
        """
        response_headers = {
            'response-content-disposition': 'inline'
        }

        if content_type:
            response_headers['response-content-type'] = content_type

        return self.generate_download_url(
            object_name,
            expires=expires,
            response_headers=response_headers
        )
