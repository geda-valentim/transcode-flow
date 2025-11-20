"""
Webhook notification service with retry logic.

This service handles sending webhook notifications for job events
with automatic retry on failure and HMAC signature verification.
"""
import requests
import hmac
import hashlib
import json
import time
from typing import Dict, Any, Optional
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from app.models.job import Job, JobStatus
from app.models.api_key import APIKey


class WebhookNotifier:
    """
    Sends webhook notifications for job events with retry logic.

    Features:
    - HMAC-SHA256 signature for webhook verification
    - Automatic retry with exponential backoff
    - Support for multiple event types
    - Configurable timeout and retry attempts
    """

    # Retry configuration
    MAX_RETRIES = 3
    RETRY_DELAY_BASE = 2  # seconds
    REQUEST_TIMEOUT = 10  # seconds

    def __init__(self, db_session: Session):
        """
        Initialize webhook notifier.

        Args:
            db_session: SQLAlchemy database session
        """
        self.db = db_session

    def send_notification(
        self,
        job: Job,
        event: str,
        extra_data: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Send webhook notification for a job event.

        Args:
            job: Job object
            event: Event type (e.g., "job.completed", "job.failed", "job.progress")
            extra_data: Additional data to include in the payload

        Returns:
            bool: True if notification was sent successfully, False otherwise
        """
        # Get API key for webhook configuration
        api_key = self.db.query(APIKey).filter(
            APIKey.id == job.api_key_id
        ).first()

        if not api_key:
            print(f"⚠️  API key not found for job {job.job_id}")
            return False

        # Check if webhook URL is configured
        webhook_url = api_key.key_metadata.get("webhook_url") if api_key.key_metadata else None
        if not webhook_url:
            # No webhook configured, skip silently
            return True

        # Check if this event type is enabled
        webhook_events = api_key.key_metadata.get("webhook_events", ["job.completed", "job.failed"]) if api_key.key_metadata else ["job.completed", "job.failed"]
        if event not in webhook_events:
            # Event not enabled, skip
            return True

        # Build payload
        payload = self._build_payload(job, event, extra_data)

        # Get webhook secret for signature
        webhook_secret = api_key.key_metadata.get("webhook_secret") if api_key.key_metadata else None

        # Generate signature
        signature = self._generate_signature(payload, webhook_secret or "")

        # Send webhook with retry logic
        success = self._send_with_retry(webhook_url, payload, signature)

        # Update job webhook status
        if success:
            job.webhook_sent = True
            self.db.commit()
            print(f"✅ Webhook sent successfully: {event} for job {job.job_id}")
        else:
            print(f"❌ Webhook failed after {self.MAX_RETRIES} retries: {event} for job {job.job_id}")

        return success

    def _build_payload(
        self,
        job: Job,
        event: str,
        extra_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Build webhook payload with job information.

        Args:
            job: Job object
            event: Event type
            extra_data: Additional data to include

        Returns:
            dict: Webhook payload
        """
        payload = {
            "event": event,
            "job_id": job.job_id,
            "status": job.status.value,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": {
                "source_filename": job.source_filename,
                "source_duration_seconds": float(job.source_duration_seconds) if job.source_duration_seconds else None,
                "source_size_bytes": job.source_size_bytes,
                "source_resolution": job.source_resolution,
                "priority": job.priority,
                "created_at": job.created_at.isoformat() if job.created_at else None,
                "updated_at": job.updated_at.isoformat() if job.updated_at else None,
            }
        }

        # Add event-specific data
        if event == "job.completed":
            payload["data"]["outputs"] = {
                "hls_manifest_url": job.hls_manifest_url,
                "audio_file_url": job.audio_file_url,
                "transcription_url": job.transcription_url,
                "thumbnail_url": job.thumbnail_url,
                "output_formats": job.output_formats,
            }
            payload["data"]["processing"] = {
                "started_at": job.processing_started_at.isoformat() if job.processing_started_at else None,
                "completed_at": job.processing_completed_at.isoformat() if job.processing_completed_at else None,
                "duration_seconds": job.processing_duration_seconds,
                "compression_ratio": float(job.compression_ratio) if job.compression_ratio else None,
                "output_total_size_bytes": job.output_total_size_bytes,
            }

        elif event == "job.failed":
            payload["data"]["error"] = {
                "message": job.error_message,
                "retry_count": job.retry_count,
            }

        elif event == "job.progress":
            payload["data"]["progress"] = {
                "processing_started_at": job.processing_started_at.isoformat() if job.processing_started_at else None,
            }

        # Merge extra data if provided
        if extra_data:
            payload["data"].update(extra_data)

        return payload

    def _generate_signature(self, payload: Dict[str, Any], secret: str) -> str:
        """
        Generate HMAC-SHA256 signature for webhook verification.

        Args:
            payload: Webhook payload
            secret: Webhook secret key

        Returns:
            str: Hex-encoded HMAC signature
        """
        # Convert payload to JSON string with sorted keys for consistency
        message = json.dumps(payload, sort_keys=True).encode('utf-8')

        # Generate HMAC signature
        signature = hmac.new(
            secret.encode('utf-8'),
            message,
            hashlib.sha256
        ).hexdigest()

        return signature

    def _send_with_retry(
        self,
        url: str,
        payload: Dict[str, Any],
        signature: str
    ) -> bool:
        """
        Send webhook with exponential backoff retry logic.

        Args:
            url: Webhook URL
            payload: Webhook payload
            signature: HMAC signature

        Returns:
            bool: True if successful, False after all retries exhausted
        """
        headers = {
            "Content-Type": "application/json",
            "X-Webhook-Signature": signature,
            "X-Webhook-Event": payload["event"],
            "X-Webhook-Timestamp": payload["timestamp"],
            "User-Agent": "Transcode-Flow-Webhook/1.0"
        }

        for attempt in range(self.MAX_RETRIES):
            try:
                # Send POST request
                response = requests.post(
                    url,
                    json=payload,
                    headers=headers,
                    timeout=self.REQUEST_TIMEOUT
                )

                # Check if successful (2xx status code)
                if 200 <= response.status_code < 300:
                    return True

                # Log error and retry
                print(f"⚠️  Webhook attempt {attempt + 1}/{self.MAX_RETRIES} failed "
                      f"with status {response.status_code}: {response.text[:200]}")

            except requests.exceptions.Timeout:
                print(f"⚠️  Webhook attempt {attempt + 1}/{self.MAX_RETRIES} timed out after {self.REQUEST_TIMEOUT}s")

            except requests.exceptions.RequestException as e:
                print(f"⚠️  Webhook attempt {attempt + 1}/{self.MAX_RETRIES} failed with error: {str(e)[:200]}")

            # Wait before retry (exponential backoff)
            if attempt < self.MAX_RETRIES - 1:
                delay = self.RETRY_DELAY_BASE ** (attempt + 1)
                print(f"   Retrying in {delay} seconds...")
                time.sleep(delay)

        # All retries exhausted
        return False

    @staticmethod
    def verify_signature(payload: str, signature: str, secret: str) -> bool:
        """
        Verify webhook signature (for webhook receivers).

        Args:
            payload: Raw payload string
            signature: Received signature
            secret: Webhook secret

        Returns:
            bool: True if signature is valid
        """
        expected_signature = hmac.new(
            secret.encode('utf-8'),
            payload.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

        return hmac.compare_digest(signature, expected_signature)
