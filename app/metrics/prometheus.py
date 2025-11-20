"""
Prometheus metrics for application monitoring.

This module defines all Prometheus metrics used throughout the application:
- API request metrics (requests, duration, in-progress)
- Job lifecycle metrics (created, completed, failed, queued)
- Video processing metrics (transcode duration, compression ratio)
- Storage metrics (usage, quota)
"""
from prometheus_client import Counter, Gauge, Histogram, Summary
from typing import Optional


# ============================================================================
# API Metrics
# ============================================================================

api_requests_total = Counter(
    "api_requests_total",
    "Total number of API requests",
    ["method", "endpoint", "status"],
)

api_request_duration_seconds = Histogram(
    "api_request_duration_seconds",
    "API request duration in seconds",
    ["method", "endpoint"],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

api_requests_in_progress = Gauge(
    "api_requests_in_progress",
    "Number of API requests currently being processed",
    ["method", "endpoint"],
)


# ============================================================================
# Job Metrics
# ============================================================================

jobs_total = Gauge(
    "jobs_total",
    "Total number of jobs in the system",
    ["status"],
)

jobs_created_total = Counter(
    "jobs_created_total",
    "Total number of jobs created",
    ["api_key_prefix"],
)

jobs_completed_total = Counter(
    "jobs_completed_total",
    "Total number of jobs completed successfully",
    ["api_key_prefix"],
)

jobs_failed_total = Counter(
    "jobs_failed_total",
    "Total number of jobs that failed",
    ["api_key_prefix", "error_type"],
)

jobs_cancelled_total = Counter(
    "jobs_cancelled_total",
    "Total number of jobs cancelled",
    ["api_key_prefix"],
)

jobs_queued = Gauge(
    "jobs_queued",
    "Number of jobs currently in queue",
)

jobs_processing = Gauge(
    "jobs_processing",
    "Number of jobs currently being processed",
)

job_processing_duration_seconds = Histogram(
    "job_processing_duration_seconds",
    "Time taken to process a job from start to completion",
    ["api_key_prefix"],
    buckets=[10, 30, 60, 120, 300, 600, 1200, 1800, 3600, 7200],
)

job_queue_time_seconds = Histogram(
    "job_queue_time_seconds",
    "Time a job spends in queue before processing starts",
    ["priority"],
    buckets=[1, 5, 10, 30, 60, 120, 300, 600, 1800, 3600],
)

job_retry_count = Counter(
    "job_retry_count",
    "Number of job retry attempts",
    ["api_key_prefix"],
)


# ============================================================================
# Video Processing Metrics
# ============================================================================

video_transcode_duration_seconds = Histogram(
    "video_transcode_duration_seconds",
    "Duration of video transcoding operations",
    ["resolution", "codec"],
    buckets=[10, 30, 60, 120, 300, 600, 1200, 1800, 3600, 7200, 14400],
)

video_transcoded_bytes = Counter(
    "video_transcoded_bytes",
    "Total bytes of video transcoded",
    ["resolution", "codec"],
)

video_compression_ratio = Histogram(
    "video_compression_ratio",
    "Compression ratio achieved (input_size / output_size)",
    buckets=[0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 5.0, 7.5, 10.0, 15.0, 20.0],
)

video_source_duration_seconds = Histogram(
    "video_source_duration_seconds",
    "Duration of source videos being processed",
    buckets=[30, 60, 120, 300, 600, 1200, 1800, 3600, 7200, 14400, 28800],
)

video_source_size_bytes = Histogram(
    "video_source_size_bytes",
    "Size of source videos being processed",
    buckets=[
        1_000_000,      # 1 MB
        10_000_000,     # 10 MB
        50_000_000,     # 50 MB
        100_000_000,    # 100 MB
        500_000_000,    # 500 MB
        1_000_000_000,  # 1 GB
        5_000_000_000,  # 5 GB
        10_000_000_000, # 10 GB
    ],
)

audio_extraction_duration_seconds = Histogram(
    "audio_extraction_duration_seconds",
    "Duration of audio extraction operations",
    buckets=[1, 5, 10, 30, 60, 120, 300, 600, 1200],
)

transcription_duration_seconds = Histogram(
    "transcription_duration_seconds",
    "Duration of audio transcription operations",
    ["model"],
    buckets=[10, 30, 60, 120, 300, 600, 1200, 1800, 3600],
)

transcription_word_count = Histogram(
    "transcription_word_count",
    "Number of words in transcribed text",
    buckets=[50, 100, 250, 500, 1000, 2500, 5000, 10000, 25000],
)

thumbnail_generation_duration_seconds = Histogram(
    "thumbnail_generation_duration_seconds",
    "Duration of thumbnail generation operations",
    buckets=[0.5, 1, 2, 5, 10, 20, 30],
)


# ============================================================================
# Storage Metrics
# ============================================================================

storage_used_bytes = Gauge(
    "storage_used_bytes",
    "Storage space used by API key",
    ["api_key_prefix"],
)

storage_quota_bytes = Gauge(
    "storage_quota_bytes",
    "Storage quota allocated to API key",
    ["api_key_prefix"],
)

storage_operations_total = Counter(
    "storage_operations_total",
    "Total number of storage operations",
    ["operation", "status"],  # operation: upload, download, delete
)

storage_operation_duration_seconds = Histogram(
    "storage_operation_duration_seconds",
    "Duration of storage operations",
    ["operation"],
    buckets=[0.1, 0.5, 1, 2, 5, 10, 30, 60, 120],
)


# ============================================================================
# Webhook Metrics
# ============================================================================

webhook_sent_total = Counter(
    "webhook_sent_total",
    "Total number of webhook notifications sent",
    ["event", "status"],  # status: success, failed
)

webhook_duration_seconds = Histogram(
    "webhook_duration_seconds",
    "Duration of webhook delivery attempts",
    ["event"],
    buckets=[0.1, 0.25, 0.5, 1, 2, 5, 10, 20],
)

webhook_retry_count = Counter(
    "webhook_retry_count",
    "Number of webhook retry attempts",
    ["event"],
)


# ============================================================================
# Database Metrics
# ============================================================================

db_connections_active = Gauge(
    "db_connections_active",
    "Number of active database connections",
)

db_connections_idle = Gauge(
    "db_connections_idle",
    "Number of idle database connections",
)

db_query_duration_seconds = Histogram(
    "db_query_duration_seconds",
    "Duration of database queries",
    ["operation"],  # operation: select, insert, update, delete
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5],
)


