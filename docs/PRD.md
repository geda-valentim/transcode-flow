# Product Requirements Document (PRD)
## Video Transcoding Service Platform

**Version:** 1.0
**Last Updated:** 2025-11-18
**Status:** Draft

---

## 1. Executive Summary

### 1.1 Overview
A job-oriented video transcoding platform that processes video files into multiple formats (360p, 720p MP4 for streaming) and extracts audio (MP3), with full orchestration, monitoring, and API access control.

### 1.2 Objectives
- Process 2TB of video content across various formats
- Enable parallel processing using 8 worker threads
- Provide real-time job status and progress tracking
- Ensure high availability and fault tolerance
- Enable NGINX-based HLS/DASH streaming delivery
- Centralized storage with MinIO S3-compatible object storage
- Full observability with Prometheus and Grafana

### 1.3 Success Metrics
- **Throughput:** Process minimum 100GB/day with 8 parallel workers
- **Reliability:** 99% job completion rate
- **Performance:** Max 5-minute startup time for job processing
- **API Response Time:** < 200ms for status endpoints
- **Error Rate:** < 1% failed jobs (excluding corrupted source files)

---

## 2. System Architecture

### 2.1 Technology Stack

| Component | Technology | Version |
|-----------|-----------|---------|
| **Orchestration** | Apache Airflow | Latest |
| **Task Queue** | Celery + Redis | Latest |
| **Object Storage** | MinIO | Latest |
| **API** | FastAPI + Uvicorn | Latest |
| **Database** | PostgreSQL | Latest |
| **Transcoding** | FFmpeg | Latest |
| **Transcription** | OpenAI Whisper | Latest |
| **Monitoring** | Prometheus + Grafana | Latest |
| **Streaming** | NGINX + RTMP/HLS | Latest |
| **OS** | Ubuntu | 24.04 |
| **Container Runtime** | Docker + Docker Compose | Latest |

**IMPORTANT:**
- All services must run via Docker Compose - no manual installations required on the host
- **Data persistence:** All data is stored in `/data/` on the host filesystem (survives container restarts/rebuilds)
- **Application code:** Runs inside Docker containers (stateless, can be rebuilt anytime)

### 2.2 Hardware Specifications

```
Processor: Intel Xeon-E3 1270 v6 (4c/8t - 3.8GHz/4.2GHz)
Memory: 64GB DDR4 ECC 2400MHz
Storage:
  - 1x 2TB HDD SATA (standalone - OS + applications)
  - 3x 2TB HDD SATA RAID 5 (~4TB usable - video storage)
Network: 500Mbit/s unmetered
```

### 2.3 Docker Services

```yaml
Services:
  1. redis - Message broker for Celery
  2. minio - S3-compatible object storage
  3. postgres - Airflow metadata + application database
  4. airflow-webserver - Airflow UI
  5. airflow-scheduler - DAG scheduler
  6. airflow-init - Database initialization
  7. celery-worker - Transcoding workers (concurrency=8)
  8. celery-flower - Celery monitoring UI
  9. fastapi - REST API service
  10. nginx - Streaming server (HLS/DASH)
  11. prometheus - Metrics collection
  12. grafana - Metrics visualization
```

### 2.4 Network Ports

| Service | Port | Access |
|---------|------|--------|
| MinIO API | 9000 | Internal |
| MinIO Console | 9001 | External |
| Airflow Webserver | 8080 | External |
| FastAPI | 8000 | External |
| Redis | 6379 | Internal |
| PostgreSQL | 5432 | Internal |
| Flower | 5555 | External |
| NGINX HTTP | 80 | External |
| NGINX HTTPS | 443 | External |
| Prometheus | 9090 | External |
| Grafana | 3000 | External |

### 2.5 Data Persistence & Volume Structure

**CRITICAL: Data Persistence Strategy**

```
┌─────────────────────────────────────────────────────────────────┐
│  HOST SYSTEM (Ubuntu + RAID 5)                                  │
│                                                                  │
│  /data/  ◄── ALL DATA LIVES HERE (PERSISTENT)                  │
│  ├── minio/         (videos, transcoded files)                  │
│  ├── postgres/      (jobs, tasks, API keys)                     │
│  ├── prometheus/    (metrics)                                   │
│  ├── grafana/       (dashboards)                                │
│  ├── airflow/       (DAGs, logs)                                │
│  └── temp/          (temporary files)                           │
│                                                                  │
│  ┌────────────────────────────────────────────────────────┐    │
│  │  DOCKER CONTAINERS (STATELESS - can be rebuilt)        │    │
│  │  ├── fastapi        ──► mounts /data/temp              │    │
│  │  ├── postgres       ──► mounts /data/postgres          │    │
│  │  ├── minio          ──► mounts /data/minio             │    │
│  │  ├── airflow        ──► mounts /data/airflow           │    │
│  │  ├── prometheus     ──► mounts /data/prometheus        │    │
│  │  ├── grafana        ──► mounts /data/grafana           │    │
│  │  ├── celery-worker  ──► mounts /data/temp              │    │
│  │  ├── redis          ──► (ephemeral - no persistence)   │    │
│  │  └── nginx          ──► (reverse proxy - no data)      │    │
│  └────────────────────────────────────────────────────────┘    │
│                                                                  │
│  docker compose down  ──► Containers destroyed ✓                │
│                           Data in /data/ preserved ✓            │
│                                                                  │
│  docker compose up -d ──► Containers recreated ✓                │
│                           Data remounted from /data/ ✓          │
└─────────────────────────────────────────────────────────────────┘
```

**Data Location:** `/data/` on host filesystem (Ubuntu RAID 5 array - 4TB)

**Volume Mapping in docker compose.yml:**
```yaml
volumes:
  - /data/minio:/data                  # MinIO data persists on host
  - /data/postgres:/var/lib/postgresql/data  # PostgreSQL data persists
  - /data/prometheus:/prometheus       # Metrics data persists
  - /data/grafana:/var/lib/grafana    # Dashboards persist
  - /data/airflow/dags:/opt/airflow/dags  # DAGs persist
  - /data/temp:/temp                   # Temp files (cleaned regularly)
```

**What Persists (survives `docker compose down`):**
✅ All videos (original + transcoded)
✅ All database data (jobs, tasks, API keys)
✅ All metrics and dashboards
✅ All DAGs and configurations
✅ All logs

**What Does NOT Persist (rebuilt on restart):**
❌ Docker images
❌ Container state
❌ Running processes
❌ Application code (lives in containers)

**Full Directory Structure:**

```
/data/                              # HOST FILESYSTEM (PERSISTENT)
├── minio/                          # MinIO object storage
│   └── videos/                     # Main video bucket
│       ├── raw/                    # Original videos (immutable)
│       └── processed/              # Processed videos
│           └── {job_id}/           # One folder per video job
│               ├── metadata.json   # Video info + user metadata
│               ├── raw/            # Original video copy
│               │   └── video_original.mp4
│               ├── 360p/           # 360p outputs
│               │   ├── video_360p.mp4
│               │   └── segments/   # HLS segments
│               │       ├── playlist.m3u8
│               │       ├── segment_000.ts
│               │       └── segment_001.ts
│               ├── 720p/           # 720p outputs
│               │   ├── video_720p.mp4
│               │   └── segments/   # HLS segments
│               │       ├── playlist.m3u8
│               │       ├── segment_000.ts
│               │       └── segment_001.ts
│               ├── audio/          # Audio extraction
│               │   └── audio.mp3
│               ├── transcription/  # Video transcription
│               │   ├── transcript.txt      # Plain text
│               │   ├── transcript.srt      # SubRip subtitles
│               │   ├── transcript.vtt      # WebVTT subtitles
│               │   └── transcript.json     # Full Whisper output
│               └── thumbnails/     # Video thumbnails
│                   ├── thumb_custom.jpg   # User-uploaded (if provided)
│                   ├── thumb_00.jpg       # Auto-generated at 0%
│                   ├── thumb_25.jpg       # Auto-generated at 25%
│                   ├── thumb_50.jpg       # Auto-generated at 50%
│                   ├── thumb_75.jpg       # Auto-generated at 75%
│                   └── thumb_100.jpg      # Auto-generated at 100%
├── temp/                           # Temporary processing files
│   └── {job_id}/                   # Cleaned after job completion
├── airflow/
│   ├── dags/                       # DAG definitions
│   ├── logs/                       # Airflow logs
│   └── plugins/                    # Custom plugins
├── postgres/                       # PostgreSQL data
├── prometheus/                     # Prometheus data
└── grafana/                        # Grafana dashboards
```

### 2.6 Metadata JSON Structure

Each processed video has a `metadata.json` file with complete video information:

