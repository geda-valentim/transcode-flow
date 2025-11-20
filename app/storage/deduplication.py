"""
Duplicate Detection Service

Sprint 4: Storage & File Management

Detects duplicate files using SHA-256 hashing to avoid storing the same video twice.
Implements:
- SHA-256 file hashing
- Duplicate detection via hash comparison
- Database tracking of file hashes
- Storage savings reporting
"""
import hashlib
import logging
from typing import Optional, Dict, List, Any
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from minio import Minio
from minio.error import S3Error

logger = logging.getLogger(__name__)


@dataclass
class FileHash:
    """
    File hash information
    """
    object_name: str
    hash_value: str
    algorithm: str
    size_bytes: int
    created_at: datetime

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'object_name': self.object_name,
            'hash': self.hash_value,
            'algorithm': self.algorithm,
            'size_bytes': self.size_bytes,
            'size_mb': round(self.size_bytes / (1024 ** 2), 2),
            'created_at': self.created_at.isoformat()
        }


@dataclass
class DuplicateFile:
    """
    Duplicate file information
    """
    original: FileHash
    duplicates: List[FileHash]
    total_duplicates: int
    wasted_space_bytes: int

    @property
    def wasted_space_mb(self) -> float:
        """Get wasted space in MB"""
        return self.wasted_space_bytes / (1024 ** 2)

    @property
    def wasted_space_gb(self) -> float:
        """Get wasted space in GB"""
        return self.wasted_space_bytes / (1024 ** 3)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'original': self.original.to_dict(),
            'duplicates': [d.to_dict() for d in self.duplicates],
            'total_duplicates': self.total_duplicates,
            'wasted_space_bytes': self.wasted_space_bytes,
            'wasted_space_mb': round(self.wasted_space_mb, 2),
            'wasted_space_gb': round(self.wasted_space_gb, 4)
        }


