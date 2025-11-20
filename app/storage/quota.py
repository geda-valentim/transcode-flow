"""
Storage Quota Management Service

Sprint 4: Storage & File Management

Manages storage quotas and usage monitoring for MinIO buckets.
Implements:
- Per-user storage quotas
- Bucket-level quotas
- Usage tracking and reporting
- Quota enforcement
- Storage analytics
"""
import logging
from datetime import datetime
from typing import Optional, Dict, List, Any
from dataclasses import dataclass
from minio import Minio
from minio.error import S3Error

logger = logging.getLogger(__name__)


@dataclass
class StorageQuota:
    """
    Storage quota configuration
    """
    entity_id: str  # user_id or bucket_name
    entity_type: str  # 'user' or 'bucket'
    quota_bytes: int
    used_bytes: int = 0
    file_count: int = 0
    warning_threshold: float = 0.8  # 80% threshold for warnings
    enabled: bool = True

    @property
    def quota_gb(self) -> float:
        """Get quota in GB"""
        return self.quota_bytes / (1024 ** 3)

    @property
    def used_gb(self) -> float:
        """Get used space in GB"""
        return self.used_bytes / (1024 ** 3)

    @property
    def usage_percentage(self) -> float:
        """Get usage percentage"""
        if self.quota_bytes == 0:
            return 0.0
        return (self.used_bytes / self.quota_bytes) * 100

    @property
    def available_bytes(self) -> int:
        """Get available space in bytes"""
        return max(0, self.quota_bytes - self.used_bytes)

    @property
    def is_exceeded(self) -> bool:
        """Check if quota is exceeded"""
        return self.used_bytes > self.quota_bytes

    @property
    def is_warning(self) -> bool:
        """Check if usage is above warning threshold"""
        return self.usage_percentage >= (self.warning_threshold * 100)


@dataclass
class StorageUsage:
    """
    Storage usage statistics
    """
    total_size: int
    file_count: int
    by_prefix: Dict[str, int]
    by_extension: Dict[str, int]
    largest_files: List[Dict[str, Any]]
    timestamp: datetime


