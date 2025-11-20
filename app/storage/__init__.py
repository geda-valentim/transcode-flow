"""
Storage Management Module

Sprint 4: Storage & File Management

This module provides comprehensive storage management for MinIO:
- Lifecycle policies for automatic file cleanup
- Storage quota management and enforcement
- Presigned URL generation for secure file access
- Duplicate detection using file hashing
- Storage cleanup services
"""

from .lifecycle import LifecyclePolicyManager, RetentionPolicy, create_default_lifecycle_policies
from .quota import StorageQuotaManager, StorageQuota, StorageUsage, QuotaExceededError
from .presigned import PresignedURLGenerator, PresignedURL
from .deduplication import DuplicateDetector, FileHash, DuplicateFile
from .cleanup import StorageCleanupService, CleanupRule, CleanupResult

__all__ = [
    # Lifecycle management
    'LifecyclePolicyManager',
    'RetentionPolicy',
    'create_default_lifecycle_policies',

    # Quota management
    'StorageQuotaManager',
    'StorageQuota',
    'StorageUsage',
    'QuotaExceededError',

    # Presigned URLs
    'PresignedURLGenerator',
    'PresignedURL',

    # Deduplication
    'DuplicateDetector',
    'FileHash',
    'DuplicateFile',

    # Cleanup
    'StorageCleanupService',
    'CleanupRule',
    'CleanupResult',
]
