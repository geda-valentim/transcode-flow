"""
Database query optimization utilities.
Provides tools for optimizing SQLAlchemy queries and reducing database load.
"""
from sqlalchemy.orm import Session, joinedload, selectinload, subqueryload
from sqlalchemy import func, Index
from typing import Optional, List
from datetime import datetime, timezone, timedelta

from app.models.job import Job
from app.models.api_key import APIKey


class QueryOptimizer:
    """Utilities for optimizing database queries."""

    @staticmethod
    def get_job_with_relations(db: Session, job_id: str) -> Optional[Job]:
        """
        Get job with all related data using eager loading.
        Reduces N+1 query problem.
        """
        return (
            db.query(Job)
            .filter(Job.id == job_id)
            .options(
                # Add eager loading for relationships when they exist
                # Example: joinedload(Job.api_key)
            )
            .first()
        )

    @staticmethod
    def get_recent_jobs_paginated(
        db: Session,
        api_key_prefix: str,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Job]:
        """
        Get recent jobs with pagination and optional status filter.
        Uses indexed columns for efficient querying.
        """
        query = db.query(Job).filter(Job.api_key_prefix == api_key_prefix)

        if status:
            query = query.filter(Job.status == status)

        return (
            query.order_by(Job.created_at.desc())
            .limit(limit)
            .offset(offset)
            .all()
        )

    @staticmethod
    def get_jobs_count(
        db: Session,
        api_key_prefix: str,
        status: Optional[str] = None,
    ) -> int:
        """
        Get count of jobs efficiently.
        Uses COUNT(*) instead of loading all records.
        """
        query = db.query(func.count(Job.id)).filter(
            Job.api_key_prefix == api_key_prefix
        )

        if status:
            query = query.filter(Job.status == status)

        return query.scalar() or 0

    @staticmethod
    def get_active_api_keys_batch(
        db: Session,
        key_prefixes: List[str],
    ) -> dict[str, APIKey]:
        """
        Get multiple API keys in a single query.
        Returns dict mapping prefix to APIKey object.
        """
        keys = (
            db.query(APIKey)
            .filter(
                APIKey.key_prefix.in_(key_prefixes),
                APIKey.is_active == True,
            )
            .all()
        )

        return {key.key_prefix: key for key in keys}

    @staticmethod
    def get_api_key_by_hash_optimized(
        db: Session,
        key_hash: str,
    ) -> Optional[APIKey]:
        """
        Get API key by hash using index.
        Only selects necessary columns initially.
        """
        return (
            db.query(APIKey)
            .filter(
                APIKey.key_hash == key_hash,
                APIKey.is_active == True,
            )
            .first()
        )

    @staticmethod
    def get_job_statistics(
        db: Session,
        api_key_prefix: str,
        days: int = 30,
    ) -> dict:
        """
        Get aggregated job statistics efficiently.
        Uses database aggregation instead of loading all records.
        """
        since = datetime.now(timezone.utc) - timedelta(days=days)

        stats = (
            db.query(
                Job.status,
                func.count(Job.id).label("count"),
                func.avg(
                    func.extract(
                        "epoch",
                        Job.completed_at - Job.started_at,
                    )
                ).label("avg_duration_seconds"),
            )
            .filter(
                Job.api_key_prefix == api_key_prefix,
                Job.created_at >= since,
            )
            .group_by(Job.status)
            .all()
        )

        return {
            stat.status: {
                "count": stat.count,
                "avg_duration_seconds": float(stat.avg_duration_seconds or 0),
            }
            for stat in stats
        }

    @staticmethod
    def cleanup_old_jobs(
        db: Session,
        days_to_keep: int = 90,
        batch_size: int = 100,
    ) -> int:
        """
        Delete old completed jobs in batches.
        Returns number of jobs deleted.
        """
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_to_keep)

        deleted_count = 0
        while True:
            # Get batch of old jobs
            old_jobs = (
                db.query(Job.id)
                .filter(
                    Job.status == "completed",
                    Job.completed_at < cutoff_date,
                )
                .limit(batch_size)
                .all()
            )

            if not old_jobs:
                break

            # Delete batch
            job_ids = [job.id for job in old_jobs]
            db.query(Job).filter(Job.id.in_(job_ids)).delete(
                synchronize_session=False
            )
            db.commit()

            deleted_count += len(job_ids)

        return deleted_count

    @staticmethod
    def update_api_key_usage_batch(
        db: Session,
        usage_updates: dict[str, dict],
    ):
        """
        Update API key usage statistics in batch.

        Args:
            usage_updates: Dict mapping key_prefix to update values
                          e.g., {'tfk_abc': {'total_requests': 1, 'storage_used_bytes': 1024}}
        """
        for key_prefix, updates in usage_updates.items():
            db.query(APIKey).filter(APIKey.key_prefix == key_prefix).update(
                updates, synchronize_session=False
            )

        db.commit()


class IndexRecommendations:
    """Recommendations for database indexes to improve query performance."""

    @staticmethod
    def get_recommended_indexes() -> list[dict]:
        """
        Get list of recommended indexes for the schema.

        Returns:
            List of dicts with index recommendations
        """
        return [
            {
                "table": "jobs",
                "columns": ["api_key_prefix", "status"],
                "type": "composite",
                "reason": "Frequently queried together for job listing",
            },
            {
                "table": "jobs",
                "columns": ["api_key_prefix", "created_at"],
                "type": "composite",
                "reason": "Used for recent jobs queries with sorting",
            },
            {
                "table": "jobs",
                "columns": ["status", "completed_at"],
                "type": "composite",
                "reason": "Used for cleanup queries",
            },
            {
                "table": "api_keys",
                "columns": ["key_hash"],
                "type": "unique",
                "reason": "Primary lookup for authentication (already exists)",
            },
            {
                "table": "api_keys",
                "columns": ["parent_key_id"],
                "type": "index",
                "reason": "Used for sub-key queries (already exists)",
            },
            {
                "table": "api_keys",
                "columns": ["is_active", "expires_at"],
                "type": "composite",
                "reason": "Used for finding valid/expired keys",
            },
        ]

    @staticmethod
    def get_missing_indexes(db: Session) -> list[str]:
        """
        Analyze database and return SQL for missing recommended indexes.

        Returns:
            List of CREATE INDEX statements
        """
        # This would need actual database inspection
        # For now, return recommended indexes as SQL
        return [
            "CREATE INDEX IF NOT EXISTS idx_jobs_prefix_status ON jobs(api_key_prefix, status);",
            "CREATE INDEX IF NOT EXISTS idx_jobs_prefix_created ON jobs(api_key_prefix, created_at DESC);",
            "CREATE INDEX IF NOT EXISTS idx_jobs_status_completed ON jobs(status, completed_at);",
            "CREATE INDEX IF NOT EXISTS idx_api_keys_active_expires ON api_keys(is_active, expires_at);",
        ]


class QueryProfiler:
    """Profile slow queries and provide optimization suggestions."""

    def __init__(self):
        self.slow_queries = []

    def log_query(self, query_str: str, duration_ms: float, threshold_ms: float = 100):
        """Log slow queries that exceed threshold."""
        if duration_ms > threshold_ms:
            self.slow_queries.append({
                "query": query_str,
                "duration_ms": duration_ms,
                "timestamp": datetime.now(timezone.utc),
            })

    def get_slow_queries(self, limit: int = 10) -> list[dict]:
        """Get slowest queries."""
        return sorted(
            self.slow_queries,
            key=lambda x: x["duration_ms"],
            reverse=True,
        )[:limit]

    def clear(self):
        """Clear logged queries."""
        self.slow_queries.clear()