```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "created_at": "2025-11-18T14:30:22Z",
  "completed_at": "2025-11-18T15:15:45Z",
  "processing_time_seconds": 2723,
  "status": "completed",

  "user_metadata": {
    "title": "My Video Title",
    "description": "Video description provided by user",
    "tags": ["tag1", "tag2", "tag3"],
    "category": "entertainment",
    "custom_field_1": "custom value",
    "custom_field_2": 123
  },

  "source": {
    "filename": "original_video.mp4",
    "size_bytes": 2147483648,
    "format": "mp4",
    "codec": "h264",
    "resolution": "1920x1080",
    "width": 1920,
    "height": 1080,
    "duration_seconds": 3600.5,
    "bitrate": 5000000,
    "fps": 30,
    "audio_codec": "aac",
    "audio_bitrate": 128000,
    "audio_sample_rate": 48000
  },

  "outputs": {
    "360p": {
      "path": "processed/{job_id}/360p/video_360p.mp4",
      "size_bytes": 268435456,
      "resolution": "640x360",
      "bitrate": 800000,
      "processing_time_seconds": 450,
      "segments": {
        "count": 360,
        "duration_seconds": 10,
        "total_size_bytes": 270000000,
        "playlist_path": "processed/{job_id}/360p/segments/playlist.m3u8"
      }
    },
    "720p": {
      "path": "processed/{job_id}/720p/video_720p.mp4",
      "size_bytes": 805306368,
      "resolution": "1280x720",
      "bitrate": 2500000,
      "processing_time_seconds": 1800,
      "segments": {
        "count": 360,
        "duration_seconds": 10,
        "total_size_bytes": 810000000,
        "playlist_path": "processed/{job_id}/720p/segments/playlist.m3u8"
      }
    },
    "audio": {
      "path": "processed/{job_id}/audio/audio.mp3",
      "size_bytes": 90177536,
      "bitrate": 192000,
      "sample_rate": 48000,
      "duration_seconds": 3600.5,
      "processing_time_seconds": 120
    },
    "transcription": {
      "text": {
        "path": "processed/{job_id}/transcription/transcript.txt",
        "size_bytes": 12456,
        "word_count": 2341,
        "language": "en"
      },
      "srt": {
        "path": "processed/{job_id}/transcription/transcript.srt",
        "size_bytes": 15234
      },
      "vtt": {
        "path": "processed/{job_id}/transcription/transcript.vtt",
        "size_bytes": 15567
      },
      "json": {
        "path": "processed/{job_id}/transcription/transcript.json",
        "size_bytes": 45789
      },
      "processing_time_seconds": 180,
      "whisper_model": "base"
    },
    "thumbnails": {
      "custom": {
        "path": "processed/{job_id}/thumbnails/thumb_custom.jpg",
        "size_bytes": 128456,
        "source": "user_uploaded",
        "is_primary": true
      },
      "auto_generated": [
        {
          "position_percent": 0,
          "timestamp": "00:00:00",
          "path": "processed/{job_id}/thumbnails/thumb_00.jpg",
          "size_bytes": 45678
        },
        {
          "position_percent": 25,
          "timestamp": "00:15:00",
          "path": "processed/{job_id}/thumbnails/thumb_25.jpg",
          "size_bytes": 47821
        },
        {
          "position_percent": 50,
          "timestamp": "00:30:00",
          "path": "processed/{job_id}/thumbnails/thumb_50.jpg",
          "size_bytes": 46912
        },
        {
          "position_percent": 75,
          "timestamp": "00:45:00",
          "path": "processed/{job_id}/thumbnails/thumb_75.jpg",
          "size_bytes": 48234
        },
        {
          "position_percent": 100,
          "timestamp": "01:00:00",
          "path": "processed/{job_id}/thumbnails/thumb_100.jpg",
          "size_bytes": 46543
        }
      ]
    }
  },

  "compression_ratio": {
    "360p": 7.99,
    "720p": 2.67,
    "total_saved_percent": 48.5
  },

  "quality_metrics": {
    "360p": {
      "psnr": 42.5,
      "ssim": 0.95
    },
    "720p": {
      "psnr": 45.2,
      "ssim": 0.97
    }
  }
}
```

---

## 3. Functional Requirements

### 3.1 Video Upload & Validation

#### FR-1.1: Video Input Methods
- **API Upload:** Accept multipart/form-data video uploads via POST endpoint
- **File Reference:** Accept filesystem path to existing video on server
- **MinIO Reference:** Accept MinIO bucket/object path

#### FR-1.2: Video Validation
```python
Validation Steps:
1. File existence check
2. File format validation (mp4, avi, mov, mkv, flv, wmv, webm)
3. Codec compatibility check (FFprobe)
4. Resolution detection
5. Duration validation (min: 1s, max: 24h)
6. File integrity check (corrupted file detection)
7. Minimum resolution: 360p (640x360)
```

**Validation Response:**
```json
{
  "valid": true,
  "video_info": {
    "format": "mp4",
    "codec": "h264",
    "resolution": "1920x1080",
    "duration": 3600.5,
    "bitrate": 5000000,
    "fps": 30,
    "audio_codec": "aac",
    "file_size_mb": 2048
  },
  "transcoding_options": {
    "can_360p": true,
    "can_720p": true,
    "can_extract_audio": true
  }
}
```

### 3.2 Transcoding Pipeline

#### FR-2.1: Resolution-Based Transcoding
```
Source Resolution Logic:
- >= 1280x720 → Generate 360p + 720p
- >= 640x360 and < 1280x720 → Generate 360p only
- < 640x360 → Skip transcoding (below minimum)
```

#### FR-2.2: FFmpeg Transcoding Parameters

**360p Configuration:**
```bash
ffmpeg -i input.mp4 \
  -vf "scale=-2:360" \
  -c:v libx264 -preset medium -crf 23 \
  -profile:v main -level 3.1 \
  -movflags +faststart \
  -c:a aac -b:a 96k -ar 44100 \
  -f mp4 output_360p.mp4
```

**720p Configuration:**
```bash
ffmpeg -i input.mp4 \
  -vf "scale=-2:720" \
  -c:v libx264 -preset medium -crf 22 \
  -profile:v high -level 4.0 \
  -movflags +faststart \
  -c:a aac -b:a 128k -ar 48000 \
  -f mp4 output_720p.mp4
```

**HLS Streaming Preparation:**
```bash
ffmpeg -i output_720p.mp4 \
  -codec: copy -start_number 0 \
  -hls_time 10 -hls_list_size 0 \
  -f hls output_720p.m3u8
```

#### FR-2.3: Audio Extraction (MP3)
```bash
ffmpeg -i input.mp4 \
  -vn -acodec libmp3lame \
  -b:a 192k -ar 48000 \
  output.mp3
```

#### FR-2.4: Video Transcription (OpenAI Whisper)

**Whisper Model Selection:**
```python
# Automatic model selection based on video duration
if duration < 300:  # < 5 minutes
    model = "tiny"   # Fastest, lower accuracy
elif duration < 1800:  # < 30 minutes
    model = "base"   # Balanced (RECOMMENDED)
elif duration < 3600:  # < 1 hour
    model = "small"  # Better accuracy
else:
    model = "base"   # Large videos use base for performance
```

**Transcription Process:**
```bash
# Extract audio for Whisper (Whisper prefers WAV format)
ffmpeg -i input.mp4 -ar 16000 -ac 1 -c:a pcm_s16le temp_audio.wav

# Run Whisper transcription
whisper temp_audio.wav \
  --model base \
  --language auto \
  --output_format all \
  --output_dir transcription/
```

**Output Formats:**
- **TXT:** Plain text transcript
- **SRT:** SubRip subtitle format (with timestamps)
- **VTT:** WebVTT format for HTML5 video players
- **JSON:** Full Whisper output with word-level timestamps, confidence scores

**Language Detection:**
Whisper auto-detects language, but users can specify via metadata:
```json
{
  "transcription_language": "pt",  // Force Portuguese
  "whisper_model": "small"          // Override model selection
}
```

**Supported Languages:**
English, Spanish, French, German, Portuguese, Italian, Dutch, Russian, Chinese, Japanese, Korean, and 90+ more languages.

### 3.3 Storage Organization (MinIO)

