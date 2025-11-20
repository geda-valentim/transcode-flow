"""
Transcode Flow API - Main Application
FastAPI application for video transcoding service.
"""
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
import logging
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import shutil

from app.core.config import settings
from app.api.v1 import api_router
from app.db import check_db_connection
from app.middleware import MetricsMiddleware
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from app.metrics import app_info, app_uptime_seconds

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)

logger = logging.getLogger(__name__)

# Track application start time for uptime metric
import time
_app_start_time = time.time()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for startup and shutdown events.
    """
    # Startup
    logger.info("Starting Transcode Flow API...")
    logger.info(f"Version: {settings.APP_VERSION}")
    logger.info(f"Environment: {settings.API_HOST}:{settings.API_PORT}")

    # Initialize app info metric
    app_info.labels(version=settings.APP_VERSION, environment="production").set(1)

    # Check database connection
    if check_db_connection():
        logger.info("Database connection: OK")
    else:
        logger.error("Database connection: FAILED")

    logger.info("Application startup complete")

    yield

    # Shutdown
    logger.info("Shutting down Transcode Flow API...")


# Create FastAPI application
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Video Transcoding Service Platform with multi-resolution transcoding, "
                "HLS streaming, audio extraction, and automatic transcription.",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add Prometheus Metrics Middleware
app.add_middleware(MetricsMiddleware)


# Exception handlers
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Handle HTTP exceptions."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.detail,
            "status_code": exc.status_code,
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle request validation errors."""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": "Validation error",
            "details": exc.errors(),
        },
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle general exceptions."""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "Internal server error",
            "message": str(exc) if settings.LOG_LEVEL == "DEBUG" else "An unexpected error occurred",
        },
    )


# Health check endpoints
@app.get("/health", tags=["health"])
async def health_check():
    """
    Basic health check endpoint.
    Returns the API status and version.
    """
    db_status = "healthy" if check_db_connection() else "unhealthy"

    return {
        "status": "healthy",
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "database": db_status,
    }


@app.get("/health/detailed", tags=["health"])
async def detailed_health_check():
    """
    Detailed health check of all services.

    Checks connectivity and status of:
    - PostgreSQL database
    - Redis cache
    - MinIO object storage
    - Disk space usage

    Returns overall status (healthy/degraded/unhealthy) and individual service status.
    """
    import requests
    from app.core.minio_client import get_minio_client

    status = {
        "overall": "healthy",
        "services": {},
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

    # Check PostgreSQL
    try:
        db_healthy = check_db_connection()
        if db_healthy:
            status["services"]["postgresql"] = {"status": "healthy"}
        else:
            status["services"]["postgresql"] = {"status": "unhealthy", "error": "Connection failed"}
            status["overall"] = "degraded"
    except Exception as e:
        status["services"]["postgresql"] = {"status": "unhealthy", "error": str(e)}
        status["overall"] = "degraded"

    # Check Redis
    try:
        import redis
        r = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=0,
            socket_connect_timeout=2
        )
        r.ping()
        status["services"]["redis"] = {"status": "healthy"}
    except Exception as e:
        status["services"]["redis"] = {"status": "unhealthy", "error": str(e)}
        status["overall"] = "degraded"

    # Check MinIO
    try:
        minio_client = get_minio_client()
        # Try to list buckets as a connectivity test
        buckets = minio_client.list_buckets()
        status["services"]["minio"] = {
            "status": "healthy",
            "buckets": len(buckets)
        }
    except Exception as e:
        status["services"]["minio"] = {"status": "unhealthy", "error": str(e)}
        status["overall"] = "degraded"

    # Check Airflow (optional - may not be accessible from API container)
    try:
        response = requests.get(
            f"http://{settings.AIRFLOW_WEBSERVER_HOST}:{settings.AIRFLOW_WEBSERVER_PORT}/health",
            timeout=2
        )
        if response.status_code == 200:
            status["services"]["airflow"] = {"status": "healthy"}
        else:
            status["services"]["airflow"] = {
                "status": "unhealthy",
                "http_code": response.status_code
            }
            status["overall"] = "degraded"
    except Exception as e:
        # Airflow health check failure is not critical for API operation
        status["services"]["airflow"] = {
            "status": "unavailable",
            "error": str(e),
            "note": "Airflow health check is optional"
        }

    # Check disk space
    try:
        disk_usage = shutil.disk_usage("/data")
        free_percent = (disk_usage.free / disk_usage.total) * 100

        disk_status = "healthy"
        if free_percent < 10:
            disk_status = "critical"
            status["overall"] = "warning"
        elif free_percent < 20:
            disk_status = "warning"

        status["services"]["disk"] = {
            "status": disk_status,
            "total_gb": round(disk_usage.total / (1024**3), 2),
            "used_gb": round(disk_usage.used / (1024**3), 2),
            "free_gb": round(disk_usage.free / (1024**3), 2),
            "free_percent": round(free_percent, 2)
        }
    except Exception as e:
        status["services"]["disk"] = {"status": "unknown", "error": str(e)}

    return status


# Include API router
app.include_router(api_router, prefix=settings.API_V1_PREFIX)


# Prometheus metrics endpoint
@app.get("/metrics", tags=["monitoring"])
async def metrics():
    """
    Prometheus metrics endpoint.

    Returns metrics in Prometheus text format for scraping.
    This endpoint is excluded from metrics collection to avoid feedback loops.

    Metrics include:
    - API request counts and durations
    - Job processing metrics
    - Storage usage metrics
    - Database connection metrics
    - System resource metrics
    """
    # Update uptime metric
    uptime = time.time() - _app_start_time
    app_uptime_seconds.set(uptime)

    # Generate Prometheus metrics in text format
    metrics_output = generate_latest()

    return Response(
        content=metrics_output,
        media_type=CONTENT_TYPE_LATEST
    )


# Root endpoint
@app.get("/", tags=["root"])
async def root():
    """
    Root endpoint.
    Provides basic API information.
    """
    return {
        "message": "Welcome to Transcode Flow API",
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "health": "/health",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=True,
        log_level=settings.LOG_LEVEL.lower(),
    )
