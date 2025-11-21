"""
Unit tests for Job Management endpoints.
Tests endpoints from app/api/v1/endpoints/jobs.py
"""
import pytest
from datetime import datetime, timezone
from unittest.mock import Mock, patch, MagicMock

from app.models.job import Job


@pytest.mark.unit
class TestCreateJob:
    """Test POST /jobs endpoint."""

    def test_create_job_success(self, authenticated_client, sample_job_data):
        """Test successful job creation."""
        with patch("app.services.video_validator.VideoValidator.validate") as mock_validate:
            mock_validate.return_value = {
                "valid": True,
                "duration": 120.5,
                "size_bytes": 10485760,
                "codec": "h264",
            }

            response = authenticated_client.post("/api/v1/jobs", json=sample_job_data)

            assert response.status_code == 201
            data = response.json()
            assert "id" in data
            assert data["status"] == "pending"
            assert data["input_url"] == sample_job_data["input_url"]

    def test_create_job_invalid_url(self, authenticated_client):
        """Test job creation with invalid URL."""
        response = authenticated_client.post(
            "/api/v1/jobs",
            json={
                "input_url": "not-a-valid-url",
                "output_formats": [{"format": "hls"}],
            },
        )

        assert response.status_code == 422  # Validation error

    def test_create_job_quota_exceeded(self, authenticated_client, master_api_key, db):
        """Test job creation when monthly quota is exceeded."""
        master_api_key.jobs_used_monthly = master_api_key.jobs_quota_monthly
        db.commit()

        response = authenticated_client.post(
            "/api/v1/jobs",
            json={
                "input_url": "https://example.com/video.mp4",
                "output_formats": [{"format": "hls"}],
            },
        )

        assert response.status_code == 429
        assert "quota" in response.json()["detail"].lower()

    def test_create_job_without_authentication(self, client):
        """Test job creation without API key."""
        response = client.post(
            "/api/v1/jobs",
            json={
                "input_url": "https://example.com/video.mp4",
                "output_formats": [{"format": "hls"}],
            },
        )

        assert response.status_code == 403


