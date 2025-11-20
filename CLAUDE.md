# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Transcode Flow is an event-driven video processing platform that applies modern data engineering principles (Apache Airflow, Celery, FastAPI) to video transcoding workflows. The system processes videos through a DAG-based pipeline that handles validation, multi-resolution transcoding, HLS segmentation, audio extraction, AI transcription, and storage in MinIO (S3-compatible).

## Essential Commands

### Quick Start
```bash
make init           # First-time setup (copies .env, builds, starts, migrates)
make up             # Start all services
make down           # Stop all services
make health         # Check all services health status
```

### Development Workflow
```bash
make logs           # View all logs
make logs-api       # FastAPI logs only
make logs-worker    # Celery worker logs
make ps             # Show running containers
make restart        # Restart all services
```

### Database Operations
```bash
make migrate        # Run SQL migrations from migrations/versions/
make backup         # Create timestamped DB backup in data/backups/
make restore FILE=backup.sql.gz  # Restore from backup
make shell-pg       # Access PostgreSQL shell
```

### Testing & Code Quality
```bash
make test           # Run pytest inside fastapi container
make test-cov       # Run tests with coverage report
make lint           # Run flake8
make format         # Run black + isort
```

### Service Access Shells
```bash
make shell-api      # Access FastAPI container bash
make shell-redis    # Access Redis CLI
```

### Manual Pipeline Trigger
```bash
./trigger.sh /path/to/video.mp4 --priority 8
# Script reads credentials from .env, creates job in DB
# Do NOT hardcode credentials in trigger.sh (loads from .env)
```

## Architecture Overview

### Service Layer (Docker Compose)
- **NGINX** (port 10080): Reverse proxy, rate limiting, routing
- **FastAPI** (port 18000): REST API, async endpoints, Prometheus metrics
- **Airflow 3.0** (port 18080): DAG orchestration, task scheduling
- **Celery Workers**: Distributed task execution (FFmpeg, Whisper)
- **PostgreSQL** (port 15432): Job metadata, API keys, state management
- **Redis** (port 16379): Celery broker, caching
- **MinIO** (port 19000/19001): S3-compatible object storage (videos, outputs)
- **Prometheus** (port 19090) + **Grafana** (port 13000): Observability stack
- **Flower** (port 15555): Celery monitoring UI

All ports use 1xxxx range to avoid conflicts (see PORTS.md).

### Application Architecture

