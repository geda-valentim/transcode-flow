"""
Job export endpoints.
Handles exporting job data to CSV and JSON formats.
"""
from typing import Optional
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
import csv
import io
import json as json_lib

from app.db import get_db
from app.models.job import Job, JobStatus
from app.models.api_key import APIKey
from app.core.security import get_api_key

router = APIRouter()


@router.get("/export")
async def export_jobs(
    format: str = Query("json", description="Export format: json or csv"),
    search: Optional[str] = Query(None, description="Search term for filename matching"),
    status: Optional[str] = Query(None, description="Filter by job status"),
    from_date: Optional[datetime] = Query(None, description="Filter jobs created from this date"),
    to_date: Optional[datetime] = Query(None, description="Filter jobs created until this date"),
    limit: int = Query(1000, ge=1, le=10000, description="Maximum number of jobs to export"),
    api_key: APIKey = Depends(get_api_key),
    db: Session = Depends(get_db),
):
    """
    Export jobs to CSV or JSON format.

    Supports:
    - JSON format: Returns array of job objects
    - CSV format: Returns spreadsheet-compatible CSV file
    - Filtering by search, status, date range
    - Maximum 10,000 jobs per export

    Returns file download with appropriate Content-Type and filename.
    """
    # Validate format
    if format not in ["json", "csv"]:
        raise HTTPException(
            status_code=400,
            detail="Invalid format. Valid values: json, csv"
        )

    # Build query with filters (reuse search endpoint logic)
    query = db.query(Job).filter(Job.api_key_id == api_key.id)

    if search:
        query = query.filter(Job.source_filename.ilike(f"%{search}%"))

    if status:
        try:
            status_enum = JobStatus(status)
            query = query.filter(Job.status == status_enum)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status: {status}. Valid values: {[s.value for s in JobStatus]}"
            )

    if from_date:
        query = query.filter(Job.created_at >= from_date)
    if to_date:
        query = query.filter(Job.created_at <= to_date)

    # Order by created_at descending and limit
    query = query.order_by(Job.created_at.desc()).limit(limit)
    jobs = query.all()

    # Generate timestamp for filename
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    if format == "json":
        # Export as JSON
        jobs_data = [
            {
                "job_id": job.job_id,
                "status": job.status.value,
                "priority": job.priority,
                "source_filename": job.source_filename,
                "source_size_bytes": job.source_size_bytes,
                "source_duration_seconds": float(job.source_duration_seconds) if job.source_duration_seconds else None,
                "source_resolution": job.source_resolution,
                "source_codec": job.source_codec,
                "source_bitrate": job.source_bitrate,
                "source_fps": float(job.source_fps) if job.source_fps else None,
                "target_resolutions": job.target_resolutions,
                "enable_hls": job.enable_hls,
                "enable_audio_extraction": job.enable_audio_extraction,
                "enable_transcription": job.enable_transcription,
                "output_path": job.output_path,
                "output_formats": job.output_formats,
                "hls_manifest_url": job.hls_manifest_url,
                "audio_file_url": job.audio_file_url,
                "transcription_url": job.transcription_url,
                "thumbnail_url": job.thumbnail_url,
                "processing_started_at": job.processing_started_at.isoformat() if job.processing_started_at else None,
                "processing_completed_at": job.processing_completed_at.isoformat() if job.processing_completed_at else None,
                "processing_duration_seconds": job.processing_duration_seconds,
                "compression_ratio": float(job.compression_ratio) if job.compression_ratio else None,
                "output_total_size_bytes": job.output_total_size_bytes,
                "error_message": job.error_message,
                "retry_count": job.retry_count,
                "created_at": job.created_at.isoformat() if job.created_at else None,
                "updated_at": job.updated_at.isoformat() if job.updated_at else None
            }
            for job in jobs
        ]

        # Create JSON string
        json_content = json_lib.dumps(jobs_data, indent=2)

        # Return as streaming response
        return StreamingResponse(
            io.BytesIO(json_content.encode('utf-8')),
            media_type="application/json",
            headers={
                "Content-Disposition": f"attachment; filename=jobs_export_{timestamp}.json"
            }
        )

    elif format == "csv":
        # Export as CSV
        output = io.StringIO()

        # Define CSV columns
        fieldnames = [
            "job_id", "status", "priority", "source_filename",
            "source_size_bytes", "source_duration_seconds", "source_resolution",
            "source_codec", "source_bitrate", "source_fps",
            "target_resolutions", "enable_hls", "enable_audio_extraction",
            "enable_transcription", "output_path", "hls_manifest_url",
            "audio_file_url", "transcription_url", "thumbnail_url",
            "processing_started_at", "processing_completed_at",
            "processing_duration_seconds", "compression_ratio",
            "output_total_size_bytes", "error_message", "retry_count",
            "created_at", "updated_at"
        ]

        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()

        for job in jobs:
            writer.writerow({
                "job_id": job.job_id,
                "status": job.status.value,
                "priority": job.priority,
                "source_filename": job.source_filename,
                "source_size_bytes": job.source_size_bytes,
                "source_duration_seconds": float(job.source_duration_seconds) if job.source_duration_seconds else "",
                "source_resolution": job.source_resolution or "",
                "source_codec": job.source_codec or "",
                "source_bitrate": job.source_bitrate or "",
                "source_fps": float(job.source_fps) if job.source_fps else "",
                "target_resolutions": json_lib.dumps(job.target_resolutions) if job.target_resolutions else "",
                "enable_hls": job.enable_hls,
                "enable_audio_extraction": job.enable_audio_extraction,
                "enable_transcription": job.enable_transcription,
                "output_path": job.output_path or "",
                "hls_manifest_url": job.hls_manifest_url or "",
                "audio_file_url": job.audio_file_url or "",
                "transcription_url": job.transcription_url or "",
                "thumbnail_url": job.thumbnail_url or "",
                "processing_started_at": job.processing_started_at.isoformat() if job.processing_started_at else "",
                "processing_completed_at": job.processing_completed_at.isoformat() if job.processing_completed_at else "",
                "processing_duration_seconds": job.processing_duration_seconds or "",
                "compression_ratio": float(job.compression_ratio) if job.compression_ratio else "",
                "output_total_size_bytes": job.output_total_size_bytes or "",
                "error_message": job.error_message or "",
                "retry_count": job.retry_count,
                "created_at": job.created_at.isoformat() if job.created_at else "",
                "updated_at": job.updated_at.isoformat() if job.updated_at else ""
            })

        # Return CSV as streaming response
        csv_content = output.getvalue()
        return StreamingResponse(
            io.BytesIO(csv_content.encode('utf-8')),
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename=jobs_export_{timestamp}.csv"
            }
        )
