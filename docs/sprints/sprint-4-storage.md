# Sprint 4: Storage & File Management (Week 5)

**Goal:** Implement comprehensive storage management and file operations

**Duration:** 1 week
**Team Size:** 2 developers

---

## Tasks

- [ ] Implement MinIO bucket lifecycle policies
- [ ] Create storage quota management system
- [ ] Implement file cleanup strategies (temp files, failed jobs)
- [ ] Add storage usage tracking per API key
- [ ] Implement presigned URL generation for downloads
- [ ] Add batch operations (delete multiple jobs, bulk download)
- [ ] Implement storage migration utilities
- [ ] Add checksum validation (SHA-256) for all uploads
- [ ] Implement duplicate detection system
- [ ] Add storage compression for old jobs (> 90 days)
- [ ] Create storage analytics dashboard data
- [ ] Implement backup automation for critical data
- [ ] Add restore functionality from backups
- [ ] Optimize MinIO performance (chunked uploads, parallel transfers)
- [ ] Implement storage tier management (hot/warm/cold)

---

## Deliverables

- ✅ Automated temp file cleanup
- ✅ Storage quota enforcement
- ✅ Presigned URL generation working
- ✅ Backup/restore procedures tested
- ✅ Storage analytics data available

---

## Acceptance Criteria

- [ ] Temp files cleaned up after job completion
- [ ] Failed job files cleaned up after 7 days
- [ ] Storage quotas enforced per API key
- [ ] Presigned URLs expire after configured time
- [ ] Duplicate videos detected and deduplicated
- [ ] Backups run automatically (daily)
- [ ] Storage usage tracked in database
- [ ] Old jobs compressed to save space

---

## Technical Details

### MinIO Lifecycle Policies

```python
# storage/lifecycle.py

from minio import Minio
from minio.lifecycleconfig import LifecycleConfig, Rule, Expiration

def configure_lifecycle_policies():
    """Configure MinIO lifecycle policies for automatic cleanup"""

    client = Minio(
        "minio:9000",
        access_key=os.getenv("MINIO_ACCESS_KEY"),
        secret_key=os.getenv("MINIO_SECRET_KEY"),
        secure=False
    )

    # Policy 1: Delete temp files after 1 day
    temp_rule = Rule(
        rule_id="delete-temp-files",
        status="Enabled",
        expiration=Expiration(days=1),
        rule_filter={"prefix": "temp/"}
    )

    # Policy 2: Delete failed job files after 7 days
    failed_rule = Rule(
        rule_id="delete-failed-jobs",
        status="Enabled",
        expiration=Expiration(days=7),
        rule_filter={"prefix": "failed/"}
    )

    # Policy 3: Transition old jobs to glacier after 90 days
    archive_rule = Rule(
        rule_id="archive-old-jobs",
        status="Enabled",
        transition=Transition(days=90, storage_class="GLACIER"),
        rule_filter={"prefix": "processed/"}
    )

    config = LifecycleConfig([temp_rule, failed_rule, archive_rule])

    client.set_bucket_lifecycle("videos", config)

    print("✅ Lifecycle policies configured")
```

---

### Storage Quota Management

```python
# storage/quota.py

from sqlalchemy import func
from models import Job, ApiKey

class StorageQuotaManager:
    def __init__(self, db_session):
        self.db = db_session

    def get_usage(self, api_key: str) -> dict:
        """Get storage usage for an API key"""

        # Sum all file sizes for this API key
        result = self.db.query(
            func.sum(Job.source_size_bytes).label('source_total'),
            func.sum(Job.output_360p_size_bytes).label('output_360p_total'),
            func.sum(Job.output_720p_size_bytes).label('output_720p_total'),
            func.sum(Job.output_audio_size_bytes).label('output_audio_total'),
            func.sum(Job.segments_360p_size_bytes).label('segments_360p_total'),
            func.sum(Job.segments_720p_size_bytes).label('segments_720p_total'),
            func.count(Job.id).label('total_jobs')
        ).filter(
            Job.api_key == api_key,
            Job.status == 'completed'
        ).first()

        total_bytes = sum([
            result.source_total or 0,
            result.output_360p_total or 0,
            result.output_720p_total or 0,
            result.output_audio_total or 0,
            result.segments_360p_total or 0,
            result.segments_720p_total or 0
        ])

        return {
            'total_bytes': total_bytes,
            'total_gb': round(total_bytes / (1024**3), 2),
            'total_jobs': result.total_jobs,
            'breakdown': {
                'source': result.source_total or 0,
                'output_360p': result.output_360p_total or 0,
                'output_720p': result.output_720p_total or 0,
                'audio': result.output_audio_total or 0,
                'segments_360p': result.segments_360p_total or 0,
                'segments_720p': result.segments_720p_total or 0
            }
        }

    def check_quota(self, api_key: str, additional_bytes: int) -> bool:
        """Check if adding more data would exceed quota"""

        # Get API key quota
        key = self.db.query(ApiKey).filter(ApiKey.key_hash == api_key).first()

        if not key.storage_quota_bytes:
            return True  # No quota set

        # Get current usage
        usage = self.get_usage(api_key)

        # Check if new upload would exceed quota
        if usage['total_bytes'] + additional_bytes > key.storage_quota_bytes:
            return False

        return True

    def enforce_quota(self, api_key: str, file_size: int):
        """Raise exception if quota would be exceeded"""

        if not self.check_quota(api_key, file_size):
            usage = self.get_usage(api_key)
            key = self.db.query(ApiKey).filter(ApiKey.key_hash == api_key).first()

            raise StorageQuotaExceeded(
                f"Storage quota exceeded. "
                f"Used: {usage['total_gb']}GB, "
                f"Quota: {key.storage_quota_bytes / (1024**3):.2f}GB"
            )
```

