"""
Pytest configuration and shared fixtures for Transcode Flow tests.
"""
import os
import sys
from typing import Generator
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool
import redis

# Add app to Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.main import app
from app.core.database import get_db, Base
from app.models.api_key import APIKey
from app.core.security import get_current_api_key
import hashlib
from datetime import datetime, timezone, timedelta


# Test Database Configuration
TEST_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="function")
def db() -> Generator[Session, None, None]:
    """Create a fresh database for each test."""
    Base.metadata.create_all(bind=engine)
    db_session = TestingSessionLocal()
    try:
        yield db_session
    finally:
        db_session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def client(db: Session) -> Generator[TestClient, None, None]:
    """Create a test client with database dependency override."""
    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


@pytest.fixture
def master_api_key(db: Session) -> APIKey:
    """Create a master API key for testing."""
    raw_key = "test_master_key_12345678"
    full_key = f"tfk_{raw_key}"
    key_hash = hashlib.sha256(full_key.encode()).hexdigest()
    key_prefix = full_key[:12]

    api_key = APIKey(
        key_hash=key_hash,
        key_prefix=key_prefix,
        name="Test Master Key",
        email="master@test.com",
        organization="Test Org",
        is_active=True,
        is_master_key=True,
        permissions={
            "can_upload": True,
            "can_transcode": True,
            "can_extract_audio": True,
            "can_transcribe": True,
            "max_resolution": "4k",
        },
        scopes=[
            "jobs:create",
            "jobs:read",
            "jobs:list",
            "jobs:delete",
            "streaming:generate_token",
            "api_keys:manage",
        ],
        rate_limit_per_hour=1000,
        rate_limit_per_day=10000,
        storage_quota_gb=500,
        jobs_quota_monthly=5000,
        expires_at=datetime.now(timezone.utc) + timedelta(days=365),
    )

    db.add(api_key)
    db.commit()
    db.refresh(api_key)

    # Attach the raw key for testing
    api_key._test_key = full_key

    return api_key


@pytest.fixture
def sub_api_key(db: Session, master_api_key: APIKey) -> APIKey:
    """Create a sub API key for testing."""
    raw_key = "test_sub_key_12345678"
    full_key = f"tfk_{raw_key}"
    key_hash = hashlib.sha256(full_key.encode()).hexdigest()
    key_prefix = full_key[:12]

    api_key = APIKey(
        key_hash=key_hash,
        key_prefix=key_prefix,
        name="Test Sub Key",
        email="master@test.com",
        organization="Test Org",
        is_active=True,
        is_master_key=False,
        parent_key_id=master_api_key.id,
        permissions={
            "can_upload": True,
            "can_transcode": True,
            "can_extract_audio": False,
            "can_transcribe": False,
            "max_resolution": "1080p",
        },
        scopes=[
            "jobs:create",
            "jobs:read",
            "jobs:list",
        ],
        rate_limit_per_hour=100,
        rate_limit_per_day=1000,
        storage_quota_gb=50,
        jobs_quota_monthly=500,
        expires_at=datetime.now(timezone.utc) + timedelta(days=90),
    )

    db.add(api_key)
    db.commit()
    db.refresh(api_key)

    # Attach the raw key for testing
    api_key._test_key = full_key

    return api_key


@pytest.fixture
def authenticated_client(client: TestClient, master_api_key: APIKey) -> TestClient:
    """Create a test client with authentication headers."""
    client.headers = {
        **client.headers,
        "X-API-Key": master_api_key._test_key,
    }
    return client


@pytest.fixture
def redis_client():
    """Create a Redis client for testing (mocked if Redis unavailable)."""
    try:
        client = redis.Redis(host='localhost', port=6379, db=15, decode_responses=True)
        client.ping()
        yield client
        # Cleanup test data
        client.flushdb()
    except (redis.ConnectionError, redis.TimeoutError):
        # If Redis is not available, return a mock
        from unittest.mock import MagicMock
        mock_redis = MagicMock()
        yield mock_redis


@pytest.fixture
def sample_job_data():
    """Sample job data for testing."""
    return {
        "input_url": "https://example.com/video.mp4",
        "output_formats": [
            {
                "format": "hls",
                "video_codec": "h264",
                "audio_codec": "aac",
                "resolutions": ["1080p", "720p", "480p"],
                "bitrate": "auto",
            }
        ],
        "extract_audio": False,
        "transcribe": False,
        "webhook_url": "https://example.com/webhook",
    }


@pytest.fixture(autouse=True)
def cleanup_files():
    """Cleanup any test files created during tests."""
    yield
    # Add cleanup logic here if needed for temporary files


@pytest.fixture
def mock_ffmpeg(monkeypatch):
    """Mock FFmpeg calls for unit tests."""
    from unittest.mock import MagicMock
    mock = MagicMock()
    monkeypatch.setattr("app.services.video_processor.ffmpeg", mock)
    return mock


@pytest.fixture
def mock_minio(monkeypatch):
    """Mock MinIO client for unit tests."""
    from unittest.mock import MagicMock
    mock = MagicMock()
    monkeypatch.setattr("app.services.storage.minio_client", mock)
    return mock