#### FR-3.1: Bucket Structure
```
Main Bucket: videos

Folder Structure:
- videos/raw/                           # Immutable original videos
  └── {job_id}_original.mp4

- videos/processed/{job_id}/            # One folder per job
  ├── metadata.json                     # Complete video metadata
  ├── raw/                              # Original copy
  │   └── video_original.mp4
  ├── 360p/
  │   ├── video_360p.mp4
  │   └── segments/
  │       ├── playlist.m3u8
  │       └── segment_*.ts
  ├── 720p/
  │   ├── video_720p.mp4
  │   └── segments/
  │       ├── playlist.m3u8
  │       └── segment_*.ts
  ├── audio/
  │   └── audio.mp3
  ├── transcription/
  │   ├── transcript.txt
  │   ├── transcript.srt
  │   ├── transcript.vtt
  │   └── transcript.json
  └── thumbnails/
      ├── thumb_custom.jpg
      ├── thumb_00.jpg
      ├── thumb_25.jpg
      ├── thumb_50.jpg
      ├── thumb_75.jpg
      └── thumb_100.jpg
```

#### FR-3.2: Metadata JSON Management

**User-Provided Metadata:**
Users can submit custom metadata with their video upload, which will be:
1. Validated and sanitized
2. Stored in PostgreSQL `jobs` table
3. Included in the `metadata.json` file
4. Returned via API endpoints

**Metadata Fields:**
- **Required:** None (all optional)
- **Common fields:** title, description, tags, category, author, copyright
- **Custom fields:** Any valid JSON key-value pairs

**Storage:**
- PostgreSQL: `jobs.user_metadata` (JSONB column)
- MinIO: `videos/processed/{job_id}/metadata.json`

### 3.4 Airflow DAG Orchestration

#### FR-4.1: DAG Structure
```python
DAG: video_transcoding_pipeline

Tasks:
1. validate_video          # Validate input file
2. upload_to_minio         # Upload source to MinIO (if from filesystem)
3. generate_thumbnail      # Extract thumbnail
4. transcode_360p          # Generate 360p (conditional)
5. transcode_720p          # Generate 720p (conditional)
6. extract_audio_mp3       # Extract MP3 audio
7. transcribe_video        # Whisper transcription (TXT, SRT, VTT, JSON)
8. prepare_hls_360p        # Generate HLS segments (conditional)
9. prepare_hls_720p        # Generate HLS segments (conditional)
10. upload_outputs         # Upload all outputs to MinIO
11. update_database        # Update job status in PostgreSQL
12. cleanup_temp_files     # Remove local temp files
13. send_notification      # Optional webhook notification

Dependencies:
validate_video >> upload_to_minio >> generate_thumbnail
validate_video >> [transcode_360p, transcode_720p, extract_audio_mp3]
transcode_360p >> prepare_hls_360p >> upload_outputs
transcode_720p >> prepare_hls_720p >> upload_outputs
extract_audio_mp3 >> transcribe_video >> upload_outputs
upload_outputs >> update_database >> cleanup_temp_files >> send_notification
```

#### FR-4.2: Task Retry Policy
```python
default_task_args = {
    'retries': 3,
    'retry_delay': timedelta(minutes=5),
    'retry_exponential_backoff': True,
    'max_retry_delay': timedelta(minutes=30),
    'execution_timeout': timedelta(hours=4)
}
```

### 3.5 Job Queue Management (Celery)

#### FR-5.1: Worker Configuration
```python
CELERY_CONFIG = {
    'broker_url': 'redis://redis:6379/0',
    'result_backend': 'db+postgresql://...',
    'task_serializer': 'json',
    'accept_content': ['json'],
    'result_serializer': 'json',
    'timezone': 'UTC',
    'worker_concurrency': 8,
    'worker_prefetch_multiplier': 1,
    'task_acks_late': True,
    'task_reject_on_worker_lost': True,
    'task_time_limit': 14400,  # 4 hours
    'task_soft_time_limit': 13500  # 3h45m
}
```

#### FR-5.2: Task Priorities
```
Priority Levels:
  10 - Critical (manual retries, VIP users)
  5  - Normal (DEFAULT - standard queue)
  3  - Low (batch processing)
  1  - Very Low (background tasks)
```

### 3.6 Database Schema (PostgreSQL)

#### FR-6.1: Tables

**jobs**
```sql
CREATE TABLE jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    api_key VARCHAR(64) NOT NULL,
    status VARCHAR(20) NOT NULL,  -- pending, validating, processing, completed, failed
    source_type VARCHAR(20) NOT NULL,  -- upload, filesystem, minio
    source_path TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    completed_at TIMESTAMP,
    priority INTEGER DEFAULT 5,  -- Default priority: 5

    -- User-provided metadata (JSONB for flexibility)
    user_metadata JSONB DEFAULT '{}',

    -- Source video info
    original_filename VARCHAR(255),
    file_size_bytes BIGINT,
    duration_seconds FLOAT,
    source_resolution VARCHAR(20),
    source_width INTEGER,
    source_height INTEGER,
    source_format VARCHAR(20),
    source_codec VARCHAR(50),
    source_bitrate BIGINT,
    source_fps FLOAT,
    audio_codec VARCHAR(50),
    audio_bitrate INTEGER,
    audio_sample_rate INTEGER,

    -- Progress tracking
    progress_percent INTEGER DEFAULT 0,
    current_task VARCHAR(100),

    -- Output paths
    output_360p_path TEXT,
    output_720p_path TEXT,
    output_audio_path TEXT,
    output_hls_360p_path TEXT,
    output_hls_720p_path TEXT,
    thumbnail_path TEXT,
    thumbnail_custom_path TEXT,
    thumbnail_custom_size_bytes BIGINT,
    transcription_txt_path TEXT,
    transcription_srt_path TEXT,
    transcription_vtt_path TEXT,
    transcription_json_path TEXT,
    metadata_json_path TEXT,

    -- Output details
    output_360p_size_bytes BIGINT,
    output_720p_size_bytes BIGINT,
    output_audio_size_bytes BIGINT,

    -- HLS segment information
    segments_360p_count INTEGER,
    segments_720p_count INTEGER,
    segments_360p_size_bytes BIGINT,
    segments_720p_size_bytes BIGINT,

    -- Processing metrics
    processing_time_seconds INTEGER,
    transcode_360p_time_seconds INTEGER,
    transcode_720p_time_seconds INTEGER,
    audio_extraction_time_seconds INTEGER,
    transcription_time_seconds INTEGER,
    transcription_language VARCHAR(10),
    transcription_word_count INTEGER,
    whisper_model VARCHAR(20),

    -- Compression metrics
    compression_ratio_360p FLOAT,
    compression_ratio_720p FLOAT,
    total_saved_percent FLOAT,

    -- Error handling
    error_message TEXT,
    retry_count INTEGER DEFAULT 0,

    INDEX idx_jobs_api_key (api_key),
    INDEX idx_jobs_status (status),
    INDEX idx_jobs_created_at (created_at),
    INDEX idx_jobs_priority (priority DESC),
    INDEX idx_jobs_user_metadata USING GIN (user_metadata)
);
```

**tasks**
```sql
CREATE TABLE tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID REFERENCES jobs(id) ON DELETE CASCADE,
    task_name VARCHAR(100) NOT NULL,
    status VARCHAR(20) NOT NULL,  -- pending, running, completed, failed, skipped
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    duration_seconds INTEGER,
    error_message TEXT,
    output_size_bytes BIGINT,

    INDEX idx_tasks_job_id (job_id),
    INDEX idx_tasks_status (status)
);
```

**api_keys**
```sql
CREATE TABLE api_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    key_hash VARCHAR(64) UNIQUE NOT NULL,
    name VARCHAR(100),
    is_active BOOLEAN DEFAULT TRUE,
    rate_limit_per_hour INTEGER DEFAULT 100,
    created_at TIMESTAMP DEFAULT NOW(),
    last_used_at TIMESTAMP,

    INDEX idx_api_keys_hash (key_hash)
);
```

**usage_stats**
```sql
CREATE TABLE usage_stats (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    api_key VARCHAR(64) NOT NULL,
    date DATE NOT NULL,
    jobs_created INTEGER DEFAULT 0,
    jobs_completed INTEGER DEFAULT 0,
    jobs_failed INTEGER DEFAULT 0,
    total_input_gb FLOAT DEFAULT 0,
    total_output_gb FLOAT DEFAULT 0,
    total_processing_hours FLOAT DEFAULT 0,

    UNIQUE (api_key, date),
    INDEX idx_usage_date (date)
);
```

---

## 4. API Specifications

### 4.1 Authentication

**Method:** API Key (Header-based)
```
Header: X-API-Key: {your_api_key}
```

### 4.2 Endpoints

#### POST /api/v1/jobs/upload
**Description:** Upload video file for transcoding

**Request:**
```http
POST /api/v1/jobs/upload
Content-Type: multipart/form-data
X-API-Key: abc123...

file: (binary) - REQUIRED - Video file to transcode
thumbnail: (binary) - OPTIONAL - Custom thumbnail image (jpg/png, max 5MB)
priority: 5 (optional, default: 5)
webhook_url: https://example.com/callback (optional)
metadata: (JSON string, optional)
```

