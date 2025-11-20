"""
API v1 router aggregation.
"""
from fastapi import APIRouter
from app.api.v1.endpoints import jobs, events, streaming, api_keys
from app.api import downloads

api_router = APIRouter()

# Include job endpoints
api_router.include_router(jobs.router, prefix="/jobs", tags=["jobs"])

# Include events endpoints (SSE)
api_router.include_router(events.router, prefix="/events", tags=["events"])

# Include streaming endpoints
api_router.include_router(streaming.router, tags=["streaming"])

# Include downloads endpoints
api_router.include_router(downloads.router, tags=["downloads"])

# Include API key management endpoints
api_router.include_router(api_keys.router, tags=["api-keys"])

__all__ = ["api_router"]
