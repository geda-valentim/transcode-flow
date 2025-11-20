"""
Storage Cleanup Service

Sprint 4: Storage & File Management

Provides automated cleanup of temporary files, failed jobs, and old outputs.
Implements:
- Age-based file deletion
- Prefix-based cleanup (temp/, failed/)
- Failed job cleanup
- Orphaned file detection
- Cleanup scheduling and reporting
"""
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from minio import Minio
from minio.error import S3Error

logger = logging.getLogger(__name__)


@dataclass
class CleanupRule:
    """
    Cleanup rule configuration
    """
    name: str
    prefix: str
    max_age_days: int
    enabled: bool = True
    description: str = ""


@dataclass
class CleanupResult:
    """
    Cleanup operation result
    """
    rule_name: str
    files_scanned: int
    files_deleted: int
    space_freed_bytes: int
    errors: List[str]
    duration_seconds: float

    @property
    def space_freed_mb(self) -> float:
        """Get freed space in MB"""
        return self.space_freed_bytes / (1024 ** 2)

    @property
    def space_freed_gb(self) -> float:
        """Get freed space in GB"""
        return self.space_freed_bytes / (1024 ** 3)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'rule_name': self.rule_name,
            'files_scanned': self.files_scanned,
            'files_deleted': self.files_deleted,
            'space_freed_bytes': self.space_freed_bytes,
            'space_freed_mb': round(self.space_freed_mb, 2),
            'space_freed_gb': round(self.space_freed_gb, 4),
            'errors': self.errors,
            'duration_seconds': round(self.duration_seconds, 2)
        }