**Notes:**
- If `thumbnail` is provided, it will be used as the primary thumbnail
- Auto-generated thumbnails will still be created at 0%, 25%, 50%, 75%, 100%
- Custom thumbnail will be saved as `thumb_custom.jpg`
- Accepted formats: JPG, PNG, WebP
- Max size: 5MB
- Recommended resolution: 1280x720

**Metadata Example:**
```json
{
  "title": "My Awesome Video",
  "description": "A detailed description of the video content",
  "tags": ["tutorial", "programming", "python"],
  "category": "education",
  "author": "John Doe",
  "copyright": "CC BY-SA 4.0",
  "language": "en",
  "custom_field": "custom value"
}
```

**Response (202 Accepted):**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "pending",
  "message": "Job queued successfully",
  "created_at": "2025-11-18T14:30:22Z",
  "priority": 5
}
```

---

#### POST /api/v1/jobs/filesystem
**Description:** Create job from server filesystem path

**Request:**
```json
{
  "file_path": "/data/videos/source/video.mp4",
  "priority": 5,
  "webhook_url": "https://example.com/callback",
  "metadata": {
    "title": "Video from filesystem",
    "description": "Description here",
    "tags": ["tag1", "tag2"]
  }
}
```

**Response (202 Accepted):**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "validating",
  "message": "Job created successfully",
  "priority": 5
}
```

---

#### POST /api/v1/jobs/minio
**Description:** Create job from MinIO object

**Request:**
```json
{
  "bucket": "videos",
  "object_key": "raw/video.mp4",
  "priority": 5,
  "metadata": {
    "title": "Video from MinIO",
    "category": "entertainment"
  }
}
```

**Response (202 Accepted):**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "pending",
  "priority": 5
}
```

---

#### GET /api/v1/jobs/{job_id}
**Description:** Get job status and details

**Response (200 OK):**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "processing",
  "progress_percent": 65,
  "current_task": "transcode_720p",
  "created_at": "2025-11-18T14:30:22Z",
  "updated_at": "2025-11-18T14:45:10Z",

  "video_info": {
    "filename": "video.mp4",
    "duration": 3600.5,
    "resolution": "1920x1080",
    "size_mb": 2048,
    "format": "mp4",
    "codec": "h264"
  },

  "tasks": [
    {
      "name": "validate_video",
      "status": "completed",
      "duration_seconds": 5
    },
    {
      "name": "transcode_360p",
      "status": "completed",
      "duration_seconds": 450,
      "output_size_mb": 256
    },
    {
      "name": "transcode_720p",
      "status": "running",
      "progress_percent": 65,
      "eta_seconds": 180
    },
    {
      "name": "extract_audio_mp3",
      "status": "pending"
    }
  ],

  "outputs": null
}
```