**Update API Key Table:**

```sql
ALTER TABLE api_keys
ADD COLUMN storage_quota_bytes BIGINT DEFAULT NULL,  -- NULL = unlimited
ADD COLUMN storage_used_bytes BIGINT DEFAULT 0;

CREATE INDEX idx_api_keys_storage ON api_keys(storage_quota_bytes, storage_used_bytes);
```

---

### Presigned URL Generation

```python
# storage/presigned.py

from minio import Minio
from datetime import timedelta

class PresignedURLGenerator:
    def __init__(self):
        self.client = Minio(
            "minio:9000",
            access_key=os.getenv("MINIO_ACCESS_KEY"),
            secret_key=os.getenv("MINIO_SECRET_KEY"),
            secure=False
        )

    def generate_download_url(
        self,
        job_id: str,
        file_type: str,
        expires: timedelta = timedelta(hours=1)
    ) -> str:
        """
        Generate presigned URL for downloading files

        file_type: '360p', '720p', 'audio', 'transcript_txt', 'transcript_srt', etc.
        """

        object_paths = {
            '360p': f'processed/{job_id}/360p/video_360p.mp4',
            '720p': f'processed/{job_id}/720p/video_720p.mp4',
            'audio': f'processed/{job_id}/audio/audio.mp3',
            'transcript_txt': f'processed/{job_id}/transcription/transcript.txt',
            'transcript_srt': f'processed/{job_id}/transcription/transcript.srt',
            'transcript_vtt': f'processed/{job_id}/transcription/transcript.vtt',
            'transcript_json': f'processed/{job_id}/transcription/transcript.json',
            'hls_360p': f'processed/{job_id}/360p/segments/playlist.m3u8',
            'hls_720p': f'processed/{job_id}/720p/segments/playlist.m3u8',
            'metadata': f'processed/{job_id}/metadata.json',
            'original': f'processed/{job_id}/raw/video_original.mp4'
        }

        object_name = object_paths.get(file_type)

        if not object_name:
            raise ValueError(f"Invalid file_type: {file_type}")

        url = self.client.presigned_get_object(
            bucket_name="videos",
            object_name=object_name,
            expires=expires
        )

        return url

    def generate_upload_url(
        self,
        job_id: str,
        filename: str,
        expires: timedelta = timedelta(minutes=30)
    ) -> str:
        """Generate presigned URL for uploading files (e.g., custom thumbnails)"""

        object_name = f"uploads/{job_id}/{filename}"

        url = self.client.presigned_put_object(
            bucket_name="videos",
            object_name=object_name,
            expires=expires
        )

        return url
```

**API Endpoint:**

```python
# api/routes/download.py

from fastapi import APIRouter, Depends, HTTPException
from storage.presigned import PresignedURLGenerator

router = APIRouter()

@router.get("/jobs/{job_id}/download/{file_type}")
async def get_download_url(
    job_id: str,
    file_type: str,
    api_key: str = Depends(verify_api_key)
):
    """
    Generate presigned download URL

    file_type options:
    - 360p, 720p, audio
    - transcript_txt, transcript_srt, transcript_vtt, transcript_json
    - hls_360p, hls_720p
    - metadata, original
    """

    # Verify job belongs to API key
    job = get_job(job_id)
    if job.api_key != api_key:
        raise HTTPException(status_code=403, detail="Access denied")

    if job.status != 'completed':
        raise HTTPException(status_code=400, detail="Job not completed")

    # Generate presigned URL (expires in 1 hour)
    generator = PresignedURLGenerator()
    url = generator.generate_download_url(job_id, file_type, expires=timedelta(hours=1))

    return {
        "job_id": job_id,
        "file_type": file_type,
        "download_url": url,
        "expires_in_seconds": 3600
    }
```