class StorageCleanupService:
    """
    Storage cleanup service for MinIO

    Features:
    - Age-based file deletion
    - Multiple cleanup rules
    - Dry-run mode for testing
    - Detailed cleanup reports
    - Error handling and logging
    """

    # Default cleanup rules
    DEFAULT_RULES = [
        CleanupRule(
            name="cleanup-temp-files",
            prefix="temp/",
            max_age_days=1,
            description="Remove temporary files older than 1 day"
        ),
        CleanupRule(
            name="cleanup-failed-jobs",
            prefix="failed/",
            max_age_days=7,
            description="Remove failed job files older than 7 days"
        ),
        CleanupRule(
            name="cleanup-old-thumbnails",
            prefix="thumbnails/",
            max_age_days=30,
            description="Remove thumbnails older than 30 days"
        ),
    ]

    def __init__(
        self,
        minio_client: Minio,
        bucket_name: str,
        custom_rules: Optional[List[CleanupRule]] = None
    ):
        """
        Initialize storage cleanup service

        Args:
            minio_client: MinIO client instance
            bucket_name: Target bucket name
            custom_rules: Optional custom cleanup rules
        """
        self.client = minio_client
        self.bucket_name = bucket_name
        self.rules = custom_rules or self.DEFAULT_RULES

        logger.info(
            f"StorageCleanupService initialized for bucket '{bucket_name}' "
            f"with {len(self.rules)} rules"
        )

    def is_file_expired(
        self,
        last_modified: datetime,
        max_age_days: int
    ) -> bool:
        """
        Check if a file has exceeded its max age

        Args:
            last_modified: File's last modified timestamp
            max_age_days: Maximum age in days

        Returns:
            True if file is expired, False otherwise
        """
        age = datetime.utcnow() - last_modified.replace(tzinfo=None)
        return age > timedelta(days=max_age_days)

    def cleanup_by_rule(
        self,
        rule: CleanupRule,
        dry_run: bool = True
    ) -> CleanupResult:
        """
        Perform cleanup based on a single rule

        Args:
            rule: CleanupRule to apply
            dry_run: If True, only simulate cleanup

        Returns:
            CleanupResult with operation details
        """
        start_time = datetime.utcnow()
        logger.info(
            f"Starting cleanup: {rule.name} "
            f"(prefix={rule.prefix}, max_age={rule.max_age_days}d, dry_run={dry_run})"
        )

        files_scanned = 0
        files_deleted = 0
        space_freed = 0
        errors = []

        try:
            # List all objects matching prefix
            objects = self.client.list_objects(
                self.bucket_name,
                prefix=rule.prefix,
                recursive=True
            )

            for obj in objects:
                files_scanned += 1

                # Check if file is expired
                if self.is_file_expired(obj.last_modified, rule.max_age_days):
                    logger.debug(
                        f"Expired file: {obj.object_name} "
                        f"(age: {(datetime.utcnow() - obj.last_modified.replace(tzinfo=None)).days}d)"
                    )

                    if not dry_run:
                        try:
                            self.client.remove_object(self.bucket_name, obj.object_name)
                            logger.info(f"Deleted: {obj.object_name}")
                        except S3Error as e:
                            error_msg = f"Failed to delete {obj.object_name}: {e}"
                            logger.error(error_msg)
                            errors.append(error_msg)
                            continue

                    files_deleted += 1
                    space_freed += obj.size

        except S3Error as e:
            error_msg = f"Failed to list objects: {e}"
            logger.error(error_msg)
            errors.append(error_msg)

        duration = (datetime.utcnow() - start_time).total_seconds()

        result = CleanupResult(
            rule_name=rule.name,
            files_scanned=files_scanned,
            files_deleted=files_deleted,
            space_freed_bytes=space_freed,
            errors=errors,
            duration_seconds=duration
        )

        logger.info(
            f"Cleanup completed: {rule.name} - "
            f"{files_deleted}/{files_scanned} files deleted, "
            f"{result.space_freed_mb:.2f}MB freed, "
            f"{duration:.2f}s"
        )

        return result

    def cleanup_all(
        self,
        dry_run: bool = True
    ) -> List[CleanupResult]:
        """
        Run all cleanup rules

        Args:
            dry_run: If True, only simulate cleanup

        Returns:
            List of CleanupResult for each rule
        """
        logger.info(f"Starting full cleanup (dry_run={dry_run})...")

        results = []

        for rule in self.rules:
            if not rule.enabled:
                logger.info(f"Skipping disabled rule: {rule.name}")
                continue

            result = self.cleanup_by_rule(rule, dry_run=dry_run)
            results.append(result)

        total_files = sum(r.files_deleted for r in results)
        total_space = sum(r.space_freed_bytes for r in results)

        logger.info(
            f"Full cleanup completed: {total_files} files deleted, "
            f"{total_space / (1024**3):.4f}GB freed"
        )

        return results

    def cleanup_old_jobs(
        self,
        max_age_days: int = 30,
        dry_run: bool = True
    ) -> CleanupResult:
        """
        Clean up old job outputs

        Args:
            max_age_days: Maximum age for job outputs
            dry_run: If True, only simulate cleanup

        Returns:
            CleanupResult with operation details
        """
        rule = CleanupRule(
            name="cleanup-old-jobs",
            prefix="jobs/",
            max_age_days=max_age_days,
            description=f"Remove job outputs older than {max_age_days} days"
        )

        return self.cleanup_by_rule(rule, dry_run=dry_run)

    def cleanup_failed_jobs(
        self,
        job_ids: List[str],
        dry_run: bool = True
    ) -> Dict[str, Any]:
        """
        Clean up specific failed jobs

        Args:
            job_ids: List of job IDs to clean up
            dry_run: If True, only simulate cleanup

        Returns:
            Dictionary with cleanup results
        """
        logger.info(f"Cleaning up {len(job_ids)} failed jobs (dry_run={dry_run})...")

        files_deleted = 0
        space_freed = 0
        errors = []

        for job_id in job_ids:
            prefix = f"jobs/{job_id}/"

            try:
                objects = self.client.list_objects(
                    self.bucket_name,
                    prefix=prefix,
                    recursive=True
                )

                for obj in objects:
                    if not dry_run:
                        try:
                            self.client.remove_object(self.bucket_name, obj.object_name)
                            logger.info(f"Deleted: {obj.object_name}")
                        except S3Error as e:
                            error_msg = f"Failed to delete {obj.object_name}: {e}"
                            logger.error(error_msg)
                            errors.append(error_msg)
                            continue

                    files_deleted += 1
                    space_freed += obj.size

            except S3Error as e:
                error_msg = f"Failed to list job {job_id}: {e}"
                logger.error(error_msg)
                errors.append(error_msg)

        return {
            'jobs_cleaned': len(job_ids),
            'files_deleted': files_deleted,
            'space_freed_bytes': space_freed,
            'space_freed_mb': round(space_freed / (1024 ** 2), 2),
            'errors': errors
        }

    def find_orphaned_files(
        self,
        valid_job_ids: List[str]
    ) -> List[str]:
        """
        Find files in jobs/ that don't have corresponding database entries

        Args:
            valid_job_ids: List of valid job IDs from database

        Returns:
            List of orphaned object names
        """
        logger.info("Scanning for orphaned files...")

        orphaned = []
        valid_prefixes = {f"jobs/{job_id}/" for job_id in valid_job_ids}

        try:
            objects = self.client.list_objects(
                self.bucket_name,
                prefix="jobs/",
                recursive=True
            )

            for obj in objects:
                # Extract job ID from path
                parts = obj.object_name.split('/')
                if len(parts) >= 2:
                    job_prefix = f"jobs/{parts[1]}/"

                    if job_prefix not in valid_prefixes:
                        orphaned.append(obj.object_name)

        except S3Error as e:
            logger.error(f"Failed to find orphaned files: {e}")

        logger.info(f"Found {len(orphaned)} orphaned files")
        return orphaned

    def cleanup_orphaned_files(
        self,
        orphaned_files: List[str],
        dry_run: bool = True
    ) -> Dict[str, Any]:
        """
        Clean up orphaned files

        Args:
            orphaned_files: List of object names to delete
            dry_run: If True, only simulate cleanup

        Returns:
            Dictionary with cleanup results
        """
        logger.info(f"Cleaning up {len(orphaned_files)} orphaned files (dry_run={dry_run})...")

        files_deleted = 0
        space_freed = 0
        errors = []

        for object_name in orphaned_files:
            try:
                # Get file size first
                stat = self.client.stat_object(self.bucket_name, object_name)

                if not dry_run:
                    self.client.remove_object(self.bucket_name, object_name)
                    logger.info(f"Deleted orphaned file: {object_name}")

                files_deleted += 1
                space_freed += stat.size

            except S3Error as e:
                error_msg = f"Failed to delete {object_name}: {e}"
                logger.error(error_msg)
                errors.append(error_msg)

        return {
            'files_deleted': files_deleted,
            'space_freed_bytes': space_freed,
            'space_freed_mb': round(space_freed / (1024 ** 2), 2),
            'errors': errors
        }

    def get_cleanup_report(
        self,
        results: List[CleanupResult]
    ) -> str:
        """
        Generate human-readable cleanup report

        Args:
            results: List of CleanupResult objects

        Returns:
            Formatted report string
        """
        report = []
        report.append("=" * 60)
        report.append("STORAGE CLEANUP REPORT")
        report.append("=" * 60)

        total_scanned = sum(r.files_scanned for r in results)
        total_deleted = sum(r.files_deleted for r in results)
        total_space = sum(r.space_freed_bytes for r in results)
        total_errors = sum(len(r.errors) for r in results)

        report.append(f"Total files scanned: {total_scanned}")
        report.append(f"Total files deleted: {total_deleted}")
        report.append(f"Total space freed: {total_space / (1024**3):.4f} GB")
        report.append(f"Total errors: {total_errors}")
        report.append("=" * 60)

        for result in results:
            report.append(f"\nRule: {result.rule_name}")
            report.append(f"  Files scanned: {result.files_scanned}")
            report.append(f"  Files deleted: {result.files_deleted}")
            report.append(f"  Space freed: {result.space_freed_mb:.2f} MB")
            report.append(f"  Duration: {result.duration_seconds:.2f}s")

            if result.errors:
                report.append(f"  Errors: {len(result.errors)}")
                for error in result.errors[:5]:  # Show first 5 errors
                    report.append(f"    - {error}")

        return "\n".join(report)