**Response when completed (200 OK):**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "completed",
  "progress_percent": 100,
  "priority": 5,
  "created_at": "2025-11-18T14:30:22Z",
  "completed_at": "2025-11-18T15:15:45Z",
  "processing_time_seconds": 2723,

  "user_metadata": {
    "title": "My Awesome Video",
    "description": "A detailed description",
    "tags": ["tutorial", "programming"],
    "category": "education"
  },

  "video_info": {
    "filename": "video.mp4",
    "duration": 3600.5,
    "resolution": "1920x1080",
    "width": 1920,
    "height": 1080,
    "size_mb": 2048,
    "format": "mp4",
    "codec": "h264",
    "bitrate": 5000000,
    "fps": 30,
    "audio_codec": "aac",
    "audio_bitrate": 128000,
    "audio_sample_rate": 48000
  },

  "outputs": {
    "360p": {
      "video": {
        "url": "http://localhost/videos/processed/550e8400.../360p/video_360p.mp4",
        "minio_path": "videos/processed/550e8400.../360p/video_360p.mp4",
        "size_mb": 256,
        "resolution": "640x360",
        "bitrate": 800000,
        "processing_time_seconds": 450
      },
      "streaming": {
        "hls_url": "http://localhost/videos/processed/550e8400.../360p/segments/playlist.m3u8",
        "segment_count": 360,
        "segment_duration": 10,
        "total_segments_size_mb": 258
      }
    },
    "720p": {
      "video": {
        "url": "http://localhost/videos/processed/550e8400.../720p/video_720p.mp4",
        "minio_path": "videos/processed/550e8400.../720p/video_720p.mp4",
        "size_mb": 768,
        "resolution": "1280x720",
        "bitrate": 2500000,
        "processing_time_seconds": 1800
      },
      "streaming": {
        "hls_url": "http://localhost/videos/processed/550e8400.../720p/segments/playlist.m3u8",
        "segment_count": 360,
        "segment_duration": 10,
        "total_segments_size_mb": 772
      }
    },
    "audio": {
      "url": "http://localhost/videos/processed/550e8400.../audio/audio.mp3",
      "minio_path": "videos/processed/550e8400.../audio/audio.mp3",
      "size_mb": 86,
      "bitrate": 192000,
      "sample_rate": 48000,
      "processing_time_seconds": 120
    },
    "transcription": {
      "text": {
        "url": "http://localhost/videos/processed/550e8400.../transcription/transcript.txt",
        "minio_path": "videos/processed/550e8400.../transcription/transcript.txt",
        "size_bytes": 12456,
        "word_count": 2341
      },
      "srt": {
        "url": "http://localhost/videos/processed/550e8400.../transcription/transcript.srt",
        "minio_path": "videos/processed/550e8400.../transcription/transcript.srt",
        "size_bytes": 15234
      },
      "vtt": {
        "url": "http://localhost/videos/processed/550e8400.../transcription/transcript.vtt",
        "minio_path": "videos/processed/550e8400.../transcription/transcript.vtt",
        "size_bytes": 15567
      },
      "json": {
        "url": "http://localhost/videos/processed/550e8400.../transcription/transcript.json",
        "minio_path": "videos/processed/550e8400.../transcription/transcript.json",
        "size_bytes": 45789
      },
      "language": "en",
      "whisper_model": "base",
      "processing_time_seconds": 180
    },
    "thumbnails": {
      "custom": {
        "url": "http://localhost/videos/processed/550e8400.../thumbnails/thumb_custom.jpg",
        "minio_path": "videos/processed/550e8400.../thumbnails/thumb_custom.jpg",
        "size_bytes": 128456,
        "source": "user_uploaded",
        "is_primary": true
      },
      "auto_generated": [
        {
          "position_percent": 0,
          "timestamp": "00:00:00",
          "url": "http://localhost/videos/processed/550e8400.../thumbnails/thumb_00.jpg"
        },
        {
          "position_percent": 25,
          "timestamp": "00:15:00",
          "url": "http://localhost/videos/processed/550e8400.../thumbnails/thumb_25.jpg"
        },
        {
          "position_percent": 50,
          "timestamp": "00:30:00",
          "url": "http://localhost/videos/processed/550e8400.../thumbnails/thumb_50.jpg"
        },
        {
          "position_percent": 75,
          "timestamp": "00:45:00",
          "url": "http://localhost/videos/processed/550e8400.../thumbnails/thumb_75.jpg"
        },
        {
          "position_percent": 100,
          "timestamp": "01:00:00",
          "url": "http://localhost/videos/processed/550e8400.../thumbnails/thumb_100.jpg"
        }
      ]
    },
    "metadata_json": {
      "url": "http://localhost/videos/processed/550e8400.../metadata.json",
      "minio_path": "videos/processed/550e8400.../metadata.json"
    }
  },

  "compression": {
    "360p_ratio": 7.99,
    "720p_ratio": 2.67,
    "total_saved_percent": 48.5
  }
}
```

---

#### GET /api/v1/jobs
**Description:** List jobs with filtering

**Query Parameters:**
```
status: pending|processing|completed|failed
limit: 50 (default)
offset: 0 (default)
sort: created_at (default) | completed_at | priority
order: desc (default) | asc
```

**Response (200 OK):**
```json
{
  "total": 1523,
  "limit": 50,
  "offset": 0,
  "jobs": [
    {
      "job_id": "...",
      "status": "completed",
      "progress_percent": 100,
      "created_at": "...",
      "completed_at": "..."
    }
  ]
}
```

---

#### DELETE /api/v1/jobs/{job_id}
**Description:** Cancel pending/processing job

**Response (200 OK):**
```json
{
  "message": "Job cancelled successfully",
  "job_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

---

#### GET /api/v1/stats
**Description:** Get processing statistics

**Response (200 OK):**
```json
{
  "total_jobs": 1523,
  "pending": 12,
  "processing": 8,
  "completed": 1480,
  "failed": 23,
  "total_input_tb": 1.87,
  "total_output_tb": 0.95,
  "avg_processing_time_minutes": 45,
  "worker_utilization_percent": 87.5
}
```

---

#### POST /api/v1/admin/api-keys
**Description:** Generate new API key (admin only)

**Request:**
```json
{
  "name": "Production App",
  "rate_limit_per_hour": 500
}
```

**Response (201 Created):**
```json
{
  "api_key": "sk_live_abc123...",
  "name": "Production App",
  "rate_limit_per_hour": 500,
  "created_at": "2025-11-18T15:00:00Z",
  "warning": "Save this key securely - it won't be shown again"
}
```

---

## 5. Monitoring & Observability

### 5.1 Prometheus Metrics

#### Application Metrics
```
# Jobs
transcode_jobs_total{status="completed|failed|cancelled"}
transcode_jobs_duration_seconds{resolution="360p|720p"}
transcode_jobs_queue_size

# Processing
transcode_input_bytes_total
transcode_output_bytes_total{resolution="360p|720p|audio"}
transcode_processing_time_seconds

# API
api_requests_total{endpoint="/jobs/upload",status="200|400|500"}
api_request_duration_seconds{endpoint}
api_rate_limit_exceeded_total

# Workers
celery_worker_tasks_active
celery_worker_tasks_processed_total
celery_worker_pool_utilization_percent

# Storage
minio_bucket_size_bytes{bucket}
minio_objects_count{bucket}
```

#### System Metrics
```
# CPU
node_cpu_usage_percent
process_cpu_percent{service="celery-worker|fastapi"}

# Memory
node_memory_usage_bytes
process_memory_bytes{service}

# Disk
node_disk_usage_percent{mountpoint="/data"}
node_disk_io_bytes{operation="read|write"}

# Network
node_network_transmit_bytes_total
node_network_receive_bytes_total
```

### 5.2 Grafana Dashboards

**Dashboard 1: Job Overview**
- Jobs processed (24h/7d/30d)
- Success/failure rate
- Average processing time by resolution
- Queue size over time
- Worker utilization

**Dashboard 2: System Performance**
- CPU usage (per core)
- Memory usage
- Disk I/O
- Network throughput
- RAID status

**Dashboard 3: Storage Analytics**
- MinIO bucket sizes
- Input vs output storage ratio
- Storage growth rate
- Object count by bucket

**Dashboard 4: API Analytics**
- Requests per second
- Response time percentiles (p50, p95, p99)
- Error rate by endpoint
- Rate limit violations
- API key usage

### 5.3 Alerting Rules

```yaml
Alerts:
  - name: HighJobFailureRate
    condition: rate(jobs_failed_total[5m]) > 0.1
    severity: warning

  - name: WorkerDown
    condition: celery_workers_active < 1
    severity: critical

  - name: DiskSpaceLow
    condition: node_disk_usage_percent > 85
    severity: warning

  - name: HighMemoryUsage
    condition: node_memory_usage_percent > 90
    severity: critical

  - name: SlowProcessing
    condition: avg(transcode_duration_seconds) > 3600
    severity: warning

  - name: MinIODown
    condition: up{job="minio"} == 0
    severity: critical
```

---

## 6. Error Handling & Recovery

### 6.1 Error Categories

**Category 1: Validation Errors (4xx)**
- Invalid file format
- Corrupted file
- File too large (>20GB)
- Resolution too low (<360p)
- Missing file

**Action:** Return error immediately, no retry

**Category 2: Processing Errors (5xx - Retryable)**
- FFmpeg crash
- Temporary disk full
- Network timeout (MinIO upload)
- Worker crash

**Action:** Retry with exponential backoff (3 attempts)

**Category 3: System Errors (5xx - Critical)**
- Redis down
- PostgreSQL down
- MinIO down
- Out of memory

**Action:** Alert immediately, pause new jobs

### 6.2 Cleanup Strategy

**Temporary Files:**
```python
Cleanup Triggers:
1. On successful completion (after MinIO upload)
2. On job cancellation
3. On permanent failure (after max retries)
4. Scheduled cleanup cron (daily at 2 AM)
   - Remove temp files older than 24h
```

**Failed Jobs:**
```python
Retention Policy:
- Keep failed job records: 30 days
- Keep error logs: 90 days
- Delete source files: After 7 days (if uploaded via API)
```

---

## 7. Performance Optimization

### 7.1 FFmpeg Optimization

```bash
# Hardware acceleration (if available)
-hwaccel auto

# Multi-threading
-threads 0  # Auto-detect optimal thread count

# Preset tuning
-preset medium  # Balance speed/quality (fast|medium|slow)

# Two-pass encoding (optional for high quality)
Pass 1: -pass 1 -an -f null /dev/null
Pass 2: -pass 2 -c:a aac output.mp4
```

### 7.2 Worker Resource Allocation

```yaml
Celery Worker Configuration:
  concurrency: 8  # Match CPU threads
  max_tasks_per_child: 10  # Prevent memory leaks
  worker_prefetch_multiplier: 1  # Prevent task hoarding

Resource Limits per Task:
  max_memory: 8GB
  max_cpu_time: 4 hours
  max_temp_disk: 50GB
```

### 7.3 Database Optimization

```sql
-- Indexes
CREATE INDEX CONCURRENTLY idx_jobs_composite
  ON jobs(status, created_at DESC);

-- Partitioning (for large datasets)
CREATE TABLE jobs_2025_11 PARTITION OF jobs
  FOR VALUES FROM ('2025-11-01') TO ('2025-12-01');

-- Materialized view for stats
CREATE MATERIALIZED VIEW daily_stats AS
SELECT
  date_trunc('day', created_at) as day,
  status,
  count(*) as count,
  avg(processing_time_seconds) as avg_time
FROM jobs
GROUP BY 1, 2;

REFRESH MATERIALIZED VIEW CONCURRENTLY daily_stats;
```

### 7.4 MinIO Performance

```yaml
# Erasure coding disabled (single node)
# Use parallel uploads
mc mb --with-versioning myminio/video-source

# Lifecycle policies
mc ilm add --expiry-days 90 myminio/video-source

# Bucket notifications (optional)
mc event add myminio/video-source arn:minio:sqs::primary:postgresql \
  --event put
```

---

## 8. Security Requirements

### 8.1 API Key Management

```python
Requirements:
1. Keys hashed with SHA-256 before storage
2. Rate limiting: 100 requests/hour per key (configurable)
3. Key rotation support
4. Automatic key expiration (optional)
5. IP whitelist support (optional)
```

### 8.2 Network Security

```yaml
Docker Network Isolation:
  - Internal network: postgres, redis, minio (API)
  - External network: fastapi, nginx, minio (console)

Firewall Rules:
  - Allow: 80, 443, 8000, 8080, 9001, 3000, 9090, 5555
  - Deny: 5432, 6379, 9000 (from external)
```

### 8.3 Data Security

```
1. MinIO TLS encryption (optional)
2. PostgreSQL SSL connections
3. API HTTPS only (production)
4. Secrets management via .env file (not committed)
5. User uploads virus scanning (ClamAV - optional)
```

---

## 9. Deployment Strategy

### 9.1 Initial Setup

**IMPORTANT: Everything runs via Docker Compose - no manual installations needed!**
**DATA PERSISTENCE: All data stored in `/data/` on host - survives container restarts!**

```bash
Steps:
1. Clone repository to /home/transcode-flow
   git clone <repo> /home/transcode-flow
   cd /home/transcode-flow

2. Create persistent data directories on host filesystem
   # This is where ALL data will be stored (videos, database, etc.)
   sudo mkdir -p /data/{minio,postgres,prometheus,grafana,airflow/dags,airflow/logs,airflow/plugins,temp}
   sudo chown -R $USER:$USER /data
   sudo chmod -R 755 /data

   # Verify RAID 5 array is mounted at /data
   df -h /data
   # Expected output: ~4TB available on RAID 5 array

3. Configure .env file with secrets
   cp .env.example .env
   nano .env  # Update passwords and secrets

4. Build and start all services with Docker Compose
   # Application code runs in containers
   # Data is persisted to /data/ on host
   docker compose build
   docker compose up -d

5. Wait for services to initialize (30-60 seconds)
   docker compose ps  # Check all services are running

6. Initialize database schema
   docker compose exec fastapi python -m alembic upgrade head

7. Create MinIO buckets
   docker compose exec minio-init sh /init-buckets.sh

8. Create initial admin API key
   docker compose exec fastapi python -m scripts.create_api_key

9. Verify health checks
   curl http://localhost:8000/health
   curl http://localhost:9001  # MinIO Console
   curl http://localhost:8080  # Airflow UI

10. Access services:
    - FastAPI: http://localhost:8000/docs
    - Airflow: http://localhost:8080
    - MinIO Console: http://localhost:9001
    - Grafana: http://localhost:3000
    - Flower (Celery): http://localhost:5555
    - Prometheus: http://localhost:9090
```

**Required Host Dependencies:**
- Docker Engine 24.0+
- Docker Compose 2.20+
- Minimum 20GB free disk space
- Ubuntu 24.04 LTS (recommended)

**All application dependencies (FFmpeg, Whisper, Python packages, etc.) are containerized!**

### 9.2 Updating the Application

**Safe Update Process (Zero Data Loss):**
```bash
# 1. Pull latest code
cd /home/transcode-flow
git pull origin main

# 2. Rebuild containers (data stays in /data/)
docker compose build

# 3. Stop old containers, start new ones
docker compose down
docker compose up -d

# 4. Verify everything works
docker compose ps
curl http://localhost:8000/health

# Result: Application updated, all data preserved in /data/
```

**What Happens During Update:**
- ✅ Application code updated (new Docker images)
- ✅ Dependencies updated (FFmpeg, Whisper, Python packages)
- ✅ Configuration changes applied
- ❌ **NO DATA LOSS** - all videos, jobs, metrics preserved in `/data/`

**Rollback Process:**
```bash
# If update fails, rollback to previous version
git checkout <previous-commit>
docker compose build
docker compose up -d

# Data remains intact throughout rollback
```

### 9.3 Health Checks

```yaml
Health Endpoints:
  - GET /health (FastAPI)
  - GET /api/v1/health/db (Database)
  - GET /api/v1/health/redis (Redis)
  - GET /api/v1/health/minio (MinIO)
  - GET /api/v1/health/workers (Celery)

Expected Response:
{
  "status": "healthy",
  "services": {
    "database": "up",
    "redis": "up",
    "minio": "up",
    "workers": "8/8 active"
  },
  "timestamp": "2025-11-18T15:30:00Z"
}
```

### 9.3 Backup Strategy

**CRITICAL: All data lives in `/data/` - backup this directory!**

**Simple Backup Strategy:**
```bash
# Option 1: Backup entire /data/ directory (RECOMMENDED for small deployments)
tar -czf /backup/transcode-flow_$(date +%Y%m%d).tar.gz /data/

# Option 2: Rsync to remote server
rsync -avz --progress /data/ backup-server:/backups/transcode-flow/
```

**Granular Backup Strategy:**
```bash
# PostgreSQL backup (daily 3 AM)
docker exec postgres pg_dump -U airflow > /backup/db_$(date +%Y%m%d).sql

# MinIO videos backup (weekly - large files)
mc mirror /data/minio/videos /backup/minio/videos

# Airflow DAGs backup (git - hourly)
git -C /data/airflow/dags add . && git commit -m "Auto backup"

# Prometheus/Grafana config backup (daily)
tar -czf /backup/monitoring_$(date +%Y%m%d).tar.gz /data/prometheus /data/grafana
```

**Retention Policy:**
- PostgreSQL dumps: 30 days
- MinIO videos: 90 days (or longer based on business needs)
- Monitoring data: 30 days
- Airflow DAGs: Forever (git history)

**Restore Process:**
```bash
# Stop all containers
docker compose down

# Restore data
tar -xzf /backup/transcode-flow_20251118.tar.gz -C /

# Start containers
docker compose up -d

# Verify data integrity
docker compose exec fastapi python -m scripts.verify_data
```

**RAID 5 Protection:**
- `/data/` mounted on RAID 5 array (3x 2TB disks = 4TB usable)
- Survives single disk failure
- Regular RAID health monitoring required

### 9.4 Disaster Recovery

**Scenario 1: Container Failure**
```bash
# Single container crashed
docker compose restart <service-name>

# All containers crashed
docker compose restart

# Data is safe in /data/ - no data loss
```

**Scenario 2: Complete System Rebuild**
```bash
# New server setup
1. Install Ubuntu 24.04 + Docker + Docker Compose
2. Mount RAID 5 array at /data
3. Clone repository
4. Copy .env file
5. Run: docker compose up -d

# Result: System fully operational with all existing data
# Videos, jobs, metrics - everything preserved
```

**Scenario 3: RAID Disk Failure**
```bash
# Monitor RAID health
cat /proc/mdstat

# Single disk failure - RAID 5 continues working
# Replace failed disk and rebuild array
mdadm --manage /dev/md0 --add /dev/sdX

# No data loss, system stays online
```

**Scenario 4: Data Corruption**
```bash
# Restore from backup
docker compose down
rm -rf /data/*
tar -xzf /backup/transcode-flow_YYYYMMDD.tar.gz -C /
docker compose up -d
```

**Recovery Time Objectives (RTO):**
- Container restart: < 2 minutes
- Full system rebuild: < 30 minutes (excluding data copy)
- Backup restore: 1-4 hours (depends on data size)

**Recovery Point Objectives (RPO):**
- Database: 24 hours (daily backup)
- Videos: 7 days (weekly backup)
- DAGs: 0 (git versioned)

---

## 10. Testing Strategy

### 10.1 Unit Tests

```python
Test Coverage:
- Video validation logic
- FFmpeg command generation
- API key authentication
- Database models
- Celery task functions

Target: 80% code coverage
```

### 10.2 Integration Tests

```python
Test Scenarios:
1. End-to-end job processing (small video)
2. Invalid file upload handling
3. Worker crash recovery
4. MinIO connection failure
5. Database connection failure
6. API rate limiting
7. Concurrent job processing (8 workers)
```

### 10.3 Load Testing

```bash
# Locust test script
- Simulate 100 concurrent uploads
- Test API throughput (1000 req/s)
- Measure p99 latency
- Monitor worker queue depth
- Verify no memory leaks (24h test)

Target Performance:
- API p99 latency: < 500ms
- Job completion rate: > 95%
- Worker utilization: 70-90%
```

---

## 11. Documentation Requirements

### 11.1 API Documentation
- OpenAPI/Swagger spec
- Interactive API docs (FastAPI auto-generated)
- Authentication guide
- Rate limiting details
- Error code reference

### 11.2 Operations Manual
- Installation guide
- Configuration reference
- Troubleshooting guide
- Scaling guide
- Backup/restore procedures

### 11.3 Developer Guide
- Architecture overview
- DAG development guide
- Adding new resolutions
- Custom task development
- Testing guide

---

## 12. Future Enhancements (Post-MVP)

### Phase 2 (Optional)
- [ ] Thumbnail generation at multiple timestamps
- [ ] Subtitle extraction and burning
- [ ] Watermark insertion
- [ ] 4K (2160p) support
- [ ] Hardware acceleration (NVENC/QSV)
- [ ] Multi-language audio track support

### Phase 3 (Scaling)
- [ ] Multi-node worker deployment
- [ ] MinIO distributed mode (4+ nodes)
- [ ] CDN integration (CloudFront/CloudFlare)
- [ ] Webhook callbacks on job completion
- [ ] WebSocket real-time progress updates
- [ ] S3-compatible source support (AWS S3, GCS)

### Phase 4 (Advanced)
- [ ] AI-based quality enhancement
- [ ] Automated content moderation
- [ ] Scene detection and chapter markers
- [ ] Cost estimation before processing
- [ ] Batch job scheduling

---

## 13. Success Criteria

### MVP Launch Requirements
- ✅ All 8 workers processing in parallel
- ✅ 360p + 720p + MP3 outputs generated
- ✅ MinIO storage organized correctly
- ✅ API authentication working
- ✅ Job status API functional
- ✅ Prometheus + Grafana dashboards live
- ✅ NGINX streaming HLS playback works
- ✅ Error handling and retries working
- ✅ Database schema complete
- ✅ Documentation complete

### Performance Benchmarks
- Process 10GB video in < 60 minutes (720p)
- Handle 100 concurrent jobs in queue
- API response time < 200ms (p95)
- Zero data loss on worker crashes
- 99% uptime over 30 days

---

## 14. Project Timeline

```
Week 1: Infrastructure Setup
- Docker Compose configuration
- Service deployment
- Database setup
- MinIO configuration

Week 2: Core Development
- FastAPI endpoints
- Celery tasks
- Airflow DAGs
- Database integration

Week 3: Integration & Testing
- End-to-end testing
- Error handling
- Monitoring setup
- Load testing

Week 4: Optimization & Documentation
- Performance tuning
- Documentation
- Final testing
- Production deployment
```

---

## 15. Risks & Mitigation

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Disk space exhaustion | High | Medium | Monitoring alerts, auto-cleanup, disk quotas |
| Worker crashes | High | Low | Auto-restart, task retries, health checks |
| FFmpeg bugs | Medium | Low | Input validation, error handling, version pinning |
| MinIO corruption | High | Very Low | Regular backups, RAID 5 protection |
| API abuse | Medium | Medium | Rate limiting, API key monitoring |
| Memory leaks | Medium | Low | Worker restarts, memory limits, monitoring |
| Network saturation | Low | Low | QoS settings, bandwidth monitoring |

---

## Appendix A: Environment Variables

```bash
# .env.example

# General
COMPOSE_PROJECT_NAME=transcode-flow
TZ=UTC

# PostgreSQL
POSTGRES_USER=airflow
POSTGRES_PASSWORD=<CHANGE_ME>
POSTGRES_DB=airflow
POSTGRES_PORT=5432

# Redis
REDIS_PORT=6379

# Airflow
AIRFLOW__CORE__EXECUTOR=CeleryExecutor
AIRFLOW__CORE__SQL_ALCHEMY_CONN=postgresql+psycopg2://airflow:<CHANGE_ME>@postgres:5432/airflow
AIRFLOW__CELERY__BROKER_URL=redis://redis:6379/0
AIRFLOW__CELERY__RESULT_BACKEND=db+postgresql://airflow:<CHANGE_ME>@postgres:5432/airflow
AIRFLOW__CORE__FERNET_KEY=<GENERATE_KEY>
AIRFLOW__CORE__DAGS_ARE_PAUSED_AT_CREATION=true
AIRFLOW__CORE__LOAD_EXAMPLES=false
AIRFLOW__API__AUTH_BACKENDS=airflow.api.auth.backend.basic_auth
AIRFLOW_UID=1000

# Celery
CELERY_CONCURRENCY=8

# MinIO
MINIO_ROOT_USER=admin
MINIO_ROOT_PASSWORD=<CHANGE_ME_MIN_8_CHARS>
MINIO_PORT=9000
MINIO_CONSOLE_PORT=9001

# FastAPI
API_SECRET_KEY=<GENERATE_SECRET>
API_ADMIN_KEY=<GENERATE_ADMIN_KEY>
DATABASE_URL=postgresql://airflow:<CHANGE_ME>@postgres:5432/airflow

# NGINX
NGINX_HTTP_PORT=80
NGINX_HTTPS_PORT=443

# Monitoring
PROMETHEUS_PORT=9090
GRAFANA_PORT=3000
GRAFANA_ADMIN_PASSWORD=<CHANGE_ME>

# Flower (Celery monitoring)
FLOWER_PORT=5555
FLOWER_BASIC_AUTH=admin:<CHANGE_ME>
```

---

## Appendix B: FFmpeg Quality Presets

```bash
# Ultra Fast (draft quality)
-preset ultrafast -crf 28

# Fast (good for previews)
-preset fast -crf 25

# Medium (balanced - RECOMMENDED)
-preset medium -crf 23

# Slow (high quality)
-preset slow -crf 20

# Very Slow (maximum quality)
-preset veryslow -crf 18
```

---

## 16. Sprint Planning & Implementation Roadmap

**Note:** Detailed sprint documents are available in [docs/sprints/](./sprints/) directory.

### Overview

| Sprint | Duration | Focus | Document |
|--------|----------|-------|----------|
| Sprint 0 | Week 1 | Infrastructure Setup | [sprint-0-infrastructure.md](./sprints/sprint-0-infrastructure.md) |
| Sprint 1 | Week 2 | Core API & Video Validation | [sprint-1-api-validation.md](./sprints/sprint-1-api-validation.md) |
| Sprint 2 | Week 3 | Airflow DAG & Celery Workers | [sprint-2-airflow-celery.md](./sprints/sprint-2-airflow-celery.md) |
| Sprint 3 | Week 4 | FFmpeg & Whisper Integration | [sprint-3-ffmpeg-whisper.md](./sprints/sprint-3-ffmpeg-whisper.md) |
| Sprint 4 | Week 5 | Storage & File Management | [sprint-4-storage.md](./sprints/sprint-4-storage.md) |
| Sprint 5 | Week 6 | Job Status & Monitoring APIs | [sprint-5-monitoring-apis.md](./sprints/sprint-5-monitoring-apis.md) |
| Sprint 6 | Week 7 | Monitoring & Observability | [sprint-6-observability.md](./sprints/sprint-6-observability.md) |
| Sprint 7 | Week 8 | NGINX Streaming & API Keys | [sprint-7-nginx-api-keys.md](./sprints/sprint-7-nginx-api-keys.md) |
| Sprint 8 | Week 9 | Testing & Performance | [sprint-8-testing.md](./sprints/sprint-8-testing.md) |
| Sprint 9 | Week 10 | Documentation & Deployment | [sprint-9-deployment.md](./sprints/sprint-9-deployment.md) |
| Sprint 10 | Week 11-12 | Production Hardening | [sprint-10-production.md](./sprints/sprint-10-production.md) |

---

### Sprint 0: Infrastructure Setup (Week 1)
**Goal:** Set up the basic infrastructure and development environment

**Tasks:**
- [ ] Create project repository structure
- [ ] Set up Docker Compose configuration
- [ ] Configure environment variables (.env)
- [ ] Deploy PostgreSQL container and initialize database
- [ ] Deploy Redis container for Celery
- [ ] Deploy MinIO container and create buckets
- [ ] Set up basic NGINX configuration
- [ ] Create initial database schema (jobs, tasks, api_keys, usage_stats)
- [ ] Set up Prometheus and Grafana containers
- [ ] Verify all services are running and communicating

**Deliverables:**
- Working Docker Compose environment
- All services running and accessible
- Database schema created
- MinIO buckets configured

**Acceptance Criteria:**
- `docker compose up -d` starts all services without errors
- Health checks pass for all services
- Can connect to PostgreSQL, Redis, and MinIO
- Grafana accessible at http://localhost:3000

---

### Sprint 1: Core API & Video Validation (Week 2)
**Goal:** Build the FastAPI application with video upload and validation

**Tasks:**
- [ ] Set up FastAPI application structure
- [ ] Implement API key authentication middleware
- [ ] Create POST /api/v1/jobs/upload endpoint
- [ ] Create POST /api/v1/jobs/filesystem endpoint
- [ ] Create POST /api/v1/jobs/minio endpoint
- [ ] Implement video validation logic using FFprobe
- [ ] Add custom thumbnail upload support
- [ ] Implement user metadata validation and sanitization
- [ ] Create database models (SQLAlchemy)
- [ ] Add OpenAPI/Swagger documentation
- [ ] Write unit tests for validation logic
- [ ] Implement rate limiting

**Deliverables:**
- Working FastAPI application
- All upload endpoints functional
- Video validation working
- API documentation available

**Acceptance Criteria:**
- Can upload video via API and receive job_id
- Invalid videos are rejected with clear error messages
- API documentation accessible at http://localhost:8000/docs
- Rate limiting works correctly
- Custom thumbnails can be uploaded

---

### Sprint 2: Airflow DAG & Celery Workers (Week 3)
**Goal:** Implement the transcoding pipeline orchestration

**Tasks:**
- [ ] Set up Airflow webserver and scheduler
- [ ] Create video_transcoding_pipeline DAG
- [ ] Implement validate_video task
- [ ] Implement upload_to_minio task
- [ ] Implement generate_thumbnail task (5 auto-generated)
- [ ] Implement process_custom_thumbnail task
- [ ] Implement transcode_360p task
- [ ] Implement transcode_720p task
- [ ] Implement extract_audio_mp3 task
- [ ] Implement transcribe_video task (Whisper: TXT, SRT, VTT, JSON)
- [ ] Implement prepare_hls_360p task
- [ ] Implement prepare_hls_720p task
- [ ] Implement upload_outputs task
- [ ] Implement update_database task
- [ ] Implement cleanup_temp_files task
- [ ] Configure Celery workers (concurrency=8)
- [ ] Set up task retry policies
- [ ] Add progress tracking updates
- [ ] Deploy Flower for Celery monitoring

**Deliverables:**
- Complete Airflow DAG
- All tasks implemented
- Celery workers processing jobs
- Flower dashboard accessible

**Acceptance Criteria:**
- DAG visible in Airflow UI
- Can trigger manual DAG runs
- Jobs process from upload to completion
- Progress updates visible in database
- Worker utilization visible in Flower

---

### Sprint 3: FFmpeg & Whisper Integration (Week 4)
**Goal:** Implement video transcoding and transcription with FFmpeg and Whisper

**Tasks:**
- [ ] Optimize FFmpeg commands for 360p transcoding
- [ ] Optimize FFmpeg commands for 720p transcoding
- [ ] Implement HLS segmentation for streaming
- [ ] Implement MP3 audio extraction
- [ ] Set up Whisper in Docker container
- [ ] Implement Whisper transcription (TXT, SRT, VTT, JSON)
- [ ] Add automatic Whisper model selection based on duration
- [ ] Implement language detection and override
- [ ] Add FFmpeg progress tracking (percentage)
- [ ] Add Whisper progress tracking
- [ ] Implement resolution detection and conditional transcoding
- [ ] Add compression ratio calculation
- [ ] Add quality metrics (PSNR, SSIM - optional)
- [ ] Implement error handling for FFmpeg/Whisper failures
- [ ] Add timeout handling for long videos
- [ ] Optimize for multi-threading
- [ ] Test with various video formats
- [ ] Test transcription accuracy across languages
- [ ] Performance benchmarking

**Deliverables:**
- Working FFmpeg transcoding
- Working Whisper transcription
- HLS streaming segments generated
- Audio extraction working
- Subtitles generated (SRT, VTT)
- Progress tracking functional

**Acceptance Criteria:**
- 1080p video transcodes to 360p and 720p
- HLS playlists are valid and playable
- MP3 audio extracted correctly
- Transcription generates all 4 formats (TXT, SRT, VTT, JSON)
- Language auto-detection works correctly
- Processing time meets performance targets
- Handles various input formats (mp4, avi, mkv, etc.)
- Subtitles are properly timed and formatted

---

### Sprint 4: Storage & File Management (Week 5)
**Goal:** Implement hierarchical storage in MinIO

**Tasks:**
- [ ] Implement job folder creation in MinIO
- [ ] Upload original video to raw/ bucket
- [ ] Create processed/{job_id}/ folder structure
- [ ] Upload transcoded videos to MinIO
- [ ] Upload HLS segments to MinIO
- [ ] Upload thumbnails to MinIO
- [ ] Generate and upload metadata.json
- [ ] Implement cleanup of temp files
- [ ] Add error handling for MinIO upload failures
- [ ] Implement retry logic for failed uploads
- [ ] Add MinIO lifecycle policies
- [ ] Test storage hierarchy

**Deliverables:**
- Organized MinIO storage structure
- metadata.json generated correctly
- Temp files cleaned up

**Acceptance Criteria:**
- All outputs stored in correct MinIO paths
- metadata.json contains complete information
- Temp files removed after job completion
- Storage structure matches PRD specification

---

### Sprint 5: Job Status & Monitoring APIs (Week 6)
**Goal:** Build job status tracking and monitoring endpoints

**Tasks:**
- [ ] Implement GET /api/v1/jobs/{job_id} endpoint
- [ ] Implement GET /api/v1/jobs (list with filters)
- [ ] Implement DELETE /api/v1/jobs/{job_id} (cancel)
- [ ] Implement GET /api/v1/stats endpoint
- [ ] Add task-level progress tracking
- [ ] Implement webhook notifications (optional)
- [ ] Add detailed error messages in responses
- [ ] Implement job search by metadata
- [ ] Add pagination for job listings
- [ ] Create health check endpoints
- [ ] Add segment count to responses
- [ ] Include compression ratios in responses

**Deliverables:**
- Complete job status API
- Statistics endpoint working
- Job cancellation functional

**Acceptance Criteria:**
- Can query job status and see progress
- Task-level details visible
- Can filter jobs by status
- Statistics accurate
- Completed jobs show all output URLs

---

### Sprint 6: Monitoring & Observability (Week 7)
**Goal:** Implement comprehensive monitoring with Prometheus and Grafana

**Tasks:**
- [ ] Implement Prometheus metrics exporters
- [ ] Add application metrics (jobs, processing time, etc.)
- [ ] Add system metrics (CPU, memory, disk)
- [ ] Add MinIO metrics
- [ ] Add Celery metrics
- [ ] Create "Job Overview" Grafana dashboard
- [ ] Create "System Performance" Grafana dashboard
- [ ] Create "Storage Analytics" Grafana dashboard
- [ ] Create "API Analytics" Grafana dashboard
- [ ] Configure Prometheus alerting rules
- [ ] Set up alert notifications (optional)
- [ ] Add logging with structured logs
- [ ] Implement log aggregation

**Deliverables:**
- Prometheus collecting metrics
- 4 Grafana dashboards operational
- Alerting rules configured

**Acceptance Criteria:**
- All metrics visible in Prometheus
- Dashboards show real-time data
- Alerts trigger correctly
- Can troubleshoot issues using dashboards

---

### Sprint 7: NGINX Streaming & API Key Management (Week 8)
**Goal:** Set up NGINX for HLS streaming and admin API

**Tasks:**
- [ ] Configure NGINX for HLS streaming
- [ ] Set up NGINX location blocks for MinIO
- [ ] Add CORS headers for streaming
- [ ] Test HLS playback in browser
- [ ] Implement POST /api/v1/admin/api-keys endpoint
- [ ] Implement GET /api/v1/admin/api-keys endpoint
- [ ] Implement DELETE /api/v1/admin/api-keys/{id}
- [ ] Add API key hashing (SHA-256)
- [ ] Implement key rotation
- [ ] Add usage statistics tracking
- [ ] Create admin authentication
- [ ] Test rate limiting per API key

**Deliverables:**
- Working HLS streaming via NGINX
- Admin API for key management
- Usage stats tracking

**Acceptance Criteria:**
- Can play HLS streams in video player
- Can create and revoke API keys
- Rate limiting enforced per key
- Usage stats accurate

---

### Sprint 8: Testing & Performance Optimization (Week 9)
**Goal:** Comprehensive testing and performance tuning

**Tasks:**
- [ ] Write unit tests (target 80% coverage)
- [ ] Write integration tests
- [ ] End-to-end testing with real videos
- [ ] Load testing with Locust (100 concurrent uploads)
- [ ] Performance profiling
- [ ] Database query optimization
- [ ] FFmpeg command optimization
- [ ] Worker concurrency tuning
- [ ] Memory leak detection
- [ ] Disk I/O optimization
- [ ] Test error recovery scenarios
- [ ] Test worker crash recovery
- [ ] Test MinIO failure scenarios
- [ ] Benchmark processing times

**Deliverables:**
- Test suite with 80% coverage
- Load testing results
- Performance optimization report

**Acceptance Criteria:**
- All tests passing
- API p99 latency < 500ms
- Job completion rate > 95%
- Worker utilization 70-90%
- No memory leaks detected

---

### Sprint 9: Documentation & Deployment (Week 10)
**Goal:** Complete documentation and production deployment

**Tasks:**
- [ ] Write API documentation
- [ ] Write operations manual
- [ ] Write developer guide
- [ ] Create troubleshooting guide
- [ ] Write deployment guide
- [ ] Create backup/restore procedures
- [ ] Set up production environment
- [ ] Configure production secrets
- [ ] Set up SSL/TLS certificates
- [ ] Configure production monitoring
- [ ] Run production smoke tests
- [ ] Create runbooks for common issues
- [ ] Document scaling procedures
- [ ] Create video tutorials (optional)

**Deliverables:**
- Complete documentation
- Production deployment
- Runbooks for operations

**Acceptance Criteria:**
- All documentation complete and accurate
- Production system operational
- Monitoring and alerting working
- Team trained on operations

---

### Sprint 10: Polish & Production Hardening (Week 11-12)
**Goal:** Final polish and production readiness

**Tasks:**
- [ ] Security audit
- [ ] Performance review
- [ ] Code review and refactoring
- [ ] Fix any remaining bugs
- [ ] Implement additional error handling
- [ ] Add input validation improvements
- [ ] Optimize database queries
- [ ] Add additional logging
- [ ] Implement graceful shutdown
- [ ] Add health check improvements
- [ ] Test disaster recovery
- [ ] Load test with production-like data
- [ ] User acceptance testing
- [ ] Create release notes
- [ ] Plan for future enhancements

**Deliverables:**
- Production-ready system
- Security audit passed
- Performance targets met

**Acceptance Criteria:**
- All critical bugs fixed
- Security best practices implemented
- Performance benchmarks met
- System stable under load
- Ready for production traffic

---

### Post-MVP Roadmap

**Phase 2 (Months 3-4):**
- Multiple thumbnail timestamps (configurable)
- Subtitle extraction and burning
- Watermark insertion
- 4K (2160p) support
- Hardware acceleration (NVENC/QSV)
- Multi-language audio tracks

**Phase 3 (Months 5-6):**
- Multi-node worker deployment
- MinIO distributed mode
- CDN integration
- WebSocket real-time updates
- Batch job scheduling
- Advanced analytics

**Phase 4 (Months 7+):**
- AI-based quality enhancement
- Content moderation
- Scene detection
- Cost estimation
- Multi-region deployment

---

**Document Status:** Ready for Implementation
**Next Steps:** Begin Sprint 0 - Infrastructure Setup
