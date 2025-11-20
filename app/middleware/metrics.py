"""
FastAPI middleware for automatic Prometheus metrics collection.

This middleware tracks:
- Total API requests with method, endpoint, and status labels
- Request duration histograms
- In-progress request gauges
"""
import time
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.metrics import (
    api_requests_total,
    api_request_duration_seconds,
    api_requests_in_progress,
)


class MetricsMiddleware(BaseHTTPMiddleware):
    """
    Middleware to automatically track API request metrics.

    Features:
    - Tracks total requests per endpoint
    - Measures request duration
    - Tracks in-progress requests
    - Excludes metrics endpoint from tracking to avoid feedback loops
    """

    def __init__(self, app: ASGIApp):
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process request and collect metrics.

        Args:
            request: FastAPI request object
            call_next: Next middleware/handler in chain

        Returns:
            Response object
        """
        # Extract method and path
        method = request.method
        path = request.url.path

        # Skip metrics collection for the /metrics endpoint itself
        # to avoid infinite loops and metric pollution
        if path == "/metrics":
            return await call_next(request)

        # Normalize path to remove dynamic segments for better metric grouping
        # e.g., /jobs/abc123 -> /jobs/{job_id}
        normalized_path = self._normalize_path(path)

        # Track in-progress requests
        api_requests_in_progress.labels(method=method, endpoint=normalized_path).inc()

        # Start timer
        start_time = time.time()

        try:
            # Process request
            response = await call_next(request)
            status_code = response.status_code

            # Record request metrics
            duration = time.time() - start_time
            api_requests_total.labels(
                method=method,
                endpoint=normalized_path,
                status=status_code
            ).inc()
            api_request_duration_seconds.labels(
                method=method,
                endpoint=normalized_path
            ).observe(duration)

            return response

        except Exception as e:
            # Record error metrics
            duration = time.time() - start_time
            api_requests_total.labels(
                method=method,
                endpoint=normalized_path,
                status=500
            ).inc()
            api_request_duration_seconds.labels(
                method=method,
                endpoint=normalized_path
            ).observe(duration)

            # Re-raise exception for FastAPI error handling
            raise

        finally:
            # Decrement in-progress requests
            api_requests_in_progress.labels(
                method=method,
                endpoint=normalized_path
            ).dec()

    def _normalize_path(self, path: str) -> str:
        """
        Normalize URL path by replacing dynamic segments with placeholders.

        This prevents high cardinality in Prometheus metrics by grouping
        similar paths together.

        Examples:
            /api/v1/jobs/abc123 -> /api/v1/jobs/{job_id}
            /api/v1/jobs/abc123/cancel -> /api/v1/jobs/{job_id}/cancel
            /downloads/job/abc123/video/720p -> /downloads/job/{job_id}/video/{resolution}
            /events/abc123/progress -> /events/{job_id}/progress

        Args:
            path: Original request path

        Returns:
            Normalized path with placeholders
        """
        parts = path.split("/")
        normalized_parts = []

        i = 0
        while i < len(parts):
            part = parts[i]

            # Empty parts (from leading/trailing slashes)
            if not part:
                normalized_parts.append(part)
                i += 1
                continue

            # Check for common patterns
            # Pattern: /jobs/{job_id}
            if i > 0 and parts[i - 1] == "jobs" and self._is_job_id(part):
                normalized_parts.append("{job_id}")
                i += 1
                continue

            # Pattern: /events/{job_id}
            if i > 0 and parts[i - 1] == "events" and self._is_job_id(part):
                normalized_parts.append("{job_id}")
                i += 1
                continue

            # Pattern: /job/{job_id} (downloads endpoint)
            if i > 0 and parts[i - 1] == "job" and self._is_job_id(part):
                normalized_parts.append("{job_id}")
                i += 1
                continue

            # Pattern: /video/{resolution} or /audio/{format}
            if i > 0 and parts[i - 1] in ["video", "audio"] and self._is_format_or_resolution(part):
                normalized_parts.append(f"{{{parts[i - 1]}_format}}")
                i += 1
                continue

            # Pattern: /keys/{key_prefix}
            if i > 0 and parts[i - 1] == "keys" and len(part) >= 8:
                normalized_parts.append("{key_prefix}")
                i += 1
                continue

            # Default: keep part as-is
            normalized_parts.append(part)
            i += 1

        return "/".join(normalized_parts)

    def _is_job_id(self, value: str) -> bool:
        """
        Check if a path segment looks like a job ID.

        Job IDs are typically:
        - Length between 8-64 characters
        - Alphanumeric with possible hyphens/underscores

        Args:
            value: Path segment to check

        Returns:
            True if likely a job ID
        """
        if len(value) < 8 or len(value) > 64:
            return False

        # Check if it's alphanumeric with hyphens/underscores
        return value.replace("-", "").replace("_", "").isalnum()

    def _is_format_or_resolution(self, value: str) -> bool:
        """
        Check if a path segment looks like a format or resolution.

        Common formats: mp4, webm, m4a, mp3, wav, 360p, 720p, 1080p, 4k

        Args:
            value: Path segment to check

        Returns:
            True if likely a format or resolution
        """
        common_formats = [
            "mp4", "webm", "mkv", "avi", "mov",
            "m4a", "mp3", "aac", "wav", "flac", "ogg",
            "360p", "480p", "720p", "1080p", "1440p", "4k",
            "srt", "vtt", "txt", "json"
        ]

        return value.lower() in common_formats
