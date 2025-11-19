# Sprint 1: Core API & Video Validation (Week 2)

**Goal:** Build the FastAPI application with video upload and validation

**Duration:** 1 week
**Team Size:** 1-2 developers

---

## Tasks

- [ ] Set up FastAPI application structure
- [ ] Implement API key authentication middleware
- [ ] Create POST /api/v1/jobs/upload endpoint
- [ ] Create POST /api/v1/jobs/filesystem endpoint
- [ ] Create POST /api/v1/jobs/minio endpoint
- [ ] Implement video validation logic using FFprobe
- [ ] Add custom thumbnail upload support
- [ ] Implement user metadata validation and sanitization
- [ ] Create database models (SQLAlchemy)
- [ ] Add OpenAPI/Swagger documentation
- [ ] Write unit tests for validation logic
- [ ] Implement rate limiting

---

## Deliverables

- ✅ Working FastAPI application
- ✅ All upload endpoints functional
- ✅ Video validation working
- ✅ API documentation available

---

## Acceptance Criteria

- [ ] Can upload video via API and receive job_id
- [ ] Invalid videos are rejected with clear error messages
- [ ] API documentation accessible at http://localhost:8000/docs
- [ ] Rate limiting works correctly (100 req/hour per API key)
- [ ] Custom thumbnails can be uploaded (JPG, PNG, WebP, max 5MB)
- [ ] User metadata validated and stored in JSONB column

---

## Technical Details

### FastAPI Project Structure

```
app/
├── main.py                 # FastAPI app initialization
├── api/
│   └── v1/
│       ├── endpoints/
│       │   ├── jobs.py     # Job endpoints
│       │   └── admin.py    # Admin endpoints
│       └── deps.py         # Dependencies (auth, etc.)
├── core/
│   ├── config.py           # Configuration
│   ├── security.py         # API key validation
│   └── rate_limit.py       # Rate limiting
├── models/
│   ├── job.py              # SQLAlchemy models
│   ├── task.py
│   └── api_key.py
├── schemas/
│   ├── job.py              # Pydantic schemas
│   └── api_key.py
├── services/
│   ├── video_validator.py  # FFprobe validation
│   └── metadata_service.py # Metadata handling
└── db/
    └── session.py          # Database session
```

### API Endpoints to Implement

**1. POST /api/v1/jobs/upload**
```python
@router.post("/upload", response_model=JobResponse)
async def upload_video(
    file: UploadFile,
    thumbnail: Optional[UploadFile] = None,
    priority: int = 5,
    metadata: Optional[str] = None,
    api_key: str = Depends(verify_api_key)
):
    # Validate video
    # Save to temp
    # Create job in DB
    # Return job_id
```

**2. POST /api/v1/jobs/filesystem**
```python
@router.post("/filesystem", response_model=JobResponse)
async def create_from_filesystem(
    request: FilesystemJobRequest,
    api_key: str = Depends(verify_api_key)
):
    # Validate file exists
    # Validate video
    # Create job in DB
    # Return job_id
```

**3. POST /api/v1/jobs/minio**
```python
@router.post("/minio", response_model=JobResponse)
async def create_from_minio(
    request: MinioJobRequest,
    api_key: str = Depends(verify_api_key)
):
    # Validate object exists in MinIO
    # Validate video
    # Create job in DB
    # Return job_id
```

### Video Validation Logic

```python
class VideoValidator:
    def validate(self, file_path: str) -> VideoInfo:
        # 1. Check file exists
        # 2. Run FFprobe to get info
        # 3. Validate format (mp4, avi, mov, mkv, etc.)
        # 4. Validate codec compatibility
        # 5. Check resolution >= 360p
        # 6. Check duration (1s - 24h)
        # 7. Detect corrupted files
        # 8. Return video metadata

        probe_cmd = [
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            file_path
        ]

        # Parse and return VideoInfo
```

### Metadata Validation

```python
class MetadataValidator:
    ALLOWED_FIELDS = [
        "title", "description", "tags", "category",
        "author", "copyright", "language"
    ]

    def validate(self, metadata: dict) -> dict:
        # 1. Sanitize user input
        # 2. Validate field types
        # 3. Limit string lengths
        # 4. Allow custom fields
        # 5. Return cleaned metadata
```

### Rate Limiting

```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_api_key)

@app.post("/api/v1/jobs/upload")
@limiter.limit("100/hour")  # Per API key
async def upload_video(...):
    ...
```

---

## Database Models

### Job Model

```python
class Job(Base):
    __tablename__ = "jobs"

    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    api_key = Column(String(64), nullable=False, index=True)
    status = Column(String(20), nullable=False, default="pending")
    source_type = Column(String(20), nullable=False)
    source_path = Column(Text, nullable=False)
    priority = Column(Integer, default=5)
    user_metadata = Column(JSONB, default={})

    # Video info
    original_filename = Column(String(255))
    file_size_bytes = Column(BigInteger)
    duration_seconds = Column(Float)
    source_resolution = Column(String(20))
    source_width = Column(Integer)
    source_height = Column(Integer)
    # ... more fields

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
```

---

## Testing

### Unit Tests

```python
# tests/test_validation.py
def test_valid_video():
    validator = VideoValidator()
    info = validator.validate("sample.mp4")
    assert info.valid == True
    assert info.resolution == "1920x1080"

def test_invalid_format():
    validator = VideoValidator()
    with pytest.raises(ValidationError):
        validator.validate("invalid.txt")

def test_corrupted_video():
    validator = VideoValidator()
    with pytest.raises(ValidationError):
        validator.validate("corrupted.mp4")
```

### Integration Tests

```python
# tests/test_api.py
def test_upload_endpoint(client, test_video):
    response = client.post(
        "/api/v1/jobs/upload",
        files={"file": test_video},
        headers={"X-API-Key": "test_key"}
    )
    assert response.status_code == 202
    assert "job_id" in response.json()

def test_rate_limiting(client):
    # Make 101 requests
    for i in range(101):
        response = client.post(...)
    assert response.status_code == 429  # Too Many Requests
```

---

## Environment Setup

### Dependencies (requirements.txt)

```txt
fastapi>=0.104.0
uvicorn[standard]>=0.24.0
sqlalchemy>=2.0.0
psycopg2-binary>=2.9.0
pydantic>=2.0.0
python-multipart>=0.0.6
slowapi>=0.1.9
pytest>=7.4.0
pytest-asyncio>=0.21.0
```

### Docker Container for FastAPI

```dockerfile
FROM python:3.11-slim

# Install FFmpeg for validation
RUN apt-get update && apt-get install -y ffmpeg

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

---

## Notes

- **Security:** Always hash API keys before storing (SHA-256)
- **File Size:** Limit uploads to 20GB per video
- **Temp Storage:** Use `/data/temp/` for uploaded files
- **Cleanup:** Remove temp files after job creation
- **Validation:** FFprobe must run in Docker container

---

## Next Sprint

Sprint 2: Airflow DAG & Celery Workers
