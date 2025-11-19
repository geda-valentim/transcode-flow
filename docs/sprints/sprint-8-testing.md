# Sprint 8: Testing & Performance Optimization (Week 9)

**Goal:** Comprehensive testing and performance optimization

**Duration:** 1 week
**Team Size:** 2-3 developers

---

## Tasks

- [ ] Write unit tests for all API endpoints
- [ ] Write unit tests for DAG tasks
- [ ] Implement integration tests for video processing pipeline
- [ ] Add load testing with Locust or k6
- [ ] Implement end-to-end tests
- [ ] Add video quality validation tests
- [ ] Write tests for error handling and edge cases
- [ ] Implement database migration tests
- [ ] Add security tests (SQL injection, XSS, etc.)
- [ ] Optimize FFmpeg commands for performance
- [ ] Optimize database queries (add missing indexes)
- [ ] Implement connection pooling optimizations
- [ ] Add caching layer (Redis) for frequently accessed data
- [ ] Optimize MinIO upload/download performance
- [ ] Profile and optimize Airflow DAG performance
- [ ] Implement parallel task execution where possible
- [ ] Add performance regression tests
- [ ] Create performance benchmarking scripts
- [ ] Optimize Docker container sizes
- [ ] Implement test coverage reporting (minimum 80%)

---

## Deliverables

- ✅ Complete test suite (unit, integration, e2e)
- ✅ Test coverage > 80%
- ✅ Load testing results documented
- ✅ Performance optimizations implemented
- ✅ Benchmark suite created

---

## Acceptance Criteria

- [ ] Test coverage ≥ 80% on all modules
- [ ] All tests passing in CI/CD
- [ ] Load test handles 100 concurrent requests
- [ ] API response time p95 < 200ms
- [ ] Video processing throughput ≥ 100GB/day
- [ ] No memory leaks detected
- [ ] Database query time p95 < 50ms
- [ ] All security tests passing

---

## Technical Details

### Unit Tests

