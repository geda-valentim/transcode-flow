"""
Metrics module for application monitoring.

This module provides Prometheus metrics collection and helper functions.
"""
from app.metrics.prometheus import (
    # API Metrics
    api_requests_total,
    api_request_duration_seconds,
    api_requests_in_progress,

    # Job Metrics
    jobs_total,
    jobs_created_total,
    jobs_completed_total,
    jobs_failed_total,
    jobs_cancelled_total,
    jobs_queued,
    jobs_processing,
    job_processing_duration_seconds,
    job_queue_time_seconds,
    job_retry_count,

    # Video Processing Metrics
    video_transcode_duration_seconds,
    video_transcoded_bytes,
    video_compression_ratio,
    video_source_duration_seconds,
    video_source_size_bytes,
    audio_extraction_duration_seconds,
    transcription_duration_seconds,
    transcription_word_count,
    thumbnail_generation_duration_seconds,

    # Storage Metrics
    storage_used_bytes,
    storage_quota_bytes,
    storage_operations_total,
    storage_operation_duration_seconds,

    # Webhook Metrics
    webhook_sent_total,
    webhook_duration_seconds,
    webhook_retry_count,

    # Database Metrics
    db_connections_active,
    db_connections_idle,
    db_query_duration_seconds,

    # Cache Metrics
    cache_operations_total,
    cache_operation_duration_seconds,

    # Celery Metrics
    celery_tasks_total,
    celery_task_duration_seconds,
    celery_workers_active,
    celery_queue_length,

    # API Key Metrics
    api_key_requests_total,
    api_key_rate_limit_exceeded,
    api_key_quota_exceeded,

    # System Metrics
    app_info,
    app_uptime_seconds,

    # Helper Functions
    record_api_request,
    record_job_created,
    record_job_completed,
    record_job_failed,
    record_job_cancelled,
    record_video_transcode,
    record_compression_ratio,
    record_webhook_sent,
    record_storage_operation,
    update_storage_metrics,
    update_queue_metrics,
    update_job_status_metrics,
    record_cache_operation,
)

__all__ = [
    # API Metrics
    "api_requests_total",
    "api_request_duration_seconds",
    "api_requests_in_progress",

    # Job Metrics
    "jobs_total",
    "jobs_created_total",
    "jobs_completed_total",
    "jobs_failed_total",
    "jobs_cancelled_total",
    "jobs_queued",
    "jobs_processing",
    "job_processing_duration_seconds",
    "job_queue_time_seconds",
    "job_retry_count",

    # Video Processing Metrics
    "video_transcode_duration_seconds",
    "video_transcoded_bytes",
    "video_compression_ratio",
    "video_source_duration_seconds",
    "video_source_size_bytes",
    "audio_extraction_duration_seconds",
    "transcription_duration_seconds",
    "transcription_word_count",
    "thumbnail_generation_duration_seconds",

    # Storage Metrics
    "storage_used_bytes",
    "storage_quota_bytes",
    "storage_operations_total",
    "storage_operation_duration_seconds",

    # Webhook Metrics
    "webhook_sent_total",
    "webhook_duration_seconds",
    "webhook_retry_count",

    # Database Metrics
    "db_connections_active",
    "db_connections_idle",
    "db_query_duration_seconds",

    # Cache Metrics
    "cache_operations_total",
    "cache_operation_duration_seconds",

    # Celery Metrics
    "celery_tasks_total",
    "celery_task_duration_seconds",
    "celery_workers_active",
    "celery_queue_length",

    # API Key Metrics
    "api_key_requests_total",
    "api_key_rate_limit_exceeded",
    "api_key_quota_exceeded",

    # System Metrics
    "app_info",
    "app_uptime_seconds",

    # Helper Functions
    "record_api_request",
    "record_job_created",
    "record_job_completed",
    "record_job_failed",
    "record_job_cancelled",
    "record_video_transcode",
    "record_compression_ratio",
    "record_webhook_sent",
    "record_storage_operation",
    "update_storage_metrics",
    "update_queue_metrics",
    "update_job_status_metrics",
    "record_cache_operation",
]