---

### Duplicate Detection

```python
# storage/deduplication.py

import hashlib
from models import Job

class DuplicateDetector:
    def __init__(self, db_session):
        self.db = db_session

    def calculate_file_hash(self, file_path: str) -> str:
        """Calculate SHA-256 hash of file"""

        sha256 = hashlib.sha256()

        with open(file_path, 'rb') as f:
            while chunk := f.read(8192):
                sha256.update(chunk)

        return sha256.hexdigest()

    def find_duplicate(self, file_hash: str, api_key: str) -> Job:
        """Find existing job with same file hash"""

        duplicate = self.db.query(Job).filter(
            Job.source_file_hash == file_hash,
            Job.api_key == api_key,
            Job.status == 'completed'
        ).first()

        return duplicate

    def handle_duplicate(self, original_job: Job) -> dict:
        """Return existing job info instead of processing again"""

        return {
            'duplicate': True,
            'original_job_id': original_job.id,
            'message': 'Video already processed. Returning existing results.',
            'created_at': original_job.created_at,
            'completed_at': original_job.completed_at,
            'outputs': {
                '360p': original_job.output_360p_path,
                '720p': original_job.output_720p_path,
                'audio': original_job.output_audio_path,
                'transcription': {
                    'txt': original_job.transcription_txt_path,
                    'srt': original_job.transcription_srt_path,
                    'vtt': original_job.transcription_vtt_path,
                    'json': original_job.transcription_json_path
                }
            }
        }
```

**Update Job Table:**

```sql
ALTER TABLE jobs
ADD COLUMN source_file_hash VARCHAR(64) DEFAULT NULL;

CREATE INDEX idx_jobs_file_hash ON jobs(source_file_hash, api_key, status);
```

**Usage in Upload Endpoint:**

```python
@router.post("/upload")
async def upload_video(file: UploadFile, api_key: str = Depends(verify_api_key)):
    # Save temp file
    temp_path = save_temp_file(file)

    # Calculate hash
    detector = DuplicateDetector(db_session)
    file_hash = detector.calculate_file_hash(temp_path)

    # Check for duplicate
    duplicate = detector.find_duplicate(file_hash, api_key)

    if duplicate:
        os.remove(temp_path)  # Delete temp file
        return detector.handle_duplicate(duplicate)

    # Continue with normal processing
    job = create_job(api_key, temp_path, file_hash)
    trigger_dag(job.id)

    return {"job_id": job.id, "status": "queued"}
```

---

### Cleanup Strategies

```python
# storage/cleanup.py

from datetime import datetime, timedelta
from models import Job
import shutil

class StorageCleanup:
    def __init__(self, db_session, minio_client):
        self.db = db_session
        self.minio = minio_client

    def cleanup_temp_files(self):
        """Delete temp files older than 1 day"""

        temp_dir = '/data/temp'
        cutoff_time = datetime.now() - timedelta(days=1)

        deleted_count = 0
        freed_bytes = 0

        for folder in os.listdir(temp_dir):
            folder_path = os.path.join(temp_dir, folder)

            if os.path.isdir(folder_path):
                # Check folder modification time
                mtime = datetime.fromtimestamp(os.path.getmtime(folder_path))

                if mtime < cutoff_time:
                    # Calculate size before deletion
                    size = sum(
                        os.path.getsize(os.path.join(dirpath, filename))
                        for dirpath, _, filenames in os.walk(folder_path)
                        for filename in filenames
                    )

                    shutil.rmtree(folder_path)
                    deleted_count += 1
                    freed_bytes += size

        return {
            'deleted_folders': deleted_count,
            'freed_bytes': freed_bytes,
            'freed_gb': round(freed_bytes / (1024**3), 2)
        }

    def cleanup_failed_jobs(self, days_old: int = 7):
        """Delete files from failed jobs after N days"""

        cutoff_date = datetime.now() - timedelta(days=days_old)

        failed_jobs = self.db.query(Job).filter(
            Job.status == 'failed',
            Job.updated_at < cutoff_date
        ).all()

        deleted_count = 0

        for job in failed_jobs:
            # Delete from MinIO
            objects = self.minio.list_objects(
                "videos",
                prefix=f"processed/{job.id}/",
                recursive=True
            )

            for obj in objects:
                self.minio.remove_object("videos", obj.object_name)

            # Update job status
            job.status = 'cleaned_up'
            job.updated_at = datetime.now()

            deleted_count += 1

        self.db.commit()

        return {
            'deleted_jobs': deleted_count
        }

    def cleanup_incomplete_jobs(self, hours_old: int = 24):
        """Cleanup jobs stuck in processing state"""

        cutoff_time = datetime.now() - timedelta(hours=hours_old)

        stuck_jobs = self.db.query(Job).filter(
            Job.status.in_(['queued', 'processing', 'transcoding', 'uploading']),
            Job.updated_at < cutoff_time
        ).all()

        for job in stuck_jobs:
            job.status = 'failed'
            job.error_message = 'Job timeout - stuck in processing'
            job.updated_at = datetime.now()

        self.db.commit()

        return {
            'marked_as_failed': len(stuck_jobs)
        }
```

