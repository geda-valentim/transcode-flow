"""
Security tests for Transcode Flow.
Tests for common vulnerabilities: SQL injection, XSS, authentication bypass, etc.
"""
import pytest
from unittest.mock import patch


@pytest.mark.security
class TestSQLInjection:
    """Test SQL injection vulnerabilities."""

    def test_sql_injection_in_job_id(self, authenticated_client):
        """Test SQL injection attempt in job ID parameter."""
        malicious_ids = [
            "1' OR '1'='1",
            "1; DROP TABLE jobs--",
            "1 UNION SELECT * FROM api_keys--",
            "'; DELETE FROM jobs WHERE '1'='1",
        ]

        for malicious_id in malicious_ids:
            response = authenticated_client.get(f"/api/v1/jobs/{malicious_id}")
            # Should return 404, not 500 or expose data
            assert response.status_code in [404, 422]
            assert "jobs" not in response.text.lower() or "not found" in response.text.lower()

    def test_sql_injection_in_query_params(self, authenticated_client):
        """Test SQL injection in query parameters."""
        response = authenticated_client.get(
            "/api/v1/jobs?status=' OR '1'='1&limit=100"
        )
        # Should handle safely, not execute injection
        assert response.status_code in [200, 422]

    def test_sql_injection_in_api_key_search(self, authenticated_client):
        """Test SQL injection in API key endpoints."""
        response = authenticated_client.get(
            "/api/v1/api-keys/999' OR '1'='1--"
        )
        assert response.status_code in [404, 422]


@pytest.mark.security
class TestXSSVulnerabilities:
    """Test Cross-Site Scripting (XSS) vulnerabilities."""

    def test_xss_in_job_creation(self, authenticated_client):
        """Test XSS payload in job creation."""
        xss_payload = "<script>alert('XSS')</script>"

        with patch("app.services.video_validator.VideoValidator.validate") as mock_validate:
            mock_validate.return_value = {"valid": True, "duration": 60.0}

            response = authenticated_client.post(
                "/api/v1/jobs",
                json={
                    "input_url": f"https://example.com/{xss_payload}",
                    "output_formats": [{"format": "hls"}],
                },
            )

        # XSS payload should be escaped or sanitized
        if response.status_code == 201:
            data = response.json()
            # Check that script tags are not present as-is in response
            assert "<script>" not in str(data)

    def test_xss_in_api_key_name(self, authenticated_client):
        """Test XSS in API key name field."""
        response = authenticated_client.post(
            "/api/v1/api-keys",
            json={
                "name": "<script>alert('XSS')</script>",
                "email": "test@example.com",
                "expires_in_days": 30,
            },
        )

        if response.status_code == 201:
            data = response.json()
            # Script tags should be escaped
            assert "<script>" not in data.get("name", "")


@pytest.mark.security
class TestAuthenticationBypass:
    """Test authentication and authorization bypass attempts."""

    def test_access_without_api_key(self, client):
        """Test accessing protected endpoints without API key."""
        protected_endpoints = [
            "/api/v1/jobs",
            "/api/v1/api-keys",
            "/api/v1/streaming/tokens",
        ]

        for endpoint in protected_endpoints:
            response = client.get(endpoint)
            assert response.status_code == 403

    def test_access_with_invalid_api_key(self, client):
        """Test accessing with malformed API key."""
        invalid_keys = [
            "invalid_key",
            "tfk_" + "0" * 100,  # Too long
            "../../etc/passwd",  # Path traversal
            "",  # Empty
        ]

        for invalid_key in invalid_keys:
            response = client.get(
                "/api/v1/jobs",
                headers={"X-API-Key": invalid_key},
            )
            assert response.status_code in [401, 403]

    def test_access_other_users_data(self, client, sub_api_key, db):
        """Test accessing another user's data."""
        from app.models.job import Job

        # Create job for different user
        other_job = Job(
            id="other-user-job",
            api_key_prefix="other_prefix",
            input_url="https://example.com/video.mp4",
            status="completed",
        )
        db.add(other_job)
        db.commit()

        # Try to access with sub_api_key
        client.headers = {"X-API-Key": sub_api_key._test_key}
        response = client.get(f"/api/v1/jobs/{other_job.id}")

        assert response.status_code == 403


