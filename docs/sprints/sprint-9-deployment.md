# Sprint 9: Documentation & Deployment (Week 10)

**Goal:** Complete documentation and deployment automation

**Duration:** 1 week
**Team Size:** 2 developers

---

## Tasks

- [ ] Write comprehensive API documentation (OpenAPI/Swagger)
- [ ] Create user guide and tutorials
- [ ] Document deployment procedures
- [ ] Create environment configuration guide
- [ ] Write operational runbooks
- [ ] Document disaster recovery procedures
- [ ] Create database migration scripts
- [ ] Implement automated deployment scripts
- [ ] Set up CI/CD pipeline
- [ ] Create Docker image optimization
- [ ] Implement health checks and readiness probes
- [ ] Document monitoring and alerting setup
- [ ] Create troubleshooting guide
- [ ] Write security best practices guide
- [ ] Create API client libraries (Python, JavaScript)
- [ ] Document scaling procedures
- [ ] Create backup and restore scripts
- [ ] Write performance tuning guide
- [ ] Create onboarding documentation for new developers

---

## Deliverables

- ✅ Complete API documentation
- ✅ Deployment automation scripts
- ✅ Operational runbooks
- ✅ CI/CD pipeline configured
- ✅ API client libraries

---

## Acceptance Criteria

- [ ] API documentation complete with examples
- [ ] Deployment can be done with single command
- [ ] CI/CD pipeline automatically tests and deploys
- [ ] All runbooks tested and validated
- [ ] Disaster recovery procedure tested
- [ ] API clients functional in Python and JavaScript
- [ ] Documentation covers all features

---

## Technical Details

### API Documentation (OpenAPI/Swagger)

```python
# main.py - FastAPI automatic OpenAPI generation

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

app = FastAPI(
    title="Transcode Flow API",
    description="""
    ## Video Transcoding Service Platform

    Complete video processing pipeline with:
    - Multi-resolution transcoding (360p, 720p)
    - HLS streaming preparation
    - Audio extraction (MP3)
    - Automatic transcription with Whisper
    - Real-time progress tracking

    ## Authentication

    All endpoints require API key authentication via `X-API-Key` header.

    ## Rate Limits

    - Per minute: 100 requests
    - Per hour: 1000 requests
    - Per day: 10000 requests

    ## Support

    For support, contact: support@transcode-flow.com
    """,
    version="1.0.0",
    contact={
        "name": "Transcode Flow Support",
        "email": "support@transcode-flow.com",
        "url": "https://transcode-flow.com"
    },
    license_info={
        "name": "Proprietary",
    },
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)

# Enhanced endpoint with detailed documentation
@app.post(
    "/api/upload",
    response_model=JobResponse,
    summary="Upload video for processing",
    description="""
    Upload a video file for transcoding and processing.

    The video will be:
    1. Validated using FFprobe
    2. Transcoded to 360p and 720p (if source resolution allows)
    3. Prepared for HLS streaming
    4. Audio extracted to MP3
    5. Transcribed using Whisper (90+ languages)
    6. Thumbnails generated (5 automatic + optional custom)

    Maximum file size: 10GB
    Supported formats: MP4, AVI, MKV, MOV, WebM, FLV
    """,
    responses={
        200: {
            "description": "Video uploaded successfully",
            "content": {
                "application/json": {
                    "example": {
                        "job_id": "123e4567-e89b-12d3-a456-426614174000",
                        "status": "queued",
                        "filename": "my_video.mp4",
                        "priority": 5,
                        "created_at": "2025-01-15T10:30:00Z"
                    }
                }
            }
        },
        400: {"description": "Invalid video format or corrupted file"},
        401: {"description": "Invalid API key"},
        413: {"description": "File too large or quota exceeded"},
        429: {"description": "Rate limit exceeded"}
    },
    tags=["Video Processing"]
)
async def upload_video(
    file: UploadFile = File(..., description="Video file to process"),
    thumbnail: Optional[UploadFile] = File(None, description="Optional custom thumbnail (JPEG/PNG)"),
    priority: int = Query(5, ge=1, le=10, description="Job priority (1=low, 10=critical)"),
    metadata: Optional[str] = Query(None, description="Custom metadata (JSON string)"),
    api_key: str = Depends(verify_api_key)
):
    # Implementation...
    pass
```

