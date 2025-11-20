# 🚀 Transcode Flow - Quick Start

## 📋 Prerequisites

- Docker 20.10+
- Docker Compose 2.0+
- 100GB+ disk space
- 8GB+ RAM

## ⚡ Quick Setup (5 minutes)

### 1. Configure environment

```bash
# Copy configuration file
cp .env.example .env

# Edit passwords (IMPORTANT!)
nano .env
```

**⚠️ CHANGE THESE PASSWORDS:**
- POSTGRES_PASSWORD
- MINIO_ROOT_PASSWORD
- AIRFLOW__CORE__FERNET_KEY
- SECRET_KEY
- GRAFANA_ADMIN_PASSWORD

**💡 Tip:** Use `make init` for automatic setup!

### 2. Start the project

```bash
# Option 1: Automatic setup (recommended)
make init

# Option 2: Manual
docker compose up -d
make migrate
```

### 3. Check health

```bash
make health
```

## 🌐 Access Services

| Service | URL | Login |
|---------|-----|-------|
| **API Docs** | http://localhost:10080/docs | - |
| **Airflow** | http://localhost:18080 | admin / (password from .env) |
| **Grafana** | http://localhost:13000 | admin / (password from .env) |
| **MinIO Console** | http://localhost:19001 | admin / (password from .env) |
| **Flower** | http://localhost:15555 | admin / (password from .env) |
| **Prometheus** | http://localhost:19090 | - |

## 📝 Useful Commands

```bash
# View logs
make logs

# View API logs
make logs-api

# Stop everything
make down

# Restart
make restart

# Database backup
make backup

# Tests
make test

# Access API shell
make shell-api

# Access PostgreSQL
make shell-pg

# View all commands
make help
```

## ✅ Verification

### 1. Test API

```bash
curl http://localhost:10080/health
```

**Expected response:**
```json
{
  "status": "healthy",
  "service": "transcode-flow-api",
  "version": "1.0.0"
}
```

### 2. Check containers

```bash
docker compose ps
```

**All should be "Up" (healthy)**

### 3. Test database

```bash
docker compose exec postgres psql -U transcode_user -d transcode_db -c "SELECT COUNT(*) FROM api_keys;"
```

**Should return 1** (default API key)

## 🐛 Common Issues

### "Port already in use"

```bash
# Check what's using the port
sudo lsof -i :80

# Stop the service or change the port in docker-compose.yml
```

### "Cannot connect to Docker daemon"

```bash
# Start Docker
sudo systemctl start docker

# Or on WSL2
sudo service docker start
```

### "Out of disk space"

```bash
# Clean old containers
docker system prune -a

# Check disk space
df -h
```

## 📚 Next Steps

1. ✅ **Read documentation:** [docs/README.md](docs/README.md)
2. ✅ **Follow sprints:** [docs/sprints/](docs/sprints/)
3. ✅ **Sprint 1:** Implement upload API
4. ✅ **Sprint 2:** Configure Airflow DAG
5. ✅ **Sprint 3:** Integrate FFmpeg and Whisper

## 🔒 Security

**BEFORE GOING TO PRODUCTION:**

1. ✅ Change ALL default passwords
2. ✅ Configure SSL/TLS (Sprint 10)
3. ✅ Configure firewall
4. ✅ Enable automatic backups
5. ✅ Review API key permissions

## 📞 Need Help?

- 📖 [README.md](README.md) - Complete documentation
- 📋 [PRD.md](docs/PRD.md) - Requirements
- 🏃 [Sprints](docs/sprints/) - Planning
- 🐛 [Issues](https://github.com/geda-valentim/transcode-flow/issues)

---

**Happy Coding! 🎉**
