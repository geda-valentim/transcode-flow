# Transcode Flow Documentation

Complete documentation for the Video Transcoding Service Platform.

---

## 📚 Documentation Structure

```
docs/
├── README.md                    # This file - documentation index
├── general_idea.txt             # Original project concept
├── PRD.md                       # Complete Product Requirements Document
└── sprints/                     # Sprint planning documents
    ├── README.md                # Sprint overview
    ├── sprint-0-infrastructure.md
    ├── sprint-1-api-validation.md
    ├── sprint-2-airflow-celery.md
    ├── sprint-3-ffmpeg-whisper.md  (to be created)
    ├── sprint-4-storage.md          (to be created)
    ├── sprint-5-monitoring-apis.md  (to be created)
    ├── sprint-6-observability.md    (to be created)
    ├── sprint-7-nginx-api-keys.md   (to be created)
    ├── sprint-8-testing.md          (to be created)
    ├── sprint-9-deployment.md       (to be created)
    └── sprint-10-production.md      (to be created)
```

---

## 🚀 Quick Start

### For Project Managers
Start with:
1. [PRD.md](./PRD.md) - Complete product requirements
2. [Sprint Overview](./sprints/README.md) - Sprint planning timeline

### For Developers
Start with:
1. [Sprint 0: Infrastructure Setup](./sprints/sprint-0-infrastructure.md)
2. [System Architecture](./PRD.md#2-system-architecture)
3. [API Specifications](./PRD.md#4-api-specifications)

### For DevOps/Infrastructure
Start with:
1. [Deployment Strategy](./PRD.md#9-deployment-strategy)
2. [Data Persistence](./PRD.md#25-data-persistence--volume-structure)
3. [Disaster Recovery](./PRD.md#94-disaster-recovery)

---

## 📖 Main Documents

### [PRD.md](./PRD.md) - Product Requirements Document
**Complete specification including:**

- **Executive Summary** - Project overview and objectives
- **System Architecture** - Technology stack and infrastructure
- **Data Persistence** - How data is stored in `/data/`
- **Functional Requirements** - Video processing pipeline
- **API Specifications** - REST API endpoints
- **Database Schema** - PostgreSQL tables and indexes
- **Monitoring** - Prometheus and Grafana setup
- **Deployment** - Docker Compose deployment guide
- **Testing Strategy** - Unit, integration, and load testing
- **Sprint Planning** - 10-sprint implementation roadmap

### [sprints/](./sprints/) - Sprint Planning Documents
**Detailed sprint breakdown:**

Each sprint includes:
- ✅ Goals and objectives
- ✅ Task checklist
- ✅ Deliverables
- ✅ Acceptance criteria
- ✅ Technical implementation details
- ✅ Testing requirements

---

## 🎯 Key Concepts

### Data Persistence Strategy

```
┌─────────────────────────────────────┐
│  HOST: /data/ (PERSISTENT)          │
│  ├── minio/    (videos)              │
│  ├── postgres/ (database)            │
│  ├── airflow/  (DAGs, logs)          │
│  └── ...                             │
│                                      │
│  ┌─────────────────────────────┐   │
│  │ DOCKER CONTAINERS           │   │
│  │ (stateless - can rebuild)   │   │
│  └─────────────────────────────┘   │
└─────────────────────────────────────┘
```

**Key Points:**
- ✅ **Apps run in Docker** (stateless, can be rebuilt)
- ✅ **Data lives in /data/** (persistent, never lost)
- ✅ **docker compose up -d** starts everything
- ✅ **Zero manual installations** on host

### Video Processing Pipeline

```
Upload → Validate → Transcode → Transcribe → Upload to MinIO → Complete
           │           │           │
           │           │           └─ Whisper (TXT, SRT, VTT, JSON)
           │           │
           │           └─ FFmpeg (360p, 720p, HLS, MP3)
           │
           └─ FFprobe (resolution, codec, duration)
```

### Technology Stack

| Layer | Technology |
|-------|------------|
| **API** | FastAPI + Uvicorn |
| **Orchestration** | Apache Airflow |
| **Queue** | Celery + Redis |
| **Storage** | MinIO (S3-compatible) |
| **Database** | PostgreSQL |
| **Transcoding** | FFmpeg |
| **Transcription** | OpenAI Whisper |
| **Streaming** | NGINX + HLS |
| **Monitoring** | Prometheus + Grafana |
| **Container** | Docker Compose |

---

## 🔧 Implementation Timeline

| Week | Sprint | Focus |
|------|--------|-------|
| 1 | Sprint 0 | Infrastructure Setup |
| 2 | Sprint 1 | Core API & Video Validation |
| 3 | Sprint 2 | Airflow DAG & Celery Workers |
| 4 | Sprint 3 | FFmpeg & Whisper Integration |
| 5 | Sprint 4 | Storage & File Management |
| 6 | Sprint 5 | Job Status & Monitoring APIs |
| 7 | Sprint 6 | Monitoring & Observability |
| 8 | Sprint 7 | NGINX Streaming & API Keys |
| 9 | Sprint 8 | Testing & Performance |
| 10 | Sprint 9 | Documentation & Deployment |
| 11-12 | Sprint 10 | Production Hardening |

**Total Timeline:** 12 weeks to production-ready system

---

## 📊 Project Highlights

### Features

- ✅ Multi-resolution transcoding (360p, 720p)
- ✅ HLS streaming preparation
- ✅ MP3 audio extraction
- ✅ Automatic transcription (90+ languages)
- ✅ Custom thumbnail support
- ✅ User metadata (JSONB)
- ✅ Hierarchical storage per video
- ✅ Real-time progress tracking
- ✅ API key authentication
- ✅ Rate limiting
- ✅ Comprehensive monitoring

### Performance Targets

- **Throughput:** 100GB/day minimum
- **Parallel Workers:** 8 concurrent jobs
- **API Latency:** < 200ms (p95)
- **Job Success Rate:** > 99%
- **Uptime:** 99% over 30 days

### Hardware Specs

- **CPU:** Intel Xeon-E3 1270 v6 (4c/8t)
- **RAM:** 64GB DDR4 ECC
- **Storage:** RAID 5 (3x 2TB = 4TB usable)
- **Network:** 500Mbit/s unmetered

---

## 🛠️ Development Workflow

### Setting Up Development Environment

```bash
# 1. Clone repository
git clone <repo> /home/transcode-flow
cd /home/transcode-flow

# 2. Create data directories
sudo mkdir -p /data/{minio,postgres,prometheus,grafana,airflow,temp}
sudo chown -R $USER:$USER /data

# 3. Configure environment
cp .env.example .env
nano .env  # Update passwords

# 4. Start all services
docker compose up -d

# 5. Verify health
docker compose ps
curl http://localhost:8000/health
```

### Working on a Sprint

```bash
# 1. Read sprint document
cat docs/sprints/sprint-X-name.md

# 2. Create feature branch
git checkout -b sprint-X-feature-name

# 3. Implement features
# ... coding ...

# 4. Run tests
docker compose exec fastapi pytest

# 5. Commit and push
git add .
git commit -m "Sprint X: Implement feature"
git push origin sprint-X-feature-name
```

---

## 📝 Additional Resources

### External Documentation

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Apache Airflow Docs](https://airflow.apache.org/docs/)
- [MinIO Documentation](https://min.io/docs/)
- [FFmpeg Documentation](https://ffmpeg.org/documentation.html)
- [OpenAI Whisper GitHub](https://github.com/openai/whisper)

### Best Practices

- **Code Style:** Follow PEP 8 for Python
- **Testing:** Minimum 80% code coverage
- **Documentation:** Update docs with code changes
- **Git:** Use conventional commits
- **Docker:** Always use bind mounts for data
- **Security:** Never commit secrets to git

---

## 🆘 Getting Help

### Common Issues

**Problem:** Services won't start
```bash
# Check logs
docker compose logs <service-name>

# Rebuild containers
docker compose down
docker compose build
docker compose up -d
```

**Problem:** Data lost after restart
```bash
# Verify volume mounts
docker compose config | grep volumes

# Check /data/ directory
ls -la /data/
```

**Problem:** Slow transcoding
```bash
# Check worker utilization
curl http://localhost:5555  # Flower dashboard

# Check system resources
docker stats
```

### Support Channels

1. Check [PRD.md](./PRD.md) for specifications
2. Review relevant [sprint documents](./sprints/)
3. Search existing issues on GitHub
4. Ask team lead for guidance

---

## 📄 License

This is an internal project document. All rights reserved.

---

**Last Updated:** 2025-11-18
**Version:** 1.0
**Status:** Ready for Implementation