---

### User Guide

```markdown
# Transcode Flow User Guide

## Quick Start

### 1. Get Your API Key

Contact your administrator or create an API key via the admin panel:

```bash
curl -X POST http://localhost/api-keys/ \
  -H "X-API-Key: ADMIN_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "My Application",
    "scopes": ["read", "write"],
    "rate_limit_per_minute": 100
  }'
```

Save the returned API key securely - it will only be shown once!

### 2. Upload a Video

```bash
curl -X POST http://localhost/api/upload \
  -H "X-API-Key: YOUR_API_KEY" \
  -F "file=@my_video.mp4" \
  -F "priority=5"
```

Response:
```json
{
  "job_id": "123e4567-e89b-12d3-a456-426614174000",
  "status": "queued",
  "filename": "my_video.mp4",
  "created_at": "2025-01-15T10:30:00Z"
}
```

### 3. Check Job Status

```bash
curl http://localhost/api/jobs/123e4567-e89b-12d3-a456-426614174000 \
  -H "X-API-Key: YOUR_API_KEY"
```

### 4. Download Outputs

Once status is `completed`, download your processed files:

```bash
# Get download URL
curl http://localhost/api/jobs/123e4567-e89b-12d3-a456-426614174000/download/360p \
  -H "X-API-Key: YOUR_API_KEY"

# Download file
curl -o video_360p.mp4 "PRESIGNED_URL"
```

### 5. Stream with HLS

Get streaming token:

```bash
curl http://localhost/api/streaming/token/123e4567-e89b-12d3-a456-426614174000/360p \
  -H "X-API-Key: YOUR_API_KEY"
```

Use the returned `playlist_url` in your video player.

## Advanced Usage

### Custom Thumbnails

Upload a custom thumbnail with your video:

```bash
curl -X POST http://localhost/api/upload \
  -H "X-API-Key: YOUR_API_KEY" \
  -F "file=@my_video.mp4" \
  -F "thumbnail=@custom_thumb.jpg"
```

### User Metadata

Attach custom metadata to your job:

```bash
curl -X POST http://localhost/api/upload \
  -H "X-API-Key: YOUR_API_KEY" \
  -F "file=@my_video.mp4" \
  -F 'metadata={"campaign_id": "2025-Q1", "user_id": "12345"}'
```

### Real-Time Progress Updates

Monitor progress using Server-Sent Events:

```javascript
const eventSource = new EventSource(
  `http://localhost/api/events/${jobId}/progress?api_key=${apiKey}`
);

eventSource.addEventListener('progress', (event) => {
  const data = JSON.parse(event.data);
  console.log(`Progress: ${data.progress}%`);
});

eventSource.addEventListener('complete', (event) => {
  console.log('Job completed!');
  eventSource.close();
});
```

## Video Player Integration

### Using video.js

```html
<link href="https://vjs.zencdn.net/8.0.4/video-js.css" rel="stylesheet" />
<script src="https://vjs.zencdn.net/8.0.4/video.min.js"></script>

<video id="my-video" class="video-js" controls preload="auto" width="640" height="360">
  <source src="PLAYLIST_URL" type="application/x-mpegURL">
</video>

<script>
  var player = videojs('my-video');
</script>
```

### Using hls.js

```html
<script src="https://cdn.jsdelivr.net/npm/hls.js@latest"></script>
<video id="video" controls></video>

<script>
  var video = document.getElementById('video');
  var hls = new Hls();
  hls.loadSource('PLAYLIST_URL');
  hls.attachMedia(video);
