"""
Application configuration management using Pydantic Settings.
Loads environment variables and provides centralized configuration.
"""
import os
from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import Field, validator


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # API Metadata
    APP_NAME: str = "Transcode Flow API"
    APP_VERSION: str = "1.0.0"
    API_V1_PREFIX: str = "/api/v1"

    # Database
    DATABASE_URL: str = Field(..., env="DATABASE_URL")

    # Redis
    REDIS_URL: str = Field(..., env="REDIS_URL")

    # MinIO / S3
    MINIO_HOST: str = Field(..., env="MINIO_HOST")
    MINIO_PORT: int = Field(9000, env="MINIO_PORT")
    MINIO_ACCESS_KEY: str = Field(..., env="MINIO_ACCESS_KEY")
    MINIO_SECRET_KEY: str = Field(..., env="MINIO_SECRET_KEY")
    MINIO_BUCKET: str = Field("videos", env="MINIO_BUCKET")
    MINIO_SECURE: bool = Field(False, env="MINIO_SECURE")

    # Security
    SECRET_KEY: str = Field(..., env="SECRET_KEY")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days

    # CORS
    CORS_ORIGINS: list = ["*"]

    # File Upload Limits
    MAX_UPLOAD_SIZE: int = 5 * 1024 * 1024 * 1024  # 5GB
    ALLOWED_VIDEO_FORMATS: list = [
        "video/mp4",
        "video/x-matroska",  # MKV
        "video/quicktime",   # MOV
        "video/x-msvideo",   # AVI
        "video/webm",
        "video/x-flv",
    ]

    # Temp Storage
    TEMP_DIR: str = Field("/data/temp", env="TEMP_DIR")

    # Rate Limiting
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_PER_HOUR: int = 100
    RATE_LIMIT_PER_DAY: int = 1000

    # Video Validation
    MIN_VIDEO_DURATION: int = 1  # seconds
    MAX_VIDEO_DURATION: int = 7200  # 2 hours
    MIN_VIDEO_WIDTH: int = 320
    MIN_VIDEO_HEIGHT: int = 240
    MAX_VIDEO_WIDTH: int = 7680  # 8K
    MAX_VIDEO_HEIGHT: int = 4320  # 8K

    # FFmpeg / FFprobe
    FFPROBE_PATH: str = Field("/usr/bin/ffprobe", env="FFPROBE_PATH")
    FFMPEG_PATH: str = Field("/usr/bin/ffmpeg", env="FFMPEG_PATH")

    # API Host
    API_HOST: str = Field("0.0.0.0", env="API_HOST")
    API_PORT: int = Field(8000, env="API_PORT")

    # Webhook Configuration
    WEBHOOK_TIMEOUT: int = 30  # seconds
    WEBHOOK_MAX_RETRIES: int = 3

    # Logging
    LOG_LEVEL: str = Field("INFO", env="LOG_LEVEL")

    @validator("TEMP_DIR")
    def validate_temp_dir(cls, v):
        """Ensure temp directory exists."""
        os.makedirs(v, exist_ok=True)
        return v

    @validator("DATABASE_URL")
    def validate_database_url(cls, v):
        """Validate database URL format."""
        if not v.startswith(("postgresql://", "postgresql+asyncpg://")):
            raise ValueError("DATABASE_URL must be a PostgreSQL connection string")
        return v

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


# Global settings instance
settings = Settings()