# ============================================================================
# Redis/Cache Metrics
# ============================================================================

cache_operations_total = Counter(
    "cache_operations_total",
    "Total number of cache operations",
    ["operation", "status"],  # operation: get, set, delete; status: hit, miss, error
)

cache_operation_duration_seconds = Histogram(
    "cache_operation_duration_seconds",
    "Duration of cache operations",
    ["operation"],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5],
)


# ============================================================================
# Celery Worker Metrics
# ============================================================================

celery_tasks_total = Counter(
    "celery_tasks_total",
    "Total number of Celery tasks",
    ["task_name", "status"],  # status: started, succeeded, failed, retried
)

celery_task_duration_seconds = Histogram(
    "celery_task_duration_seconds",
    "Duration of Celery task execution",
    ["task_name"],
    buckets=[1, 5, 10, 30, 60, 120, 300, 600, 1200, 1800, 3600],
)

celery_workers_active = Gauge(
    "celery_workers_active",
    "Number of active Celery workers",
)

celery_queue_length = Gauge(
    "celery_queue_length",
    "Number of tasks in Celery queue",
    ["queue_name"],
)


# ============================================================================
# API Key Metrics
# ============================================================================

api_key_requests_total = Counter(
    "api_key_requests_total",
    "Total number of requests per API key",
    ["api_key_prefix"],
)