</script>
```

## Troubleshooting

### Job Stuck in "Queued"

Check worker status:
```bash
curl http://localhost/health/detailed
```

### Upload Fails with 413

Your video exceeds the size limit or storage quota:
```bash
# Check your quota
curl http://localhost/api-keys/YOUR_KEY_ID/usage \
  -H "X-API-Key: ADMIN_KEY"
```

### Transcription Not Generating

Ensure your video has audio:
```bash
ffprobe your_video.mp4 2>&1 | grep Audio
```
```

---

### Deployment Scripts

```bash
#!/bin/bash
# deploy.sh - Automated deployment script

set -e  # Exit on error

echo "====================================="
echo "Transcode Flow Deployment Script"
echo "====================================="

# Configuration
ENVIRONMENT=${1:-production}
DATA_DIR="/data"
BACKUP_DIR="/data/backups"

echo "Environment: $ENVIRONMENT"

# 1. Pre-deployment checks
echo "[1/10] Running pre-deployment checks..."

# Check Docker installed
if ! command -v docker &> /dev/null; then
    echo "Error: Docker not installed"
    exit 1
fi

# Check Docker Compose installed
if ! command -v docker compose &> /dev/null; then
    echo "Error: Docker Compose not installed"
    exit 1
fi

# Check data directory exists
if [ ! -d "$DATA_DIR" ]; then
    echo "Error: Data directory $DATA_DIR does not exist"
    exit 1
fi

# Check disk space (need at least 100GB free)
FREE_SPACE=$(df -BG $DATA_DIR | tail -1 | awk '{print $4}' | sed 's/G//')
if [ "$FREE_SPACE" -lt 100 ]; then
    echo "Warning: Less than 100GB free space on $DATA_DIR"
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# 2. Backup current database
echo "[2/10] Backing up database..."
timestamp=$(date +%Y%m%d_%H%M%S)
mkdir -p $BACKUP_DIR

docker exec postgres pg_dump -U transcode_user transcode_db | gzip > \
  "$BACKUP_DIR/postgres_$timestamp.sql.gz"

echo "Database backed up to: $BACKUP_DIR/postgres_$timestamp.sql.gz"

# 3. Pull latest code
echo "[3/10] Pulling latest code..."
git pull origin main

# 4. Build Docker images
echo "[4/10] Building Docker images..."
docker compose build --parallel

# 5. Stop running containers
echo "[5/10] Stopping running containers..."
docker compose down

# 6. Run database migrations
echo "[6/10] Running database migrations..."
docker compose run --rm fastapi alembic upgrade head

# 7. Start services
echo "[7/10] Starting services..."
docker compose up -d

# 8. Wait for services to be healthy
echo "[8/10] Waiting for services to be healthy..."
sleep 10

for i in {1..30}; do
    if curl -f http://localhost/health > /dev/null 2>&1; then
        echo "Services are healthy!"
        break
    fi

    if [ $i -eq 30 ]; then
        echo "Error: Services did not become healthy in time"
        echo "Check logs: docker compose logs"
        exit 1
    fi

    echo "Waiting for services... ($i/30)"
    sleep 2
done

# 9. Run smoke tests
echo "[9/10] Running smoke tests..."
python tests/smoke_tests.py

# 10. Cleanup old images
echo "[10/10] Cleaning up old Docker images..."
docker image prune -f

echo "====================================="
echo "Deployment completed successfully!"
echo "====================================="
echo ""
echo "Services:"
echo "  API:        http://localhost/api"
echo "  Docs:       http://localhost/docs"
echo "  Airflow:    http://localhost:8080"
echo "  Flower:     http://localhost:5555"
echo "  Grafana:    http://localhost:3000"
echo "  Prometheus: http://localhost:9090"
echo ""
echo "Check status: docker compose ps"
echo "View logs:    docker compose logs -f"
```

---

### Database Migration Scripts