```python
# tests/test_api_endpoints.py

import pytest
from fastapi.testclient import TestClient
from main import app
from models import Job, ApiKey
from datetime import datetime

client = TestClient(app)

# ============================================
# Fixtures
# ============================================

@pytest.fixture
def test_db():
    """Create test database"""
    # Setup
    create_test_database()
    yield db_session
    # Teardown
    drop_test_database()

@pytest.fixture
def test_api_key(test_db):
    """Create test API key"""
    raw_key, key_hash = ApiKey.generate_key()

    api_key = ApiKey(
        key_hash=key_hash,
        key_prefix=raw_key[:8],
        name="Test Key",
        scopes=["read", "write"],
        is_active=True
    )

    test_db.add(api_key)
    test_db.commit()

    return raw_key

@pytest.fixture
def test_job(test_db, test_api_key):
    """Create test job"""
    job = Job(
        api_key=hashlib.sha256(test_api_key.encode()).hexdigest(),
        status='queued',
        priority=5,
        original_filename='test_video.mp4',
        source_size_bytes=1000000
    )

    test_db.add(job)
    test_db.commit()

    return job

# ============================================
# Upload Endpoint Tests
# ============================================

def test_upload_video_success(test_api_key):
    """Test successful video upload"""

    with open('tests/fixtures/test_video.mp4', 'rb') as f:
        response = client.post(
            "/api/upload",
            files={"file": ("test.mp4", f, "video/mp4")},
            headers={"X-API-Key": test_api_key}
        )

    assert response.status_code == 200
    data = response.json()

    assert "job_id" in data
    assert data["status"] == "queued"
    assert "video.mp4" in data["filename"]

def test_upload_video_invalid_format(test_api_key):
    """Test upload with invalid video format"""

    with open('tests/fixtures/test_image.jpg', 'rb') as f:
        response = client.post(
            "/api/upload",
            files={"file": ("test.jpg", f, "image/jpeg")},
            headers={"X-API-Key": test_api_key}
        )

    assert response.status_code == 400
    assert "Invalid video format" in response.json()["detail"]

def test_upload_video_no_api_key():
    """Test upload without API key"""

    with open('tests/fixtures/test_video.mp4', 'rb') as f:
        response = client.post(
            "/api/upload",
            files={"file": ("test.mp4", f, "video/mp4")}
        )

    assert response.status_code == 403

def test_upload_video_invalid_api_key():
    """Test upload with invalid API key"""

    with open('tests/fixtures/test_video.mp4', 'rb') as f:
        response = client.post(
            "/api/upload",
            files={"file": ("test.mp4", f, "video/mp4")},
            headers={"X-API-Key": "invalid_key"}
        )

    assert response.status_code == 401

def test_upload_video_exceeds_quota(test_api_key, test_db):
    """Test upload that exceeds storage quota"""

    # Set quota to 1MB
    api_key_obj = test_db.query(ApiKey).filter(
        ApiKey.key_hash == hashlib.sha256(test_api_key.encode()).hexdigest()
    ).first()

    api_key_obj.storage_quota_bytes = 1024 * 1024  # 1MB
    test_db.commit()

    # Try to upload 10MB file
    with open('tests/fixtures/large_video.mp4', 'rb') as f:
        response = client.post(
            "/api/upload",
            files={"file": ("large.mp4", f, "video/mp4")},
            headers={"X-API-Key": test_api_key}
        )

    assert response.status_code == 413
    assert "quota exceeded" in response.json()["detail"].lower()

# ============================================
# Job Status Endpoint Tests
# ============================================

def test_get_job_status_success(test_api_key, test_job):
    """Test getting job status"""

    response = client.get(
        f"/api/jobs/{test_job.id}",
        headers={"X-API-Key": test_api_key}
    )

    assert response.status_code == 200
    data = response.json()

    assert data["job_id"] == str(test_job.id)
    assert data["status"] == "queued"
    assert "progress" in data

def test_get_job_status_not_found(test_api_key):
    """Test getting non-existent job"""

    response = client.get(
        "/api/jobs/00000000-0000-0000-0000-000000000000",
        headers={"X-API-Key": test_api_key}
    )

    assert response.status_code == 404

def test_get_job_status_wrong_api_key(test_job):
    """Test accessing job with wrong API key"""

    # Create another API key
    other_key, _ = ApiKey.generate_key()

    response = client.get(
        f"/api/jobs/{test_job.id}",
        headers={"X-API-Key": other_key}
    )

    assert response.status_code == 403

# ============================================
# List Jobs Endpoint Tests
# ============================================

def test_list_jobs(test_api_key, test_db):
    """Test listing jobs"""

    # Create multiple jobs
    for i in range(10):
        job = Job(
            api_key=hashlib.sha256(test_api_key.encode()).hexdigest(),
            status='completed',
            priority=5,
            original_filename=f'video_{i}.mp4'
        )
        test_db.add(job)

    test_db.commit()

    response = client.get(
        "/api/jobs",
        headers={"X-API-Key": test_api_key}
    )

    assert response.status_code == 200
    data = response.json()

    assert data["total"] == 10
    assert len(data["jobs"]) == 10

def test_list_jobs_pagination(test_api_key, test_db):
    """Test job listing pagination"""

    # Create 25 jobs
    for i in range(25):
        job = Job(
            api_key=hashlib.sha256(test_api_key.encode()).hexdigest(),
            status='completed',
            priority=5
        )
        test_db.add(job)

    test_db.commit()

    # Get page 1
    response = client.get(
        "/api/jobs?page=1&per_page=10",
        headers={"X-API-Key": test_api_key}
    )

    assert response.status_code == 200
    data = response.json()

    assert data["page"] == 1
    assert len(data["jobs"]) == 10
    assert data["total"] == 25
    assert data["total_pages"] == 3

def test_list_jobs_filtering(test_api_key, test_db):
    """Test job filtering by status"""

    # Create jobs with different statuses
    for status in ['queued', 'processing', 'completed', 'failed']:
        for i in range(3):
            job = Job(
                api_key=hashlib.sha256(test_api_key.encode()).hexdigest(),
                status=status,
                priority=5
            )
            test_db.add(job)

    test_db.commit()

    # Filter by completed
    response = client.get(
        "/api/jobs?status=completed",
        headers={"X-API-Key": test_api_key}
    )

    assert response.status_code == 200
    data = response.json()

    assert data["total"] == 3
    for job in data["jobs"]:
        assert job["status"] == "completed"

# ============================================
# Cancel Job Tests
# ============================================

def test_cancel_job(test_api_key, test_job):
    """Test canceling a queued job"""

    response = client.post(
        f"/api/jobs/{test_job.id}/cancel",
        headers={"X-API-Key": test_api_key}
    )

    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"

def test_cancel_completed_job(test_api_key, test_job, test_db):
    """Test cannot cancel completed job"""

    test_job.status = 'completed'
    test_db.commit()

    response = client.post(
        f"/api/jobs/{test_job.id}/cancel",
        headers={"X-API-Key": test_api_key}
    )

    assert response.status_code == 400

# ============================================
# Delete Job Tests
# ============================================

def test_delete_job(test_api_key, test_job):
    """Test deleting a job"""

    response = client.delete(
        f"/api/jobs/{test_job.id}",
        headers={"X-API-Key": test_api_key}
    )

    assert response.status_code == 200
    assert response.json()["deleted"] == True

# ============================================
# Statistics Endpoint Tests
# ============================================

def test_get_statistics(test_api_key, test_db):
    """Test statistics endpoint"""

    # Create jobs with different statuses
    for status in ['completed', 'failed']:
        for i in range(5):
            job = Job(
                api_key=hashlib.sha256(test_api_key.encode()).hexdigest(),
                status=status,
                priority=5
            )
            test_db.add(job)

    test_db.commit()

    response = client.get(
        "/api/jobs/stats",
        headers={"X-API-Key": test_api_key}
    )

    assert response.status_code == 200
    data = response.json()

    assert data["total_jobs"] == 10
    assert data["status_breakdown"]["completed"] == 5
    assert data["status_breakdown"]["failed"] == 5
    assert data["success_rate"] == 50.0
```

