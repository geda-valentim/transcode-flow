"""
Locust load testing file for Transcode Flow API.
Run with: locust -f tests/load/locustfile.py --host=http://localhost:18000
"""
from locust import HttpUser, task, between, events
import random
import json
import hashlib


class TranscodeFlowUser(HttpUser):
    """Simulated user for load testing Transcode Flow API."""

    wait_time = between(1, 3)  # Wait 1-3 seconds between tasks

    def on_start(self):
        """Setup: Create API key for this user."""
        # In production, use a pre-created master API key
        self.api_key = "tfk_load_test_master_key_12345678"
        self.headers = {"X-API-Key": self.api_key}
        self.job_ids = []

    @task(5)
    def list_jobs(self):
        """List jobs - high frequency task."""
        with self.client.get(
            "/api/v1/jobs",
            headers=self.headers,
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Failed with status {response.status_code}")

    @task(10)
    def get_job_status(self):
        """Get specific job status - very high frequency."""
        if not self.job_ids:
            return

        job_id = random.choice(self.job_ids)
        with self.client.get(
            f"/api/v1/jobs/{job_id}",
            headers=self.headers,
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                response.success()
            elif response.status_code == 404:
                # Job not found, remove from list
                self.job_ids.remove(job_id)
                response.success()
            else:
                response.failure(f"Failed with status {response.status_code}")

    @task(2)
    def create_job(self):
        """Create new transcoding job - medium frequency."""
        job_data = {
            "input_url": f"https://example.com/video_{random.randint(1, 1000)}.mp4",
            "output_formats": [
                {
                    "format": "hls",
                    "video_codec": "h264",
                    "audio_codec": "aac",
                    "resolutions": random.choice([
                        ["1080p"],
                        ["720p", "480p"],
                        ["1080p", "720p", "480p"],
                    ]),
                }
            ],
            "extract_audio": random.choice([True, False]),
            "webhook_url": "https://example.com/webhook",
        }

        with self.client.post(
            "/api/v1/jobs",
            headers=self.headers,
            json=job_data,
            catch_response=True,
        ) as response:
            if response.status_code == 201:
                job_id = response.json().get("id")
                if job_id:
                    self.job_ids.append(job_id)
                response.success()
            elif response.status_code == 429:
                # Rate limit hit - expected behavior
                response.success()
            else:
                response.failure(f"Failed with status {response.status_code}")

    @task(3)
    def generate_streaming_token(self):
        """Generate streaming token - medium frequency."""
        if not self.job_ids:
            return

        job_id = random.choice(self.job_ids)
        with self.client.post(
            "/api/v1/streaming/tokens",
            headers=self.headers,
            json={
                "job_id": job_id,
                "expires_in_seconds": 3600,
            },
            catch_response=True,
        ) as response:
            if response.status_code in [200, 400, 403]:
                # 400/403 expected if job not completed
                response.success()
            else:
                response.failure(f"Failed with status {response.status_code}")

    @task(1)
    def list_api_keys(self):
        """List API keys - low frequency."""
        with self.client.get(
            "/api/v1/api-keys",
            headers=self.headers,
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Failed with status {response.status_code}")

    @task(1)
    def get_api_key_analytics(self):
        """Get API key analytics - low frequency."""
        with self.client.get(
            "/api/v1/api-keys/1/analytics",
            headers=self.headers,
            catch_response=True,
        ) as response:
            if response.status_code in [200, 404]:
                response.success()
            else:
                response.failure(f"Failed with status {response.status_code}")

    @task(1)
    def health_check(self):
        """Health check endpoint - low frequency."""
        with self.client.get("/health", catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Failed with status {response.status_code}")


class HeavyLoadUser(HttpUser):
    """User simulating heavy API usage for stress testing."""

    wait_time = between(0.1, 0.5)  # Faster requests
    weight = 1  # Lower weight means fewer of these users

    def on_start(self):
        self.api_key = "tfk_load_test_heavy_key_87654321"
        self.headers = {"X-API-Key": self.api_key}

    @task
    def rapid_fire_job_listing(self):
        """Rapidly list jobs to test caching and DB performance."""
        self.client.get("/api/v1/jobs", headers=self.headers)

    @task
    def create_multiple_jobs(self):
        """Create multiple jobs in quick succession."""
        for _ in range(3):
            job_data = {
                "input_url": f"https://example.com/heavy_{random.randint(1, 10000)}.mp4",
                "output_formats": [{"format": "hls", "resolutions": ["720p"]}],
            }
            self.client.post("/api/v1/jobs", headers=self.headers, json=job_data)


@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """Execute before load test starts."""
    print("=" * 60)
    print("  TRANSCODE FLOW LOAD TEST STARTING")
    print("=" * 60)
    print(f"  Host: {environment.host}")
    print(f"  Users: {environment.runner.user_count if hasattr(environment.runner, 'user_count') else 'N/A'}")
    print("=" * 60)


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Execute after load test completes."""
    print("\n" + "=" * 60)
    print("  TRANSCODE FLOW LOAD TEST COMPLETED")
    print("=" * 60)
    stats = environment.stats
    print(f"  Total requests: {stats.total.num_requests}")
    print(f"  Total failures: {stats.total.num_failures}")
    print(f"  Average response time: {stats.total.avg_response_time:.2f}ms")
    print(f"  RPS: {stats.total.total_rps:.2f}")
    print("=" * 60)