```python
# migrations/versions/001_initial_schema.py

"""Initial schema

Revision ID: 001
Create Date: 2025-01-15 10:00:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY

revision = '001'
down_revision = None

def upgrade():
    # Create api_keys table
    op.create_table(
        'api_keys',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('key_hash', sa.String(64), unique=True, nullable=False),
        sa.Column('key_prefix', sa.String(8), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('scopes', ARRAY(sa.String), default=['read', 'write']),
        sa.Column('is_active', sa.Boolean(), default=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )

    op.create_index('idx_api_keys_hash', 'api_keys', ['key_hash'])

    # Create jobs table
    op.create_table(
        'jobs',
        sa.Column('id', UUID(), primary_key=True),
        sa.Column('api_key', sa.String(64), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('priority', sa.Integer(), default=5),
        sa.Column('user_metadata', JSONB, default={}),
        sa.Column('original_filename', sa.String(255)),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), onupdate=sa.func.now()),
    )

    op.create_index('idx_jobs_api_key', 'jobs', ['api_key'])
    op.create_index('idx_jobs_status', 'jobs', ['status'])
    op.create_index('idx_jobs_priority', 'jobs', ['priority'])

def downgrade():
    op.drop_table('jobs')
    op.drop_table('api_keys')
```

**Running Migrations:**

```bash
# Generate new migration
docker compose run --rm fastapi alembic revision --autogenerate -m "Add new field"

# Apply migrations
docker compose run --rm fastapi alembic upgrade head

# Rollback
docker compose run --rm fastapi alembic downgrade -1
```

---

### CI/CD Pipeline

```yaml
# .github/workflows/deploy.yml

name: Deploy

on:
  push:
    branches:
      - main
      - staging

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2

      - name: Run tests
        run: |
          docker compose -f docker compose.test.yml up --abort-on-container-exit

      - name: Upload coverage
        uses: codecov/codecov-action@v2

  build:
    needs: test
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2

      - name: Build Docker images
        run: |
          docker compose build

      - name: Push to registry
        run: |
          echo "${{ secrets.DOCKER_PASSWORD }}" | docker login -u "${{ secrets.DOCKER_USERNAME }}" --password-stdin
          docker compose push

  deploy-staging:
    needs: build
    if: github.ref == 'refs/heads/staging'
    runs-on: ubuntu-latest
    steps:
      - name: Deploy to staging
        uses: appleboy/ssh-action@master
        with:
          host: ${{ secrets.STAGING_HOST }}
          username: ${{ secrets.STAGING_USER }}
          key: ${{ secrets.STAGING_SSH_KEY }}
          script: |
            cd /opt/transcode-flow
            git pull origin staging
            ./deploy.sh staging

  deploy-production:
    needs: build
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    environment: production
    steps:
      - name: Deploy to production
        uses: appleboy/ssh-action@master
        with:
          host: ${{ secrets.PRODUCTION_HOST }}
          username: ${{ secrets.PRODUCTION_USER }}
          key: ${{ secrets.PRODUCTION_SSH_KEY }}
          script: |
            cd /opt/transcode-flow
            git pull origin main
            ./deploy.sh production

      - name: Notify Slack
        uses: 8398a7/action-slack@v3
        with:
          status: ${{ job.status }}
          text: 'Production deployment ${{ job.status }}'
          webhook_url: ${{ secrets.SLACK_WEBHOOK }}
```

---

### API Client Libraries

#### Python Client