#### API Layer (`app/`)
- **main.py**: FastAPI app with lifespan events, CORS, metrics middleware
- **api/v1/endpoints/**: Modular endpoint structure
  - **jobs/**: Consolidated job endpoints package
    - `creation.py`: Upload endpoints (multipart, filesystem, MinIO)
    - `management.py`: Job control (status, cancel, retry, delete, priority)
    - `queries.py`: List, search, statistics
    - `export.py`: CSV/JSON export
    - `observability.py`: Real-time XCom metrics
  - `api_keys.py`: API key CRUD (admin endpoints)
  - `events.py`: Server-Sent Events for real-time job progress
  - `streaming.py`: HLS video streaming with token authentication
- **core/**: Configuration, security, logging, MinIO client, rate limiting, caching
- **models/**: SQLAlchemy ORM (Job, ApiKey)
- **schemas/**: Pydantic models for validation
- **services/**: Business logic (video validation, Whisper transcription, webhooks)
- **storage/**: MinIO operations (cleanup, deduplication, lifecycle, quotas, presigned URLs)
- **metrics/**: Prometheus metric definitions

#### Airflow DAGs (`data/airflow/dags/`)
- **video_transcoding_pipeline.py**: Main DAG with task dependency graph
  - Uses Airflow 3.0 context manager pattern (`with DAG`)
  - Triggered externally via API (schedule=None)
  - Max 8 concurrent runs, 3 retries with exponential backoff
- **transcode_pipeline/**: Modular task packages
  - `validation_tasks.py`: Video validation, thumbnail generation
  - `transcoding_tasks.py`: FFmpeg transcoding (360p, 720p), MP3 extraction, Whisper transcription
  - `hls_tasks.py`: HLS segmentation preparation
  - `storage_tasks.py`: MinIO upload operations
  - `database_tasks.py`: DB updates, temp file cleanup
  - `notification_tasks.py`: Webhook callbacks
- **storage_cleanup_pipeline.py**: Daily maintenance DAG (temp files, failed jobs, duplicates)

**Critical Pattern**: Tasks communicate via **XCom** (Airflow's inter-task data passing). When pulling XCom data, always specify `task_ids` parameter to avoid ambiguity:
```python
input_path = context['task_instance'].xcom_pull(
    key='360p_path',
    task_ids='transcode_360p'  # REQUIRED for clarity
)
```

#### Database Schema (`migrations/versions/`)
- **001_initial_schema.sql**: Jobs table with JSONB metadata, status enum
- **002_add_api_key_management_fields.sql**: API keys with quotas, rate limits, IP whitelist

### Data Flow Pattern

1. **Ingestion**: Client uploads video via `/api/v1/jobs/upload` with API key
2. **Validation**: FastAPI validates, creates DB job record
3. **Trigger**: API triggers Airflow DAG via internal API call
4. **Orchestration**: Airflow schedules tasks based on dependency graph
5. **Execution**: Celery workers execute tasks (FFmpeg/Whisper processing)
6. **Communication**: Tasks pass file paths via XCom
7. **Storage**: Processed outputs uploaded to MinIO buckets
8. **Notification**: Webhook sent on completion/failure
9. **Monitoring**: Prometheus scrapes metrics, Grafana visualizes

### Key Design Patterns

#### Event-Driven Architecture
- API triggers DAG runs dynamically (no cron scheduling)
- Server-Sent Events provide real-time progress updates
- Webhook callbacks for async notifications

#### Data Lake (Bronze/Silver/Gold)
- **Bronze**: `raw-videos/` - original uploads
- **Silver**: `processed-videos/` - transcoded outputs (360p, 720p, MP3, thumbnails)
- **Gold**: `hls-streams/` - HLS manifests and segments for CDN

#### Horizontal Scalability
- Add Celery workers with `docker compose up --scale celery-worker=N`
- Worker pools for CPU-intensive tasks
- Priority queues per API key

#### Fault Tolerance
- Automatic retries with exponential backoff (3 retries, 5-30 min delay)
- Idempotent tasks (safe to retry)
- XCom for stateful inter-task communication
- Database tracks job state transitions

## Configuration Files

### Environment Variables (.env)
**CRITICAL**: Never commit `.env`. Always use `.env.example` as template.
- Database credentials (POSTGRES_PASSWORD)
- MinIO credentials (MINIO_ROOT_PASSWORD)
- Airflow secrets (FERNET_KEY, JWT_SECRET)
- API secrets (SECRET_KEY)
- Grafana password (GRAFANA_ADMIN_PASSWORD)

### Docker Compose
- All services networked via `transcode-network`
- Volumes persist data in `./data/` subdirectories
- Healthchecks ensure proper startup order
- Airflow init container runs DB migrations

## Development Patterns

### Adding New Job Endpoints
1. Create module in `app/api/v1/endpoints/jobs/`
2. Define router with appropriate tags
3. Include router in `jobs/__init__.py`
4. Endpoint automatically inherits API key authentication from parent router

### Adding Airflow Tasks
1. Create task function in appropriate `transcode_pipeline/*.py` module
2. Import in `video_transcoding_pipeline.py`
3. Create PythonOperator with task_id
4. Define dependencies using `>>` operator
5. Use XCom for passing data: `context['ti'].xcom_push(key, value)` and `xcom_pull(key, task_ids)`

### Airflow 3.0 Migration Notes
- Use `with DAG(...)` context manager (not standalone `dag = DAG()`)
- Use `from airflow.providers.standard.operators.python import PythonOperator`
- Set `schedule=None` (not `schedule_interval=None`)
- Execution API requires JWT configuration in docker-compose.yml

### Working with XCom
Always specify source task when pulling to avoid ambiguous matches:
```python
# BAD - may pull from wrong task
value = ti.xcom_pull(key='some_key')

# GOOD - explicit source
value = ti.xcom_pull(key='some_key', task_ids='source_task_name')
```

### MinIO Client Usage
```python
from app.core.minio_client import get_minio_client

client = get_minio_client()
client.fput_object('videos', 'path/file.mp4', local_path)
url = client.presigned_get_object('videos', 'path/file.mp4', expires=timedelta(hours=1))
```

### Testing Video Pipeline
1. Ensure services running: `make health`
2. Get API key from database: `make shell-pg`, `SELECT * FROM api_keys;`
3. Upload test video: `curl -X POST http://localhost:10080/api/v1/jobs/upload -H "X-API-Key: tfk_..." -F "video_file=@test.mp4"`
4. Monitor in Airflow UI: http://localhost:18080/dags/video_transcoding_pipeline/grid
5. Watch logs: `make logs-worker`
6. Check XCom: Airflow UI → DAG Run → Task Instance → XCom tab

## Important Constraints

### Port Conflicts
All services use 1xxxx port range. If adding new services, follow this pattern.

### Path Translation (Host ↔ Container)
When triggering DAGs, translate paths:
- Host: `/home/transcode-flow/data/temp/video.mp4`
- Container: `/data/temp/video.mp4`
Handled automatically in `validation_tasks.py`.

### Credentials Security
`trigger.sh` loads credentials from `.env` - never hardcode passwords.

### Airflow Task Communication
Always use XCom with explicit `task_ids` to avoid pulling data from wrong tasks.

### Database Migrations
SQL migrations in `migrations/versions/` must be idempotent (use `IF NOT EXISTS`).

## File Organization Rules

### Documentation Placement
- **Root-level docs**: Only keep essential user-facing files (README.md, QUICKSTART.md, PORTS.md, CHANGELOG.md)
- **All other documentation**: Must be placed in `docs/` folder
- **Temporary/working docs**: Place in `docs/tmp/` (gitignored) unless specified otherwise
- **Technical notes**: (e.g., OBSERVABILITY_SUMMARY.md, TRANSCRIPTION_FIX.md, XCOM_OBSERVABILITY.md) should be moved to `docs/` or `docs/tmp/` depending on permanence

When creating new documentation files, always place them in `docs/` unless explicitly instructed to use a different location.

## Documentation References

- **QUICKSTART.md**: 5-minute setup guide
- **PORTS.md**: Complete port mapping and firewall rules
- **docs/PRD.md**: Product requirements document
- **docs/sprints/**: Implementation sprints breakdown
- **docs/TRIGGER_MANUAL.md**: Manual DAG triggering guide
- **docs/tmp/**: Temporary documentation and working notes (gitignored)
