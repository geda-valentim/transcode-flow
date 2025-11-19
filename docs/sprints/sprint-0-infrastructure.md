# Sprint 0: Infrastructure Setup (Week 1)

**Goal:** Set up the basic infrastructure and development environment

**Duration:** 1 week
**Team Size:** 1-2 developers

---

## Tasks

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

---

## Deliverables

- ✅ Working Docker Compose environment
- ✅ All services running and accessible
- ✅ Database schema created
- ✅ MinIO buckets configured

---

## Acceptance Criteria

- [ ] `docker compose up -d` starts all services without errors
- [ ] Health checks pass for all services
- [ ] Can connect to PostgreSQL, Redis, and MinIO
- [ ] Grafana accessible at http://localhost:3000
- [ ] MinIO Console accessible at http://localhost:9001
- [ ] All data directories created in `/data/`

---

## Technical Details

### Docker Compose Services

```yaml
services:
  - postgres (PostgreSQL latest)
  - redis (Redis latest)
  - minio (MinIO latest)
  - nginx (NGINX latest)
  - prometheus (Prometheus latest)
  - grafana (Grafana latest)
```

### Data Directories to Create

```bash
/data/
├── minio/
├── postgres/
├── prometheus/
├── grafana/
├── airflow/
│   ├── dags/
│   ├── logs/
│   └── plugins/
└── temp/
```

### Environment Variables Required

```bash
# PostgreSQL
POSTGRES_USER=airflow
POSTGRES_PASSWORD=<secure_password>
POSTGRES_DB=airflow

# MinIO
MINIO_ROOT_USER=admin
MINIO_ROOT_PASSWORD=<secure_password>

# Redis
REDIS_PORT=6379

# Grafana
GRAFANA_ADMIN_PASSWORD=<secure_password>
```

### Database Schema Files

Create migration files:
- `migrations/001_create_jobs_table.sql`
- `migrations/002_create_tasks_table.sql`
- `migrations/003_create_api_keys_table.sql`
- `migrations/004_create_usage_stats_table.sql`

---

## Testing Checklist

- [ ] PostgreSQL accessible: `docker exec postgres psql -U airflow -d airflow -c "SELECT 1;"`
- [ ] Redis accessible: `docker exec redis redis-cli ping`
- [ ] MinIO accessible: `curl http://localhost:9001`
- [ ] Prometheus accessible: `curl http://localhost:9090/-/healthy`
- [ ] Grafana accessible: `curl http://localhost:3000/api/health`
- [ ] NGINX accessible: `curl http://localhost:80`

---

## Notes

- **Data Persistence:** All data must be stored in `/data/` on host
- **Docker Compose:** Everything runs via docker compose - no manual installs
- **RAID 5:** Verify `/data/` is mounted on RAID 5 array (4TB usable)

---

## Next Sprint

Sprint 1: Core API & Video Validation