```python
# clients/python/transcode_flow/__init__.py

import requests
from typing import Optional, Dict, BinaryIO
from datetime import datetime

class TranscodeFlowClient:
    """Python client for Transcode Flow API"""

    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update({'X-API-Key': api_key})

    def upload_video(
        self,
        file: BinaryIO,
        filename: str,
        priority: int = 5,
        thumbnail: Optional[BinaryIO] = None,
        metadata: Optional[Dict] = None
    ) -> Dict:
        """Upload video for processing"""

        files = {'file': (filename, file, 'video/mp4')}

        if thumbnail:
            files['thumbnail'] = ('thumbnail.jpg', thumbnail, 'image/jpeg')

        data = {'priority': priority}

        if metadata:
            import json
            data['metadata'] = json.dumps(metadata)

        response = self.session.post(
            f'{self.base_url}/api/upload',
            files=files,
            data=data
        )

        response.raise_for_status()
        return response.json()

    def get_job(self, job_id: str) -> Dict:
        """Get job status and details"""

        response = self.session.get(f'{self.base_url}/api/jobs/{job_id}')
        response.raise_for_status()
        return response.json()

    def list_jobs(
        self,
        status: Optional[str] = None,
        page: int = 1,
        per_page: int = 100
    ) -> Dict:
        """List jobs with filtering"""

        params = {'page': page, 'per_page': per_page}

        if status:
            params['status'] = status

        response = self.session.get(
            f'{self.base_url}/api/jobs',
            params=params
        )

        response.raise_for_status()
        return response.json()

    def cancel_job(self, job_id: str) -> Dict:
        """Cancel a job"""

        response = self.session.post(
            f'{self.base_url}/api/jobs/{job_id}/cancel'
        )

        response.raise_for_status()
        return response.json()

    def delete_job(self, job_id: str, delete_files: bool = True) -> Dict:
        """Delete a job"""

        response = self.session.delete(
            f'{self.base_url}/api/jobs/{job_id}',
            params={'delete_files': delete_files}
        )

        response.raise_for_status()
        return response.json()

    def get_download_url(self, job_id: str, file_type: str) -> str:
        """Get presigned download URL"""

        response = self.session.get(
            f'{self.base_url}/api/jobs/{job_id}/download/{file_type}'
        )

        response.raise_for_status()
        return response.json()['download_url']

    def get_streaming_token(self, job_id: str, resolution: str) -> Dict:
        """Get HLS streaming token"""

        response = self.session.get(
            f'{self.base_url}/api/streaming/token/{job_id}/{resolution}'
        )

        response.raise_for_status()
        return response.json()

    def wait_for_completion(
        self,
        job_id: str,
        timeout: int = 3600,
        poll_interval: int = 5
    ) -> Dict:
        """Wait for job to complete"""

        import time

        start_time = time.time()

        while time.time() - start_time < timeout:
            job = self.get_job(job_id)

            if job['status'] == 'completed':
                return job

            if job['status'] == 'failed':
                raise Exception(f"Job failed: {job.get('error', {}).get('message')}")

            time.sleep(poll_interval)

        raise TimeoutError(f"Job did not complete within {timeout} seconds")

# Usage example
if __name__ == '__main__':
    client = TranscodeFlowClient(
        base_url='http://localhost',
        api_key='YOUR_API_KEY'
    )

    # Upload video
    with open('my_video.mp4', 'rb') as f:
        result = client.upload_video(
            file=f,
            filename='my_video.mp4',
            priority=5,
            metadata={'campaign': '2025-Q1'}
        )

    job_id = result['job_id']
    print(f"Job created: {job_id}")

    # Wait for completion
    job = client.wait_for_completion(job_id)
    print(f"Job completed! Status: {job['status']}")

    # Get download URLs
    url_360p = client.get_download_url(job_id, '360p')
    url_720p = client.get_download_url(job_id, '720p')

    print(f"Download 360p: {url_360p}")
    print(f"Download 720p: {url_720p}")
```

#### JavaScript Client