class StorageQuotaManager:
    """
    Storage quota management service

    Features:
    - Per-user quota enforcement
    - Bucket-level quotas
    - Real-time usage tracking
    - Warning notifications
    - Storage analytics
    - Quota history tracking
    """

    def __init__(
        self,
        minio_client: Minio,
        bucket_name: str,
        default_quota_gb: float = 100.0
    ):
        """
        Initialize storage quota manager

        Args:
            minio_client: MinIO client instance
            bucket_name: Target bucket name
            default_quota_gb: Default quota in GB
        """
        self.client = minio_client
        self.bucket_name = bucket_name
        self.default_quota_bytes = int(default_quota_gb * (1024 ** 3))
        self.quotas: Dict[str, StorageQuota] = {}

        logger.info(
            f"StorageQuotaManager initialized for bucket '{bucket_name}' "
            f"with default quota {default_quota_gb}GB"
        )

    def set_quota(
        self,
        entity_id: str,
        entity_type: str,
        quota_gb: float,
        warning_threshold: float = 0.8
    ) -> StorageQuota:
        """
        Set storage quota for user or bucket

        Args:
            entity_id: User ID or bucket name
            entity_type: 'user' or 'bucket'
            quota_gb: Quota in GB
            warning_threshold: Warning threshold (0.0-1.0)

        Returns:
            StorageQuota object
        """
        quota_bytes = int(quota_gb * (1024 ** 3))

        quota = StorageQuota(
            entity_id=entity_id,
            entity_type=entity_type,
            quota_bytes=quota_bytes,
            warning_threshold=warning_threshold
        )

        self.quotas[entity_id] = quota

        logger.info(
            f"Set quota for {entity_type} '{entity_id}': {quota_gb}GB "
            f"(warning at {warning_threshold * 100}%)"
        )

        return quota

    def get_quota(self, entity_id: str) -> Optional[StorageQuota]:
        """
        Get quota for entity

        Args:
            entity_id: User ID or bucket name

        Returns:
            StorageQuota or None if not found
        """
        return self.quotas.get(entity_id)

    def calculate_usage(
        self,
        prefix: Optional[str] = None,
        recursive: bool = True
    ) -> StorageUsage:
        """
        Calculate storage usage for bucket or prefix

        Args:
            prefix: Optional prefix to filter objects
            recursive: Include nested objects

        Returns:
            StorageUsage statistics
        """
        try:
            total_size = 0
            file_count = 0
            by_prefix: Dict[str, int] = {}
            by_extension: Dict[str, int] = {}
            all_files: List[Dict[str, Any]] = []

            # List all objects
            objects = self.client.list_objects(
                self.bucket_name,
                prefix=prefix or "",
                recursive=recursive
            )

            for obj in objects:
                size = obj.size
                total_size += size
                file_count += 1

                # Track by prefix
                obj_prefix = obj.object_name.split('/')[0] if '/' in obj.object_name else 'root'
                by_prefix[obj_prefix] = by_prefix.get(obj_prefix, 0) + size

                # Track by extension
                extension = obj.object_name.split('.')[-1] if '.' in obj.object_name else 'none'
                by_extension[extension] = by_extension.get(extension, 0) + size

                # Track file info
                all_files.append({
                    'name': obj.object_name,
                    'size': size,
                    'last_modified': obj.last_modified
                })

            # Get top 10 largest files
            largest_files = sorted(all_files, key=lambda x: x['size'], reverse=True)[:10]

            usage = StorageUsage(
                total_size=total_size,
                file_count=file_count,
                by_prefix=by_prefix,
                by_extension=by_extension,
                largest_files=largest_files,
                timestamp=datetime.utcnow()
            )

            logger.info(
                f"Calculated usage for bucket '{self.bucket_name}': "
                f"{total_size / (1024**3):.2f}GB, {file_count} files"
            )

            return usage

        except S3Error as e:
            logger.error(f"Failed to calculate usage: {e}")
            raise

    def update_quota_usage(self, entity_id: str, prefix: Optional[str] = None) -> StorageQuota:
        """
        Update quota usage statistics

        Args:
            entity_id: User ID or bucket name
            prefix: Optional prefix to filter (e.g., 'users/{user_id}/')

        Returns:
            Updated StorageQuota
        """
        quota = self.get_quota(entity_id)
        if not quota:
            # Create default quota
            quota = self.set_quota(
                entity_id,
                'user',
                self.default_quota_bytes / (1024 ** 3)
            )

        # Calculate usage
        usage = self.calculate_usage(prefix=prefix)

        # Update quota
        quota.used_bytes = usage.total_size
        quota.file_count = usage.file_count

        logger.info(
            f"Updated quota for '{entity_id}': "
            f"{quota.usage_percentage:.1f}% used ({quota.used_gb:.2f}GB / {quota.quota_gb:.2f}GB)"
        )

        return quota

    def check_quota(
        self,
        entity_id: str,
        additional_bytes: int = 0
    ) -> Dict[str, Any]:
        """
        Check if quota allows additional storage

        Args:
            entity_id: User ID or bucket name
            additional_bytes: Bytes to be added

        Returns:
            Dictionary with quota check results
        """
        quota = self.get_quota(entity_id)
        if not quota:
            quota = self.set_quota(
                entity_id,
                'user',
                self.default_quota_bytes / (1024 ** 3)
            )

        would_use = quota.used_bytes + additional_bytes
        would_exceed = would_use > quota.quota_bytes

        return {
            'entity_id': entity_id,
            'quota_gb': quota.quota_gb,
            'used_gb': quota.used_gb,
            'available_gb': quota.available_bytes / (1024 ** 3),
            'usage_percentage': quota.usage_percentage,
            'additional_gb': additional_bytes / (1024 ** 3),
            'would_use_gb': would_use / (1024 ** 3),
            'would_exceed': would_exceed,
            'is_warning': quota.is_warning,
            'allowed': not would_exceed
        }

    def enforce_quota(
        self,
        entity_id: str,
        file_size: int
    ) -> bool:
        """
        Enforce quota before allowing file upload

        Args:
            entity_id: User ID or bucket name
            file_size: Size of file to upload

        Returns:
            True if upload is allowed, False otherwise

        Raises:
            QuotaExceededError: If quota would be exceeded
        """
        check = self.check_quota(entity_id, file_size)

        if check['would_exceed']:
            logger.warning(
                f"Quota exceeded for '{entity_id}': "
                f"would use {check['would_use_gb']:.2f}GB / {check['quota_gb']:.2f}GB"
            )
            raise QuotaExceededError(
                f"Storage quota exceeded. "
                f"Used: {check['used_gb']:.2f}GB, "
                f"Quota: {check['quota_gb']:.2f}GB, "
                f"File size: {check['additional_gb']:.2f}GB"
            )

        if check['is_warning']:
            logger.warning(
                f"Quota warning for '{entity_id}': "
                f"{check['usage_percentage']:.1f}% used"
            )

        return True

    def get_usage_report(
        self,
        entity_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get detailed usage report

        Args:
            entity_id: Optional entity ID to filter

        Returns:
            Usage report dictionary
        """
        if entity_id:
            quota = self.get_quota(entity_id)
            if not quota:
                return {'error': f"No quota found for '{entity_id}'"}

            return {
                'entity_id': entity_id,
                'entity_type': quota.entity_type,
                'quota': {
                    'total_gb': quota.quota_gb,
                    'used_gb': quota.used_gb,
                    'available_gb': quota.available_bytes / (1024 ** 3),
                    'usage_percentage': quota.usage_percentage,
                    'file_count': quota.file_count,
                },
                'status': {
                    'is_exceeded': quota.is_exceeded,
                    'is_warning': quota.is_warning,
                    'enabled': quota.enabled,
                },
                'thresholds': {
                    'warning_threshold': quota.warning_threshold * 100,
                }
            }
        else:
            # Global report
            total_quotas = len(self.quotas)
            exceeded = sum(1 for q in self.quotas.values() if q.is_exceeded)
            warnings = sum(1 for q in self.quotas.values() if q.is_warning)

            return {
                'total_entities': total_quotas,
                'exceeded_count': exceeded,
                'warning_count': warnings,
                'quotas': [
                    {
                        'entity_id': q.entity_id,
                        'type': q.entity_type,
                        'used_gb': q.used_gb,
                        'quota_gb': q.quota_gb,
                        'usage_percentage': q.usage_percentage,
                        'status': 'exceeded' if q.is_exceeded else 'warning' if q.is_warning else 'ok'
                    }
                    for q in self.quotas.values()
                ]
            }

    def cleanup_over_quota(
        self,
        entity_id: str,
        strategy: str = 'oldest'
    ) -> Dict[str, Any]:
        """
        Clean up files to get under quota

        Args:
            entity_id: Entity to clean up
            strategy: 'oldest' or 'largest'

        Returns:
            Cleanup results
        """
        quota = self.get_quota(entity_id)
        if not quota or not quota.is_exceeded:
            return {'cleaned': False, 'reason': 'Not over quota'}

        # Calculate how much to free
        bytes_to_free = quota.used_bytes - quota.quota_bytes

        logger.info(
            f"Cleaning up {bytes_to_free / (1024**3):.2f}GB for '{entity_id}' "
            f"using strategy '{strategy}'"
        )

        # Get usage details
        prefix = f"users/{entity_id}/" if quota.entity_type == 'user' else None
        usage = self.calculate_usage(prefix=prefix)

        # Sort files by strategy
        if strategy == 'oldest':
            files_to_delete = sorted(
                usage.largest_files,
                key=lambda x: x['last_modified']
            )
        else:  # largest
            files_to_delete = usage.largest_files

        deleted_files = []
        freed_bytes = 0

        for file_info in files_to_delete:
            if freed_bytes >= bytes_to_free:
                break

            try:
                self.client.remove_object(self.bucket_name, file_info['name'])
                deleted_files.append(file_info['name'])
                freed_bytes += file_info['size']
                logger.info(f"Deleted: {file_info['name']} ({file_info['size'] / (1024**2):.2f}MB)")
            except S3Error as e:
                logger.error(f"Failed to delete {file_info['name']}: {e}")

        # Update quota
        self.update_quota_usage(entity_id, prefix=prefix)

        return {
            'cleaned': True,
            'strategy': strategy,
            'bytes_freed': freed_bytes,
            'files_deleted': len(deleted_files),
            'deleted_files': deleted_files
        }


class QuotaExceededError(Exception):
    """Raised when storage quota is exceeded"""
    pass