---

### Integration Tests

```python
# tests/test_video_processing_integration.py

import pytest
import time
from pathlib import Path

def test_complete_video_processing_pipeline():
    """Test complete video processing from upload to completion"""

    # 1. Upload video
    with open('tests/fixtures/sample_video.mp4', 'rb') as f:
        upload_response = client.post(
            "/api/upload",
            files={"file": ("sample.mp4", f, "video/mp4")},
            headers={"X-API-Key": api_key}
        )

    assert upload_response.status_code == 200
    job_id = upload_response.json()["job_id"]

    # 2. Wait for processing (with timeout)
    timeout = 300  # 5 minutes
    start_time = time.time()

    while time.time() - start_time < timeout:
        status_response = client.get(
            f"/api/jobs/{job_id}",
            headers={"X-API-Key": api_key}
        )

        job_data = status_response.json()

        if job_data["status"] == "completed":
            break

        if job_data["status"] == "failed":
            pytest.fail(f"Job failed: {job_data['error']}")

        time.sleep(5)
    else:
        pytest.fail("Job did not complete within timeout")

    # 3. Verify outputs exist
    assert job_data["outputs"]["360p"]["available"]
    assert job_data["outputs"]["720p"]["available"]
    assert job_data["outputs"]["audio"]["available"]
    assert job_data["outputs"]["transcription"]["available"]

    # 4. Verify HLS segments
    assert job_data["outputs"]["hls"]["360p"]["available"]
    assert job_data["outputs"]["hls"]["720p"]["available"]
    assert job_data["outputs"]["hls"]["360p"]["segments_count"] > 0

    # 5. Download and verify 360p output
    download_url = job_data["outputs"]["360p"]["download_url"]
    download_response = client.get(
        download_url,
        headers={"X-API-Key": api_key}
    )

    assert download_response.status_code == 200
    assert len(download_response.content) > 0

    # 6. Verify compression
    assert job_data["outputs"]["360p"]["compression_ratio"] < 1.0

    # 7. Verify transcription
    transcript_response = client.get(
        job_data["outputs"]["transcription"]["formats"]["txt"],
        headers={"X-API-Key": api_key}
    )

    assert transcript_response.status_code == 200
    assert len(transcript_response.text) > 0

def test_video_processing_with_custom_thumbnail():
    """Test video processing with custom thumbnail"""

    with open('tests/fixtures/sample_video.mp4', 'rb') as video:
        with open('tests/fixtures/custom_thumb.jpg', 'rb') as thumb:
            upload_response = client.post(
                "/api/upload",
                files={
                    "file": ("sample.mp4", video, "video/mp4"),
                    "thumbnail": ("thumb.jpg", thumb, "image/jpeg")
                },
                headers={"X-API-Key": api_key}
            )

    assert upload_response.status_code == 200
    job_id = upload_response.json()["job_id"]

    # Wait for completion
    wait_for_job_completion(job_id, api_key)

    # Verify custom thumbnail exists
    # (Implementation specific to your storage structure)

def test_parallel_job_processing():
    """Test system can handle multiple jobs in parallel"""

    job_ids = []

    # Upload 10 videos
    for i in range(10):
        with open('tests/fixtures/sample_video.mp4', 'rb') as f:
            response = client.post(
                "/api/upload",
                files={"file": (f"video_{i}.mp4", f, "video/mp4")},
                headers={"X-API-Key": api_key}
            )

            assert response.status_code == 200
            job_ids.append(response.json()["job_id"])

    # Wait for all to complete
    for job_id in job_ids:
        wait_for_job_completion(job_id, api_key, timeout=600)

    # Verify all completed successfully
    for job_id in job_ids:
        response = client.get(
            f"/api/jobs/{job_id}",
            headers={"X-API-Key": api_key}
        )

        assert response.json()["status"] == "completed"
```