**Scheduled Cleanup Task (Airflow):**

```python
# dags/storage_cleanup_dag.py

from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime, timedelta

default_args = {
    'owner': 'transcode-flow',
    'retries': 1,
    'retry_delay': timedelta(minutes=5)
}

dag = DAG(
    'storage_cleanup',
    default_args=default_args,
    description='Daily storage cleanup tasks',
    schedule_interval='0 2 * * *',  # Run at 2 AM daily
    start_date=datetime(2025, 1, 1),
    catchup=False,
    tags=['storage', 'cleanup']
)

def cleanup_temp_files_task():
    cleanup = StorageCleanup(db_session, minio_client)
    result = cleanup.cleanup_temp_files()
    print(f"✅ Cleaned up {result['deleted_folders']} folders, freed {result['freed_gb']}GB")

def cleanup_failed_jobs_task():
    cleanup = StorageCleanup(db_session, minio_client)
    result = cleanup.cleanup_failed_jobs(days_old=7)
    print(f"✅ Cleaned up {result['deleted_jobs']} failed jobs")

def cleanup_stuck_jobs_task():
    cleanup = StorageCleanup(db_session, minio_client)
    result = cleanup.cleanup_incomplete_jobs(hours_old=24)
    print(f"✅ Marked {result['marked_as_failed']} stuck jobs as failed")

# Tasks
cleanup_temp = PythonOperator(
    task_id='cleanup_temp_files',
    python_callable=cleanup_temp_files_task,
    dag=dag
)

cleanup_failed = PythonOperator(
    task_id='cleanup_failed_jobs',
    python_callable=cleanup_failed_jobs_task,
    dag=dag
)

cleanup_stuck = PythonOperator(
    task_id='cleanup_stuck_jobs',
    python_callable=cleanup_stuck_jobs_task,
    dag=dag
)

# Run in parallel
[cleanup_temp, cleanup_failed, cleanup_stuck]
```

---

### Backup & Restore

```python
# storage/backup.py

import subprocess
from datetime import datetime

class BackupManager:
    def __init__(self):
        self.backup_dir = '/data/backups'
        os.makedirs(self.backup_dir, exist_ok=True)

    def backup_database(self):
        """Backup PostgreSQL database"""

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_file = f'{self.backup_dir}/postgres_{timestamp}.sql.gz'

        # Use pg_dump
        cmd = [
            'docker', 'exec', 'postgres',
            'pg_dump', '-U', 'transcode_user', 'transcode_db'
        ]

        # Compress and save
        with open(backup_file, 'wb') as f:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE)
            subprocess.run(['gzip'], stdin=proc.stdout, stdout=f)

        file_size = os.path.getsize(backup_file)

        return {
            'backup_file': backup_file,
            'size_mb': round(file_size / (1024**2), 2),
            'timestamp': timestamp
        }

    def backup_minio_metadata(self):
        """Backup critical MinIO metadata (not full videos)"""

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_dir = f'{self.backup_dir}/minio_metadata_{timestamp}'
        os.makedirs(backup_dir, exist_ok=True)

        # Backup only metadata.json files (small)
        objects = minio_client.list_objects(
            "videos",
            prefix="processed/",
            recursive=True
        )

        count = 0
        for obj in objects:
            if obj.object_name.endswith('metadata.json'):
                local_path = f'{backup_dir}/{obj.object_name}'
                os.makedirs(os.path.dirname(local_path), exist_ok=True)

                minio_client.fget_object("videos", obj.object_name, local_path)
                count += 1

        # Create tarball
        tarball = f'{self.backup_dir}/minio_metadata_{timestamp}.tar.gz'
        subprocess.run(['tar', '-czf', tarball, '-C', self.backup_dir,
                       f'minio_metadata_{timestamp}'])

        # Remove uncompressed backup
        shutil.rmtree(backup_dir)

        return {
            'backup_file': tarball,
            'metadata_files': count,
            'size_mb': round(os.path.getsize(tarball) / (1024**2), 2)
        }

    def restore_database(self, backup_file: str):
        """Restore database from backup"""

        # Decompress
        cmd = ['gunzip', '-c', backup_file]

        # Restore using psql
        restore_cmd = [
            'docker', 'exec', '-i', 'postgres',
            'psql', '-U', 'transcode_user', 'transcode_db'
        ]

        proc1 = subprocess.Popen(cmd, stdout=subprocess.PIPE)
        proc2 = subprocess.Popen(restore_cmd, stdin=proc1.stdout)
        proc2.wait()

        return {
            'status': 'restored',
            'backup_file': backup_file
        }
```