api_key_rate_limit_exceeded = Counter(
    "api_key_rate_limit_exceeded",
    "Number of times rate limit was exceeded",
    ["api_key_prefix", "limit_type"],  # limit_type: hourly, daily
)

api_key_quota_exceeded = Counter(
    "api_key_quota_exceeded",
    "Number of times quota was exceeded",
    ["api_key_prefix", "quota_type"],  # quota_type: storage, jobs
)


# ============================================================================
# System Metrics (Application Level)
# ============================================================================

app_info = Gauge(
    "app_info",
    "Application information",
    ["version", "environment"],
)

app_uptime_seconds = Gauge(
    "app_uptime_seconds",
    "Application uptime in seconds",
)


# ============================================================================
# Helper Functions
# ============================================================================

def record_api_request(method: str, endpoint: str, status_code: int, duration: float):
    """Record API request metrics."""
    api_requests_total.labels(method=method, endpoint=endpoint, status=status_code).inc()
    api_request_duration_seconds.labels(method=method, endpoint=endpoint).observe(duration)


def record_job_created(api_key_prefix: str):
    """Record job creation metric."""
    jobs_created_total.labels(api_key_prefix=api_key_prefix).inc()


def record_job_completed(api_key_prefix: str, duration_seconds: float):
    """Record job completion metrics."""
    jobs_completed_total.labels(api_key_prefix=api_key_prefix).inc()
    job_processing_duration_seconds.labels(api_key_prefix=api_key_prefix).observe(duration_seconds)


def record_job_failed(api_key_prefix: str, error_type: str):
    """Record job failure metric."""
    jobs_failed_total.labels(api_key_prefix=api_key_prefix, error_type=error_type).inc()


def record_job_cancelled(api_key_prefix: str):
    """Record job cancellation metric."""
    jobs_cancelled_total.labels(api_key_prefix=api_key_prefix).inc()


def record_video_transcode(resolution: str, codec: str, duration: float, output_bytes: int):
    """Record video transcoding metrics."""
    video_transcode_duration_seconds.labels(resolution=resolution, codec=codec).observe(duration)
    video_transcoded_bytes.labels(resolution=resolution, codec=codec).inc(output_bytes)


def record_compression_ratio(ratio: float):
    """Record video compression ratio."""
    video_compression_ratio.observe(ratio)


def record_webhook_sent(event: str, success: bool, duration: float):
    """Record webhook delivery metrics."""
    status = "success" if success else "failed"
    webhook_sent_total.labels(event=event, status=status).inc()
    webhook_duration_seconds.labels(event=event).observe(duration)


def record_storage_operation(operation: str, success: bool, duration: float):
    """Record storage operation metrics."""
    status = "success" if success else "failed"
    storage_operations_total.labels(operation=operation, status=status).inc()
    storage_operation_duration_seconds.labels(operation=operation).observe(duration)


def update_storage_metrics(api_key_prefix: str, used_bytes: int, quota_bytes: int):
    """Update storage usage metrics."""
    storage_used_bytes.labels(api_key_prefix=api_key_prefix).set(used_bytes)
    storage_quota_bytes.labels(api_key_prefix=api_key_prefix).set(quota_bytes)


def update_queue_metrics(queued_count: int, processing_count: int):
    """Update job queue metrics."""
    jobs_queued.set(queued_count)
    jobs_processing.set(processing_count)


def update_job_status_metrics(status_counts: dict):
    """
    Update job status gauge metrics.

    Args:
        status_counts: Dictionary mapping status strings to counts
                      e.g., {"pending": 5, "processing": 2, "completed": 100}
    """
    for status, count in status_counts.items():
        jobs_total.labels(status=status).set(count)


def record_cache_operation(operation: str, hit: bool, duration: float):
    """Record cache operation metrics."""
    status = "hit" if hit else "miss"
    cache_operations_total.labels(operation=operation, status=status).inc()
    cache_operation_duration_seconds.labels(operation=operation).observe(duration)
