"""
MinIO Client Module

Provides MinIO client configuration and initialization.
"""
from minio import Minio
from app.core.config import settings


def get_minio_client() -> Minio:
    """
    Create and return a MinIO client instance.

    Returns:
        Minio: Configured MinIO client
    """
    return Minio(
        f"{settings.MINIO_HOST}:{settings.MINIO_PORT}",
        access_key=settings.MINIO_ACCESS_KEY,
        secret_key=settings.MINIO_SECRET_KEY,
        secure=settings.MINIO_SECURE
    )