@pytest.mark.unit
class TestGetJob:
    """Test GET /jobs/{job_id} endpoint."""

    def test_get_job_success(self, authenticated_client, sample_job, master_api_key):
        """Test retrieving own job."""
        response = authenticated_client.get(f"/api/v1/jobs/{sample_job.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == sample_job.id
        assert data["status"] == sample_job.status

    def test_get_job_not_found(self, authenticated_client):
        """Test retrieving non-existent job."""
        response = authenticated_client.get("/api/v1/jobs/non-existent-job")

        assert response.status_code == 404

    def test_get_job_wrong_owner(self, client, sample_job, sub_api_key, db):
        """Test retrieving job owned by different API key."""
        sample_job.api_key_prefix = "different_prefix"
        db.commit()

        client.headers = {"X-API-Key": sub_api_key._test_key}
        response = client.get(f"/api/v1/jobs/{sample_job.id}")

        assert response.status_code == 403


@pytest.mark.unit
class TestListJobs:
    """Test GET /jobs endpoint."""

    def test_list_jobs_success(self, authenticated_client, sample_job):
        """Test listing jobs."""
        response = authenticated_client.get("/api/v1/jobs")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        assert any(job["id"] == sample_job.id for job in data)

    def test_list_jobs_with_status_filter(self, authenticated_client, sample_job, db):
        """Test listing jobs with status filter."""
        # Create jobs with different statuses
        pending_job = Job(
            id="pending-job",
            api_key_prefix=sample_job.api_key_prefix,
            input_url="https://example.com/pending.mp4",
            status="pending",
        )
        db.add(pending_job)
        db.commit()

        response = authenticated_client.get("/api/v1/jobs?status=completed")

        assert response.status_code == 200
        data = response.json()
        assert all(job["status"] == "completed" for job in data)

    def test_list_jobs_with_pagination(self, authenticated_client, db, master_api_key):
        """Test job listing with pagination."""
        # Create multiple jobs
        for i in range(15):
            job = Job(
                id=f"job-{i}",
                api_key_prefix=master_api_key.key_prefix,
                input_url=f"https://example.com/video{i}.mp4",
                status="pending",
            )
            db.add(job)
        db.commit()

        response = authenticated_client.get("/api/v1/jobs?limit=10&offset=0")

        assert response.status_code == 200
        data = response.json()
        assert len(data) <= 10

    def test_list_jobs_only_shows_own(self, client, sub_api_key, db):
        """Test that users only see their own jobs."""
        # Create job for different API key
        other_job = Job(
            id="other-job",
            api_key_prefix="different_prefix",
            input_url="https://example.com/other.mp4",
            status="pending",
        )
        db.add(other_job)
        db.commit()

        client.headers = {"X-API-Key": sub_api_key._test_key}
        response = client.get("/api/v1/jobs")

        assert response.status_code == 200
        data = response.json()
        assert not any(job["id"] == "other-job" for job in data)


@pytest.mark.unit
class TestDeleteJob:
    """Test DELETE /jobs/{job_id} endpoint."""

    def test_delete_job_success(self, authenticated_client, sample_job, db):
        """Test successful job deletion."""
        response = authenticated_client.delete(f"/api/v1/jobs/{sample_job.id}")

        assert response.status_code == 204

        # Verify job is deleted
        deleted_job = db.query(Job).filter(Job.id == sample_job.id).first()
        assert deleted_job is None

    def test_delete_job_not_found(self, authenticated_client):
        """Test deleting non-existent job."""
        response = authenticated_client.delete("/api/v1/jobs/non-existent")

        assert response.status_code == 404

    def test_delete_job_wrong_owner(self, client, sample_job, sub_api_key, db):
        """Test deleting job owned by different API key."""
        sample_job.api_key_prefix = "different_prefix"
        db.commit()

        client.headers = {"X-API-Key": sub_api_key._test_key}
        response = client.delete(f"/api/v1/jobs/{sample_job.id}")

        assert response.status_code == 403


@pytest.mark.unit
class TestCancelJob:
    """Test POST /jobs/{job_id}/cancel endpoint."""

    def test_cancel_job_success(self, authenticated_client, db, master_api_key):
        """Test canceling a processing job."""
        job = Job(
            id="processing-job",
            api_key_prefix=master_api_key.key_prefix,
            input_url="https://example.com/video.mp4",
            status="processing",
        )
        db.add(job)
        db.commit()

        response = authenticated_client.post(f"/api/v1/jobs/{job.id}/cancel")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "cancelled"

    def test_cancel_completed_job(self, authenticated_client, sample_job):
        """Test that completed jobs cannot be cancelled."""
        response = authenticated_client.post(f"/api/v1/jobs/{sample_job.id}/cancel")

        assert response.status_code == 400
        assert "cannot be cancelled" in response.json()["detail"].lower()


@pytest.mark.unit
class TestRetryJob:
    """Test POST /jobs/{job_id}/retry endpoint."""

    def test_retry_failed_job(self, authenticated_client, db, master_api_key):
        """Test retrying a failed job."""
        job = Job(
            id="failed-job",
            api_key_prefix=master_api_key.key_prefix,
            input_url="https://example.com/video.mp4",
            status="failed",
            error_message="Something went wrong",
        )
        db.add(job)
        db.commit()

        response = authenticated_client.post(f"/api/v1/jobs/{job.id}/retry")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "pending"
        assert data["error_message"] is None

    def test_retry_successful_job(self, authenticated_client, sample_job):
        """Test that successful jobs cannot be retried."""
        response = authenticated_client.post(f"/api/v1/jobs/{sample_job.id}/retry")

        assert response.status_code == 400


@pytest.mark.unit
class TestJobModel:
    """Test Job model methods."""

    def test_job_model_creation(self, db):
        """Test creating a Job model instance."""
        job = Job(
            id="test-model-job",
            api_key_prefix="tfk_test",
            input_url="https://example.com/video.mp4",
            status="pending",
        )
        db.add(job)
        db.commit()
        db.refresh(job)

        assert job.id == "test-model-job"
        assert job.status == "pending"
        assert job.created_at is not None

    def test_job_status_transitions(self, db):
        """Test job status transitions."""
        job = Job(
            id="status-test-job",
            api_key_prefix="tfk_test",
            input_url="https://example.com/video.mp4",
            status="pending",
        )
        db.add(job)
        db.commit()

        # Transition to processing
        job.status = "processing"
        job.started_at = datetime.now(timezone.utc)
        db.commit()
        assert job.status == "processing"

        # Transition to completed
        job.status = "completed"
        job.completed_at = datetime.now(timezone.utc)
        db.commit()
        assert job.status == "completed"

    def test_job_output_files_storage(self, db):
        """Test storing output files as JSONB."""
        job = Job(
            id="output-test-job",
            api_key_prefix="tfk_test",
            input_url="https://example.com/video.mp4",
            status="completed",
            output_files={
                "hls": {
                    "1080p": {"manifest": "path/to/manifest.m3u8"},
                    "720p": {"manifest": "path/to/720p.m3u8"},
                },
                "mp4": {"1080p": "path/to/video.mp4"},
            },
        )
        db.add(job)
        db.commit()
        db.refresh(job)

        assert "hls" in job.output_files
        assert "1080p" in job.output_files["hls"]