---

### Load Testing (Locust)

```python
# tests/load/locustfile.py

from locust import HttpUser, task, between
import random

class TranscodeFlowUser(HttpUser):
    wait_time = between(1, 5)

    def on_start(self):
        """Setup - get API key"""
        self.api_key = "YOUR_TEST_API_KEY"
        self.headers = {"X-API-Key": self.api_key}

    @task(3)
    def list_jobs(self):
        """List jobs (most common operation)"""
        self.client.get("/api/jobs", headers=self.headers)

    @task(2)
    def get_job_status(self):
        """Get specific job status"""
        # Assume we have some job IDs
        job_id = random.choice(self.existing_job_ids)
        self.client.get(f"/api/jobs/{job_id}", headers=self.headers)

    @task(1)
    def get_statistics(self):
        """Get statistics"""
        self.client.get("/api/jobs/stats", headers=self.headers)

    @task(1)
    def upload_video(self):
        """Upload video (less frequent)"""
        files = {
            'file': ('test.mp4', open('sample_video.mp4', 'rb'), 'video/mp4')
        }

        self.client.post("/api/upload", headers=self.headers, files=files)

# Run with: locust -f tests/load/locustfile.py --host=http://localhost
```

---

### Performance Optimization

#### Database Query Optimization

```python
# optimization/database.py

# BEFORE: N+1 query problem
def get_jobs_with_api_keys():
    jobs = db.query(Job).all()

    for job in jobs:
        api_key = db.query(ApiKey).filter(ApiKey.key_hash == job.api_key).first()
        # Do something with api_key

# AFTER: Eager loading with join
def get_jobs_with_api_keys_optimized():
    jobs = db.query(Job).join(ApiKey, Job.api_key == ApiKey.key_hash).all()

# Add missing indexes
CREATE INDEX idx_jobs_status_priority ON jobs(status, priority);
CREATE INDEX idx_jobs_created_at ON jobs(created_at DESC);
CREATE INDEX idx_jobs_api_key_status ON jobs(api_key, status);

# Use EXPLAIN ANALYZE to check query performance
EXPLAIN ANALYZE
SELECT * FROM jobs WHERE status = 'queued' ORDER BY priority DESC, created_at ASC;
```

#### Caching Layer

```python
# caching/redis_cache.py

import redis
import json
from functools import wraps

redis_client = redis.Redis(host='redis', port=6379, db=2)

def cache_result(key_prefix: str, ttl: int = 300):
    """Decorator to cache function results in Redis"""

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Generate cache key
            cache_key = f"{key_prefix}:{args}:{kwargs}"

            # Try to get from cache
            cached = redis_client.get(cache_key)

            if cached:
                return json.loads(cached)

            # Call function
            result = func(*args, **kwargs)

            # Store in cache
            redis_client.setex(
                cache_key,
                ttl,
                json.dumps(result, default=str)
            )

            return result

        return wrapper
    return decorator

# Usage
@cache_result(key_prefix="job_stats", ttl=60)
def get_statistics(api_key: str):
    # ... expensive query ...
    return stats
```

#### FFmpeg Optimization

