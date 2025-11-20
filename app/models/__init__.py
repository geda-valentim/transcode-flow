"""
SQLAlchemy models for the Transcode Flow application.
"""
from app.models.job import Job, JobStatus, Base as JobBase
from app.models.api_key import APIKey, Base as APIKeyBase

# Use a single Base for all models
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

# Re-export models
__all__ = ["Job", "JobStatus", "APIKey", "Base"]