```javascript
// clients/javascript/transcode-flow.js

class TranscodeFlowClient {
  constructor(baseUrl, apiKey) {
    this.baseUrl = baseUrl.replace(/\/$/, '');
    this.apiKey = apiKey;
  }

  async uploadVideo(file, options = {}) {
    const formData = new FormData();
    formData.append('file', file);

    if (options.thumbnail) {
      formData.append('thumbnail', options.thumbnail);
    }

    if (options.priority) {
      formData.append('priority', options.priority);
    }

    if (options.metadata) {
      formData.append('metadata', JSON.stringify(options.metadata));
    }

    const response = await fetch(`${this.baseUrl}/api/upload`, {
      method: 'POST',
      headers: {
        'X-API-Key': this.apiKey
      },
      body: formData
    });

    if (!response.ok) {
      throw new Error(`Upload failed: ${response.statusText}`);
    }

    return response.json();
  }

  async getJob(jobId) {
    const response = await fetch(`${this.baseUrl}/api/jobs/${jobId}`, {
      headers: {
        'X-API-Key': this.apiKey
      }
    });

    if (!response.ok) {
      throw new Error(`Get job failed: ${response.statusText}`);
    }

    return response.json();
  }

  async listJobs(options = {}) {
    const params = new URLSearchParams();

    if (options.status) params.append('status', options.status);
    if (options.page) params.append('page', options.page);
    if (options.per_page) params.append('per_page', options.per_page);

    const response = await fetch(
      `${this.baseUrl}/api/jobs?${params}`,
      {
        headers: {
          'X-API-Key': this.apiKey
        }
      }
    );

    if (!response.ok) {
      throw new Error(`List jobs failed: ${response.statusText}`);
    }

    return response.json();
  }

  streamProgress(jobId, onProgress, onComplete, onError) {
    const eventSource = new EventSource(
      `${this.baseUrl}/api/events/${jobId}/progress?api_key=${this.apiKey}`
    );

    eventSource.addEventListener('progress', (event) => {
      const data = JSON.parse(event.data);
      onProgress(data);
    });

    eventSource.addEventListener('complete', (event) => {
      const data = JSON.parse(event.data);
      onComplete(data);
      eventSource.close();
    });

    eventSource.onerror = (error) => {
      onError(error);
      eventSource.close();
    };

    return eventSource;
  }

  async waitForCompletion(jobId, timeout = 3600000, pollInterval = 5000) {
    const startTime = Date.now();

    while (Date.now() - startTime < timeout) {
      const job = await this.getJob(jobId);

      if (job.status === 'completed') {
        return job;
      }

      if (job.status === 'failed') {
        throw new Error(`Job failed: ${job.error?.message}`);
      }

      await new Promise(resolve => setTimeout(resolve, pollInterval));
    }

    throw new Error(`Job did not complete within ${timeout}ms`);
  }
}

// Usage example
const client = new TranscodeFlowClient('http://localhost', 'YOUR_API_KEY');

// Upload with progress tracking
const fileInput = document.getElementById('video-file');
const file = fileInput.files[0];

const result = await client.uploadVideo(file, {
  priority: 5,
  metadata: { campaign: '2025-Q1' }
});

console.log('Job created:', result.job_id);

// Stream progress
client.streamProgress(
  result.job_id,
  (data) => {
    console.log(`Progress: ${data.progress}%`);
    updateProgressBar(data.progress);
  },
  (data) => {
    console.log('Job completed!', data);
  },
  (error) => {
    console.error('Error:', error);
  }
);
```

---

## Operational Runbooks

### Runbook: Service Restart

```markdown
# Runbook: Restart Transcode Flow Services

## When to Use
- After configuration changes
- Service unresponsive
- Memory leaks detected

## Steps

1. Check current status:
   ```bash
   docker compose ps
   ```

2. Backup database (precaution):
   ```bash
   ./scripts/backup_database.sh
   ```

3. Stop services gracefully:
   ```bash
   docker compose down
   ```

4. Start services:
   ```bash
   docker compose up -d
   ```

5. Verify health:
   ```bash
   curl http://localhost/health/detailed
   ```

6. Check logs for errors:
   ```bash
   docker compose logs -f --tail=100
   ```

## Rollback
If issues occur, restore from backup and restart old version.
```

---

## Performance Targets

| Task | Target Time | Notes |
|------|-------------|-------|
| Deployment (zero downtime) | < 5 minutes | Automated script |
| Database migration | < 2 minutes | Depends on schema changes |
| Service startup | < 30 seconds | All containers healthy |
| Smoke tests | < 1 minute | Basic functionality check |

---

## Next Sprint

Sprint 10: Polish & Production Hardening