```python
# optimization/ffmpeg.py

# Use hardware acceleration (if available)
def get_ffmpeg_hw_accel():
    """Detect and configure hardware acceleration"""

    # Check for NVIDIA GPU
    try:
        subprocess.run(['nvidia-smi'], check=True, capture_output=True)
        return ['-hwaccel', 'cuda', '-hwaccel_output_format', 'cuda']
    except:
        pass

    # Check for Intel Quick Sync
    if os.path.exists('/dev/dri/renderD128'):
        return ['-hwaccel', 'vaapi', '-vaapi_device', '/dev/dri/renderD128']

    # No hardware acceleration
    return []

# Optimized FFmpeg command with hardware acceleration
def transcode_with_hw_accel(input_path, output_path, resolution):
    hw_accel = get_ffmpeg_hw_accel()

    cmd = [
        'ffmpeg',
        *hw_accel,
        '-i', input_path,
        '-vf', f'scale=-2:{resolution}',
        '-c:v', 'h264_nvenc' if 'cuda' in hw_accel else 'libx264',
        '-preset', 'fast',
        '-crf', '23',
        output_path
    ]

    subprocess.run(cmd, check=True)
```

---

### Performance Benchmarks

```python
# tests/benchmarks/benchmark_suite.py

import pytest
import time
from statistics import mean, median

class PerformanceBenchmark:
    """Performance benchmark suite"""

    def __init__(self):
        self.results = {}

    def benchmark(self, name: str, func, iterations: int = 100):
        """Run benchmark"""

        times = []

        for i in range(iterations):
            start = time.time()
            func()
            end = time.time()

            times.append((end - start) * 1000)  # Convert to ms

        self.results[name] = {
            'mean': mean(times),
            'median': median(times),
            'min': min(times),
            'max': max(times),
            'p95': sorted(times)[int(len(times) * 0.95)]
        }

    def report(self):
        """Print benchmark results"""

        print("\n=== Performance Benchmark Results ===\n")

        for name, metrics in self.results.items():
            print(f"{name}:")
            print(f"  Mean:   {metrics['mean']:.2f}ms")
            print(f"  Median: {metrics['median']:.2f}ms")
            print(f"  Min:    {metrics['min']:.2f}ms")
            print(f"  Max:    {metrics['max']:.2f}ms")
            print(f"  P95:    {metrics['p95']:.2f}ms")
            print()

# Run benchmarks
benchmark = PerformanceBenchmark()

benchmark.benchmark("List Jobs", lambda: client.get("/api/jobs", headers=headers))
benchmark.benchmark("Get Job Status", lambda: client.get(f"/api/jobs/{job_id}", headers=headers))
benchmark.benchmark("Get Statistics", lambda: client.get("/api/jobs/stats", headers=headers))

benchmark.report()

# Assert performance targets
assert benchmark.results["List Jobs"]["p95"] < 200  # < 200ms
assert benchmark.results["Get Job Status"]["p95"] < 100  # < 100ms
```

---

### Test Coverage

```bash
# Generate coverage report

# Install coverage
pip install coverage pytest-cov

# Run tests with coverage
pytest --cov=app --cov-report=html --cov-report=term

# View report
open htmlcov/index.html

# Coverage requirements in pytest.ini
[tool:pytest]
addopts = --cov=app --cov-fail-under=80
```

---

## CI/CD Integration

```yaml
# .github/workflows/tests.yml

name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest

    services:
      postgres:
        image: postgres:latest
        env:
          POSTGRES_PASSWORD: test_password
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

      redis:
        image: redis:latest
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

    steps:
      - uses: actions/checkout@v2

      - name: Set up Python
        uses: actions/setup-python@v2
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install -r requirements-dev.txt

      - name: Run tests
        run: |
          pytest --cov=app --cov-report=xml

      - name: Upload coverage
        uses: codecov/codecov-action@v2
        with:
          files: ./coverage.xml

      - name: Run load tests
        run: |
          locust -f tests/load/locustfile.py --headless -u 100 -r 10 -t 60s

      - name: Run benchmarks
        run: |
          python tests/benchmarks/benchmark_suite.py
```

---

## Performance Targets Summary

| Metric | Target | Current | Status |
|--------|--------|---------|--------|
| API p95 response time | < 200ms | TBD | ⏳ |
| Database query p95 | < 50ms | TBD | ⏳ |
| Test coverage | ≥ 80% | TBD | ⏳ |
| Concurrent requests | 100 | TBD | ⏳ |
| Processing throughput | 100GB/day | TBD | ⏳ |
| Memory usage | < 8GB | TBD | ⏳ |
| Job success rate | > 99% | TBD | ⏳ |

---

## Next Sprint

Sprint 9: Documentation & Deployment
