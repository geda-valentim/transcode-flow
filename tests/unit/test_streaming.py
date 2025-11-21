"""
Unit tests for Streaming Token endpoints.
Tests endpoints from app/api/v1/endpoints/streaming.py
"""
import pytest
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime, timezone, timedelta
from fastapi import HTTPException
import jwt

from app.models.api_key import APIKey
from app.models.job import Job


@pytest.fixture
def sample_job(db, master_api_key):
    """Create a sample completed job for testing."""
    job = Job(
        id="test-job-123",
        api_key_prefix=master_api_key.key_prefix,
        input_url="https://example.com/video.mp4",
        status="completed",
        output_files={
            "hls": {
                "1080p": {
                    "manifest": "jobs/test-job-123/hls/1080p/manifest.m3u8",
                    "segments": ["jobs/test-job-123/hls/1080p/segment_0.ts"],
                },
                "720p": {
                    "manifest": "jobs/test-job-123/hls/720p/manifest.m3u8",
                    "segments": ["jobs/test-job-123/hls/720p/segment_0.ts"],
                },
            }
        },
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


@pytest.mark.unit
class TestGenerateStreamingTokens:
    """Test POST /streaming/tokens endpoint."""

    def test_generate_tokens_success(self, authenticated_client, sample_job):
        """Test successful token generation."""
        response = authenticated_client.post(
            "/api/v1/streaming/tokens",
            json={
                "job_id": sample_job.id,
                "expires_in_seconds": 3600,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["job_id"] == sample_job.id
        assert "tokens" in data
        assert "1080p" in data["tokens"]
        assert "720p" in data["tokens"]
        assert data["expires_at"] is not None

    def test_generate_tokens_with_ip_restriction(self, authenticated_client, sample_job):
        """Test token generation with IP whitelist."""
        response = authenticated_client.post(
            "/api/v1/streaming/tokens",
            json={
                "job_id": sample_job.id,
                "allowed_ips": ["192.168.1.100"],
                "expires_in_seconds": 1800,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["allowed_ips"] == ["192.168.1.100"]

    def test_generate_tokens_with_max_uses(self, authenticated_client, sample_job):
        """Test token generation with usage limit."""
        response = authenticated_client.post(
            "/api/v1/streaming/tokens",
            json={
                "job_id": sample_job.id,
                "max_uses": 10,
                "expires_in_seconds": 3600,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["max_uses"] == 10

    def test_generate_tokens_job_not_found(self, authenticated_client):
        """Test token generation for non-existent job."""
        response = authenticated_client.post(
            "/api/v1/streaming/tokens",
            json={
                "job_id": "non-existent-job",
                "expires_in_seconds": 3600,
            },
        )

        assert response.status_code == 403

    def test_generate_tokens_wrong_api_key(self, client, sample_job, sub_api_key, db):
        """Test token generation for job owned by different API key."""
        # Change job owner
        sample_job.api_key_prefix = "different_prefix"
        db.commit()

        client.headers = {"X-API-Key": sub_api_key._test_key}
        response = client.post(
            "/api/v1/streaming/tokens",
            json={
                "job_id": sample_job.id,
                "expires_in_seconds": 3600,
            },
        )

        assert response.status_code == 403

    def test_generate_tokens_job_not_completed(self, authenticated_client, sample_job, db):
        """Test token generation for incomplete job."""
        sample_job.status = "processing"
        db.commit()

        response = authenticated_client.post(
            "/api/v1/streaming/tokens",
            json={
                "job_id": sample_job.id,
                "expires_in_seconds": 3600,
            },
        )

        assert response.status_code == 400
        assert "must be completed" in response.json()["detail"]

    def test_generate_tokens_no_hls_output(self, authenticated_client, sample_job, db):
        """Test token generation for job without HLS output."""
        sample_job.output_files = {"mp4": {"720p": "some_file.mp4"}}
        db.commit()

        response = authenticated_client.post(
            "/api/v1/streaming/tokens",
            json={
                "job_id": sample_job.id,
                "expires_in_seconds": 3600,
            },
        )

        assert response.status_code == 400
        assert "No HLS outputs" in response.json()["detail"]


@pytest.mark.unit
class TestValidateStreamingToken:
    """Test GET /streaming/validate-token endpoint."""

    @patch("app.services.streaming_tokens.StreamingTokenService")
    def test_validate_token_success(self, mock_service_class, authenticated_client):
        """Test successful token validation."""
        mock_service = MagicMock()
        mock_service.validate_token.return_value = {
            "job_id": "test-job-123",
            "api_key_prefix": "tfk_test",
            "allowed_ips": None,
            "max_uses": None,
        }
        mock_service_class.return_value = mock_service

        response = authenticated_client.get(
            "/api/v1/streaming/validate-token",
            headers={"X-Stream-Token": "valid.token.here"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True
        assert data["job_id"] == "test-job-123"

    @patch("app.services.streaming_tokens.StreamingTokenService")
    def test_validate_token_expired(self, mock_service_class, authenticated_client):
        """Test validation of expired token."""
        mock_service = MagicMock()
        mock_service.validate_token.side_effect = jwt.ExpiredSignatureError()
        mock_service_class.return_value = mock_service

        response = authenticated_client.get(
            "/api/v1/streaming/validate-token",
            headers={"X-Stream-Token": "expired.token.here"},
        )

        assert response.status_code == 401
        assert "expired" in response.json()["detail"].lower()

    @patch("app.services.streaming_tokens.StreamingTokenService")
    def test_validate_token_invalid(self, mock_service_class, authenticated_client):
        """Test validation of invalid token."""
        mock_service = MagicMock()
        mock_service.validate_token.side_effect = jwt.InvalidTokenError()
        mock_service_class.return_value = mock_service

        response = authenticated_client.get(
            "/api/v1/streaming/validate-token",
            headers={"X-Stream-Token": "invalid.token.here"},
        )

        assert response.status_code == 401
        assert "Invalid" in response.json()["detail"]

    def test_validate_token_missing(self, authenticated_client):
        """Test validation without token header."""
        response = authenticated_client.get("/api/v1/streaming/validate-token")

        assert response.status_code == 400
        assert "required" in response.json()["detail"].lower()

    @patch("app.services.streaming_tokens.StreamingTokenService")
    def test_validate_token_with_ip_check(self, mock_service_class, authenticated_client):
        """Test token validation with IP restriction."""
        mock_service = MagicMock()
        mock_service.validate_token.return_value = {
            "job_id": "test-job-123",
            "api_key_prefix": "tfk_test",
            "allowed_ips": ["192.168.1.100"],
            "max_uses": None,
        }
        mock_service_class.return_value = mock_service

        # Client IP doesn't match allowed IPs
        response = authenticated_client.get(
            "/api/v1/streaming/validate-token",
            headers={
                "X-Stream-Token": "valid.token.here",
                "X-Forwarded-For": "10.0.0.1",
            },
        )

        assert response.status_code == 403
        assert "IP address not allowed" in response.json()["detail"]


@pytest.mark.unit
class TestRevokeStreamingToken:
    """Test POST /streaming/revoke endpoint."""

    @patch("app.services.streaming_tokens.StreamingTokenService")
    def test_revoke_token_success(self, mock_service_class, authenticated_client):
        """Test successful token revocation."""
        mock_service = MagicMock()
        mock_service.revoke_token.return_value = True
        mock_service_class.return_value = mock_service

        response = authenticated_client.post(
            "/api/v1/streaming/revoke",
            json={"token": "token.to.revoke"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["revoked"] is True

    @patch("app.services.streaming_tokens.StreamingTokenService")
    def test_revoke_token_already_revoked(self, mock_service_class, authenticated_client):
        """Test revoking already revoked token."""
        mock_service = MagicMock()
        mock_service.revoke_token.return_value = False
        mock_service_class.return_value = mock_service

        response = authenticated_client.post(
            "/api/v1/streaming/revoke",
            json={"token": "already.revoked.token"},
        )

        assert response.status_code == 400
        assert "already revoked" in response.json()["detail"]


@pytest.mark.unit
class TestGetStreamingURL:
    """Test GET /streaming/url/{job_id}/{resolution} endpoint."""

    def test_get_streaming_url_success(self, authenticated_client, sample_job):
        """Test successful streaming URL generation."""
        response = authenticated_client.get(
            f"/api/v1/streaming/url/{sample_job.id}/1080p",
            params={"expires_in_seconds": 3600},
        )

        assert response.status_code == 200
        data = response.json()
        assert "streaming_url" in data
        assert "token" in data
        assert data["job_id"] == sample_job.id
        assert data["resolution"] == "1080p"

    def test_get_streaming_url_invalid_resolution(self, authenticated_client, sample_job):
        """Test streaming URL for non-existent resolution."""
        response = authenticated_client.get(
            f"/api/v1/streaming/url/{sample_job.id}/4k",
            params={"expires_in_seconds": 3600},
        )

        assert response.status_code == 404
        assert "Resolution not found" in response.json()["detail"]

    def test_get_streaming_url_job_not_found(self, authenticated_client):
        """Test streaming URL for non-existent job."""
        response = authenticated_client.get(
            "/api/v1/streaming/url/non-existent/1080p",
            params={"expires_in_seconds": 3600},
        )

        assert response.status_code == 404


@pytest.mark.unit
class TestStreamingTokenService:
    """Test StreamingTokenService class."""

    @patch("redis.Redis")
    def test_generate_token_basic(self, mock_redis):
        """Test basic token generation."""
        from app.services.streaming_tokens import StreamingTokenService

        service = StreamingTokenService(
            secret_key="test_secret",
            redis_client=None,
        )

        token = service.generate_token(
            job_id="test-job",
            api_key_prefix="tfk_test",
            expires_in_seconds=3600,
        )

        assert isinstance(token, str)
        assert len(token) > 20

        # Decode and verify
        payload = jwt.decode(token, "test_secret", algorithms=["HS256"])
        assert payload["job_id"] == "test-job"
        assert payload["api_key_prefix"] == "tfk_test"
        assert payload["type"] == "streaming"

    @patch("redis.Redis")
    def test_validate_token_basic(self, mock_redis):
        """Test basic token validation."""
        from app.services.streaming_tokens import StreamingTokenService

        service = StreamingTokenService(
            secret_key="test_secret",
            redis_client=None,
        )

        token = service.generate_token(
            job_id="test-job",
            api_key_prefix="tfk_test",
            expires_in_seconds=3600,
        )

        payload = service.validate_token(token)
        assert payload["job_id"] == "test-job"
        assert payload["api_key_prefix"] == "tfk_test"

    @patch("redis.Redis")
    def test_validate_token_expired(self, mock_redis):
        """Test validation of expired token."""
        from app.services.streaming_tokens import StreamingTokenService

        service = StreamingTokenService(
            secret_key="test_secret",
            redis_client=None,
        )

        # Generate token that expires immediately
        token = service.generate_token(
            job_id="test-job",
            api_key_prefix="tfk_test",
            expires_in_seconds=-1,  # Already expired
        )

        with pytest.raises(jwt.ExpiredSignatureError):
            service.validate_token(token)

    def test_revoke_token_with_redis(self):
        """Test token revocation with Redis."""
        from app.services.streaming_tokens import StreamingTokenService

        mock_redis = MagicMock()
        service = StreamingTokenService(
            secret_key="test_secret",
            redis_client=mock_redis,
        )

        token = service.generate_token(
            job_id="test-job",
            api_key_prefix="tfk_test",
            expires_in_seconds=3600,
        )

        result = service.revoke_token(token)
        assert result is True
        assert mock_redis.setex.called

    def test_validate_revoked_token(self):
        """Test that revoked tokens fail validation."""
        from app.services.streaming_tokens import StreamingTokenService

        mock_redis = MagicMock()
        mock_redis.exists.return_value = True  # Token is blacklisted

        service = StreamingTokenService(
            secret_key="test_secret",
            redis_client=mock_redis,
        )

        token = service.generate_token(
            job_id="test-job",
            api_key_prefix="tfk_test",
            expires_in_seconds=3600,
        )

        with pytest.raises(Exception, match="revoked"):
            service.validate_token(token)

    def test_token_usage_tracking(self):
        """Test token usage tracking with max_uses."""
        from app.services.streaming_tokens import StreamingTokenService

        mock_redis = MagicMock()
        mock_redis.get.return_value = "5"  # Used 5 times

        service = StreamingTokenService(
            secret_key="test_secret",
            redis_client=mock_redis,
        )

        token = service.generate_token(
            job_id="test-job",
            api_key_prefix="tfk_test",
            expires_in_seconds=3600,
            max_uses=10,
        )

        # Should be valid (5 < 10)
        payload = service.validate_token(token)
        assert payload is not None

        # Simulate max uses reached
        mock_redis.get.return_value = "10"
        with pytest.raises(Exception, match="exceeded"):
            service.validate_token(token)