class DuplicateDetector:
    """
    Duplicate file detection service

    Features:
    - SHA-256 hashing for file comparison
    - In-memory hash database
    - Duplicate detection before upload
    - Storage savings calculation
    - Batch duplicate scanning
    """

    def __init__(
        self,
        minio_client: Minio,
        bucket_name: str,
        hash_algorithm: str = 'sha256'
    ):
        """
        Initialize duplicate detector

        Args:
            minio_client: MinIO client instance
            bucket_name: Target bucket name
            hash_algorithm: Hashing algorithm (default: sha256)
        """
        self.client = minio_client
        self.bucket_name = bucket_name
        self.hash_algorithm = hash_algorithm
        self.hash_db: Dict[str, List[FileHash]] = {}  # hash -> list of files

        logger.info(
            f"DuplicateDetector initialized for bucket '{bucket_name}' "
            f"using {hash_algorithm}"
        )

    def calculate_file_hash(
        self,
        file_path: str,
        chunk_size: int = 8192
    ) -> str:
        """
        Calculate hash of a local file

        Args:
            file_path: Path to file
            chunk_size: Read chunk size in bytes

        Returns:
            Hex digest of file hash
        """
        hasher = hashlib.sha256()

        with open(file_path, 'rb') as f:
            while chunk := f.read(chunk_size):
                hasher.update(chunk)

        hash_value = hasher.hexdigest()
        logger.debug(f"Calculated {self.hash_algorithm} for '{file_path}': {hash_value}")

        return hash_value

    def calculate_object_hash(
        self,
        object_name: str,
        chunk_size: int = 8192
    ) -> str:
        """
        Calculate hash of a MinIO object

        Args:
            object_name: Object key in bucket
            chunk_size: Read chunk size in bytes

        Returns:
            Hex digest of object hash
        """
        hasher = hashlib.sha256()

        try:
            # Stream object data
            response = self.client.get_object(self.bucket_name, object_name)

            for chunk in response.stream(chunk_size):
                hasher.update(chunk)

            response.close()
            response.release_conn()

            hash_value = hasher.hexdigest()
            logger.debug(f"Calculated {self.hash_algorithm} for '{object_name}': {hash_value}")

            return hash_value

        except S3Error as e:
            logger.error(f"Failed to calculate hash for '{object_name}': {e}")
            raise

    def add_to_hash_db(self, file_hash: FileHash) -> None:
        """
        Add file hash to in-memory database

        Args:
            file_hash: FileHash object to add
        """
        if file_hash.hash_value not in self.hash_db:
            self.hash_db[file_hash.hash_value] = []

        self.hash_db[file_hash.hash_value].append(file_hash)

        logger.debug(
            f"Added hash to database: {file_hash.hash_value[:16]}... "
            f"(total entries: {len(self.hash_db[file_hash.hash_value])})"
        )

    def check_duplicate(self, file_path: str) -> Optional[FileHash]:
        """
        Check if a local file is a duplicate of an existing object

        Args:
            file_path: Path to local file

        Returns:
            FileHash of duplicate if found, None otherwise
        """
        # Calculate hash of local file
        file_hash = self.calculate_file_hash(file_path)

        # Check if hash exists in database
        if file_hash in self.hash_db:
            duplicates = self.hash_db[file_hash]
            logger.info(
                f"Duplicate found for '{file_path}': "
                f"{len(duplicates)} existing file(s) with same hash"
            )
            return duplicates[0]  # Return first duplicate

        logger.debug(f"No duplicate found for '{file_path}'")
        return None

    def scan_bucket(
        self,
        prefix: Optional[str] = None,
        recursive: bool = True
    ) -> Dict[str, Any]:
        """
        Scan bucket for duplicate files

        Args:
            prefix: Optional prefix to filter objects
            recursive: Scan recursively

        Returns:
            Dictionary with duplicate detection results
        """
        logger.info(f"Starting duplicate scan for bucket '{self.bucket_name}'...")

        # Clear hash database
        self.hash_db.clear()

        total_files = 0
        total_size = 0
        duplicates_found: List[DuplicateFile] = []

        # List all objects
        objects = self.client.list_objects(
            self.bucket_name,
            prefix=prefix or "",
            recursive=recursive
        )

        for obj in objects:
            total_files += 1
            total_size += obj.size

            # Calculate hash
            try:
                hash_value = self.calculate_object_hash(obj.object_name)

                file_hash = FileHash(
                    object_name=obj.object_name,
                    hash_value=hash_value,
                    algorithm=self.hash_algorithm,
                    size_bytes=obj.size,
                    created_at=obj.last_modified
                )

                # Add to database
                self.add_to_hash_db(file_hash)

            except Exception as e:
                logger.error(f"Failed to process '{obj.object_name}': {e}")
                continue

        # Find duplicates
        total_duplicates = 0
        wasted_space = 0

        for hash_value, files in self.hash_db.items():
            if len(files) > 1:
                # Sort by creation time (oldest first)
                files_sorted = sorted(files, key=lambda x: x.created_at)
                original = files_sorted[0]
                dups = files_sorted[1:]

                duplicate_count = len(dups)
                duplicate_space = sum(f.size_bytes for f in dups)

                duplicates_found.append(DuplicateFile(
                    original=original,
                    duplicates=dups,
                    total_duplicates=duplicate_count,
                    wasted_space_bytes=duplicate_space
                ))

                total_duplicates += duplicate_count
                wasted_space += duplicate_space

        logger.info(
            f"Duplicate scan complete: {total_files} files scanned, "
            f"{total_duplicates} duplicates found, "
            f"{wasted_space / (1024**3):.2f}GB wasted"
        )

        return {
            'bucket': self.bucket_name,
            'prefix': prefix or '/',
            'total_files': total_files,
            'total_size_bytes': total_size,
            'total_size_gb': round(total_size / (1024 ** 3), 2),
            'unique_hashes': len(self.hash_db),
            'duplicate_groups': len(duplicates_found),
            'total_duplicates': total_duplicates,
            'wasted_space_bytes': wasted_space,
            'wasted_space_gb': round(wasted_space / (1024 ** 3), 4),
            'savings_percentage': round((wasted_space / total_size * 100), 2) if total_size > 0 else 0,
            'duplicates': [d.to_dict() for d in duplicates_found]
        }

    def remove_duplicates(
        self,
        dry_run: bool = True,
        keep_strategy: str = 'oldest'
    ) -> Dict[str, Any]:
        """
        Remove duplicate files from bucket

        Args:
            dry_run: If True, only report what would be deleted
            keep_strategy: 'oldest' or 'newest' file to keep

        Returns:
            Dictionary with removal results
        """
        if not self.hash_db:
            logger.warning("Hash database is empty. Run scan_bucket() first.")
            return {'error': 'No scan data available'}

        files_deleted = []
        space_freed = 0

        for hash_value, files in self.hash_db.items():
            if len(files) <= 1:
                continue

            # Sort files
            if keep_strategy == 'oldest':
                files_sorted = sorted(files, key=lambda x: x.created_at)
            else:  # newest
                files_sorted = sorted(files, key=lambda x: x.created_at, reverse=True)

            # Keep first, delete rest
            original = files_sorted[0]
            to_delete = files_sorted[1:]

            logger.info(
                f"Keeping '{original.object_name}', "
                f"deleting {len(to_delete)} duplicate(s)"
            )

            for dup in to_delete:
                if not dry_run:
                    try:
                        self.client.remove_object(self.bucket_name, dup.object_name)
                        logger.info(f"Deleted duplicate: {dup.object_name}")
                    except S3Error as e:
                        logger.error(f"Failed to delete '{dup.object_name}': {e}")
                        continue

                files_deleted.append(dup.object_name)
                space_freed += dup.size_bytes

        return {
            'dry_run': dry_run,
            'keep_strategy': keep_strategy,
            'files_deleted': len(files_deleted),
            'deleted_files': files_deleted,
            'space_freed_bytes': space_freed,
            'space_freed_gb': round(space_freed / (1024 ** 3), 4)
        }

    def get_duplicate_report(self) -> str:
        """
        Generate human-readable duplicate detection report

        Returns:
            Formatted report string
        """
        if not self.hash_db:
            return "No scan data available. Run scan_bucket() first."

        total_files = sum(len(files) for files in self.hash_db.values())
        duplicate_groups = sum(1 for files in self.hash_db.values() if len(files) > 1)
        total_duplicates = sum(len(files) - 1 for files in self.hash_db.values() if len(files) > 1)

        wasted_space = 0
        for files in self.hash_db.values():
            if len(files) > 1:
                # All duplicates waste space
                wasted_space += sum(f.size_bytes for f in files[1:])

        report = []
        report.append("=" * 60)
        report.append("DUPLICATE DETECTION REPORT")
        report.append("=" * 60)
        report.append(f"Total files scanned: {total_files}")
        report.append(f"Unique files: {len(self.hash_db)}")
        report.append(f"Duplicate groups: {duplicate_groups}")
        report.append(f"Total duplicates: {total_duplicates}")
        report.append(f"Wasted space: {wasted_space / (1024**3):.2f} GB")
        report.append("=" * 60)

        if duplicate_groups > 0:
            report.append("\nDuplicate Groups:")
            report.append("-" * 60)

            for hash_value, files in self.hash_db.items():
                if len(files) > 1:
                    report.append(f"\nHash: {hash_value[:16]}...")
                    report.append(f"  Count: {len(files)} files")
                    report.append(f"  Size: {files[0].size_bytes / (1024**2):.2f} MB each")
                    for f in files:
                        report.append(f"    - {f.object_name}")

        return "\n".join(report)