**Backup DAG:**

```python
# dags/backup_dag.py

dag = DAG(
    'daily_backup',
    default_args=default_args,
    description='Daily backup of database and metadata',
    schedule_interval='0 3 * * *',  # Run at 3 AM daily
    start_date=datetime(2025, 1, 1),
    catchup=False,
    tags=['backup']
)

def backup_task():
    manager = BackupManager()

    # Backup database
    db_result = manager.backup_database()
    print(f"✅ Database backed up: {db_result['size_mb']}MB")

    # Backup MinIO metadata
    minio_result = manager.backup_minio_metadata()
    print(f"✅ MinIO metadata backed up: {minio_result['metadata_files']} files, {minio_result['size_mb']}MB")

    # Delete old backups (keep last 30 days)
    cleanup_old_backups(days=30)

backup = PythonOperator(
    task_id='daily_backup',
    python_callable=backup_task,
    dag=dag
)
```

---

## Testing

### Storage Tests

```python
# tests/test_storage.py

def test_quota_enforcement():
    """Test that storage quota is enforced"""
    quota_manager = StorageQuotaManager(db_session)

    # Set quota to 1GB
    api_key.storage_quota_bytes = 1024**3

    # Try to upload 2GB file
    with pytest.raises(StorageQuotaExceeded):
        quota_manager.enforce_quota(api_key.key_hash, 2 * 1024**3)

def test_duplicate_detection():
    """Test duplicate video detection"""
    detector = DuplicateDetector(db_session)

    # Upload same video twice
    hash1 = detector.calculate_file_hash('test_video.mp4')
    hash2 = detector.calculate_file_hash('test_video.mp4')

    assert hash1 == hash2

    # Check duplicate is found
    duplicate = detector.find_duplicate(hash1, api_key.key_hash)
    assert duplicate is not None

def test_presigned_url():
    """Test presigned URL generation"""
    generator = PresignedURLGenerator()

    url = generator.generate_download_url(job_id, '360p', expires=timedelta(hours=1))

    assert 'minio' in url
    assert 'X-Amz-Expires=3600' in url

def test_cleanup_temp_files():
    """Test temp file cleanup"""
    cleanup = StorageCleanup(db_session, minio_client)

    # Create old temp folder
    old_folder = '/data/temp/old_job'
    os.makedirs(old_folder)

    # Set modification time to 2 days ago
    two_days_ago = time.time() - (2 * 24 * 3600)
    os.utime(old_folder, (two_days_ago, two_days_ago))

    # Run cleanup
    result = cleanup.cleanup_temp_files()

    assert result['deleted_folders'] > 0
    assert not os.path.exists(old_folder)

def test_backup_restore():
    """Test database backup and restore"""
    manager = BackupManager()

    # Create backup
    backup_result = manager.backup_database()
    assert os.path.exists(backup_result['backup_file'])

    # Restore backup
    restore_result = manager.restore_database(backup_result['backup_file'])
    assert restore_result['status'] == 'restored'
```

---

## Performance Targets

| Operation | Target Time | Max Time |
|-----------|-------------|----------|
| Presigned URL generation | < 50ms | < 100ms |
| Duplicate detection (hash) | < 2s | < 5s |
| Cleanup temp files (1000 files) | < 30s | < 60s |
| Database backup | < 2 min | < 5 min |
| Storage quota check | < 10ms | < 50ms |

---

## Next Sprint

Sprint 5: Job Status & Monitoring APIs
