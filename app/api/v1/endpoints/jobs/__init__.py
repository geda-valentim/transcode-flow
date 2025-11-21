"""
Job endpoints package.

Consolidates all job-related endpoints from modular submodules:
- creation: Job creation endpoints (upload, filesystem, minio)
- management: Job control endpoints (status, cancel, retry, delete, priority)
- queries: Job listing, searching, and statistics
- export: Data export in CSV/JSON formats
- observability: Real-time monitoring and metrics via XCom
"""
from fastapi import APIRouter
from . import creation, management, queries, export, observability

# Create main router for jobs
router = APIRouter()

# Include creation endpoints (no prefix, direct routes like /upload)
router.include_router(creation.router, tags=["jobs-creation"])

# Include query endpoints first (for list endpoint at root /jobs)
router.include_router(queries.router, tags=["jobs-queries"])

# Include management endpoints (/{job_id} routes)
router.include_router(management.router, tags=["jobs-management"])

# Include export endpoints
router.include_router(export.router, tags=["jobs-export"])

# Include observability endpoints
router.include_router(observability.router, tags=["jobs-observability"])

__all__ = ["router"]