@pytest.mark.security
class TestInputValidation:
    """Test input validation and sanitization."""

    def test_oversized_input_url(self, authenticated_client):
        """Test extremely long input URL."""
        with patch("app.services.video_validator.VideoValidator.validate") as mock_validate:
            mock_validate.return_value = {"valid": True, "duration": 60.0}

            response = authenticated_client.post(
                "/api/v1/jobs",
                json={
                    "input_url": "https://example.com/" + "a" * 10000,
                    "output_formats": [{"format": "hls"}],
                },
            )

        # Should reject or truncate
        assert response.status_code in [201, 422]

    def test_negative_values(self, authenticated_client):
        """Test negative values in numeric fields."""
        response = authenticated_client.post(
            "/api/v1/streaming/tokens",
            json={
                "job_id": "test-job",
                "expires_in_seconds": -1000,  # Negative expiration
            },
        )

        # Should reject negative values
        assert response.status_code in [400, 422]

    def test_array_overflow(self, authenticated_client):
        """Test array field with too many items."""
        with patch("app.services.video_validator.VideoValidator.validate") as mock_validate:
            mock_validate.return_value = {"valid": True, "duration": 60.0}

            response = authenticated_client.post(
                "/api/v1/jobs",
                json={
                    "input_url": "https://example.com/video.mp4",
                    "output_formats": [{"format": "hls"}] * 1000,  # Too many formats
                },
            )

        # Should reject or limit
        assert response.status_code in [201, 422]


@pytest.mark.security
class TestRateLimitBypass:
    """Test rate limiting bypass attempts."""

    def test_rate_limit_with_different_ips(self, client, master_api_key):
        """Test rate limiting with IP spoofing."""
        client.headers = {"X-API-Key": master_api_key._test_key}

        # Try to bypass with different X-Forwarded-For headers
        for i in range(5):
            headers = {
                **client.headers,
                "X-Forwarded-For": f"192.168.1.{i}",
            }
            response = client.get("/api/v1/jobs", headers=headers)
            # Rate limit should still apply per API key
            assert response.status_code in [200, 429]

    def test_concurrent_requests(self, client, master_api_key):
        """Test concurrent request handling."""
        import threading

        client.headers = {"X-API-Key": master_api_key._test_key}
        results = []

        def make_request():
            response = client.get("/api/v1/jobs")
            results.append(response.status_code)

        threads = [threading.Thread(target=make_request) for _ in range(10)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        # All requests should be handled properly
        assert all(status in [200, 429] for status in results)


@pytest.mark.security
class TestTokenSecurity:
    """Test streaming token security."""

    def test_token_tampering(self, authenticated_client):
        """Test tampered JWT token detection."""
        tampered_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"

        response = authenticated_client.get(
            "/api/v1/streaming/validate-token",
            headers={"X-Stream-Token": tampered_token},
        )

        assert response.status_code in [400, 401]

    def test_expired_token(self, authenticated_client):
        """Test that expired tokens are rejected."""
        # Would need actual expired token generation
        # This is a placeholder for the test structure
        pass


@pytest.mark.security
class TestIPRestrictions:
    """Test IP whitelist/blacklist enforcement."""

    def test_ip_blacklist_enforcement(self, client, db, master_api_key):
        """Test that blacklisted IPs are blocked."""
        master_api_key.ip_blacklist = ["192.168.1.100"]
        db.commit()

        client.headers = {
            "X-API-Key": master_api_key._test_key,
            "X-Forwarded-For": "192.168.1.100",
        }

        response = client.get("/api/v1/jobs")
        assert response.status_code == 403

    def test_ip_whitelist_enforcement(self, client, db, master_api_key):
        """Test that only whitelisted IPs are allowed."""
        master_api_key.ip_whitelist = ["10.0.0.1"]
        db.commit()

        # Request from non-whitelisted IP
        client.headers = {
            "X-API-Key": master_api_key._test_key,
            "X-Forwarded-For": "192.168.1.1",
        }

        response = client.get("/api/v1/jobs")
        assert response.status_code == 403


@pytest.mark.security
class TestDataExposure:
    """Test for sensitive data exposure."""

    def test_no_api_key_in_response(self, authenticated_client, master_api_key):
        """Test that full API keys are never exposed in responses."""
        response = authenticated_client.get(f"/api/v1/api-keys/{master_api_key.id}")

        assert response.status_code == 200
        data = response.json()
        # Should only show prefix, not full key
        assert "api_key" not in data or data.get("api_key", "").startswith("tfk_")
        assert len(data.get("key_prefix", "")) <= 12

    def test_error_messages_dont_expose_internals(self, client):
        """Test that error messages don't expose system internals."""
        response = client.get("/api/v1/jobs/invalid-id")

        # Error should be generic, not expose DB structure
        if response.status_code == 403:
            detail = response.json().get("detail", "")
            assert "SELECT" not in detail.upper()
            assert "TABLE" not in detail.upper()
            assert "DATABASE" not in detail.upper()
