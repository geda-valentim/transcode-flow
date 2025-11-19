.PHONY: help init up down restart logs ps build clean backup restore test

# Default target
help:
	@echo "Transcode Flow - Available Commands:"
	@echo ""
	@echo "  make init       - Initialize project (first time setup)"
	@echo "  make up         - Start all services"
	@echo "  make down       - Stop all services"
	@echo "  make restart    - Restart all services"
	@echo "  make logs       - Show logs (all services)"
	@echo "  make logs-api   - Show FastAPI logs"
	@echo "  make logs-pg    - Show PostgreSQL logs"
	@echo "  make ps         - Show running containers"
	@echo "  make build      - Build/rebuild containers"
	@echo "  make clean      - Stop and remove all containers, volumes"
	@echo "  make backup     - Backup database"
	@echo "  make restore    - Restore database (use FILE=backup.sql.gz)"
	@echo "  make test       - Run tests"
	@echo "  make migrate    - Run database migrations"
	@echo "  make shell-api  - Access FastAPI container shell"
	@echo "  make shell-pg   - Access PostgreSQL shell"
	@echo "  make health     - Check health of all services"
	@echo ""

# Initialize project (first time setup)
init:
	@echo "Initializing Transcode Flow..."
	@if [ ! -f .env ]; then \
		cp .env.example .env; \
		echo "✅ Created .env file - PLEASE UPDATE PASSWORDS!"; \
	else \
		echo "⚠️  .env already exists, skipping..."; \
	fi
	@echo "Building containers..."
	@docker compose build
	@echo "Starting services..."
	@docker compose up -d
	@echo "Waiting for services to be ready..."
	@sleep 15
	@echo "Running database migrations..."
	@make migrate
	@echo ""
	@echo "✅ Initialization complete!"
	@echo ""
	@make health

# Start all services
up:
	docker compose up -d

# Stop all services
down:
	docker compose down

# Restart all services
restart:
	docker compose restart

# Show logs for all services
logs:
	docker compose logs -f --tail=100

# Show FastAPI logs
logs-api:
	docker compose logs -f --tail=100 fastapi

# Show PostgreSQL logs
logs-pg:
	docker compose logs -f --tail=100 postgres

# Show Celery worker logs
logs-worker:
	docker compose logs -f --tail=100 celery-worker

# Show running containers
ps:
	docker compose ps

# Build/rebuild containers
build:
	docker compose build

# Build without cache
build-no-cache:
	docker compose build --no-cache

# Stop and remove everything
clean:
	@echo "⚠️  This will remove all containers and volumes!"
	@read -p "Are you sure? [y/N] " -n 1 -r; \
	echo; \
	if [[ $$REPLY =~ ^[Yy]$$ ]]; then \
		docker compose down -v; \
		echo "✅ Cleaned up!"; \
	fi

# Backup database
backup:
	@mkdir -p data/backups
	@echo "Creating database backup..."
	@docker compose exec postgres pg_dump -U transcode_user transcode_db | gzip > data/backups/backup_$$(date +%Y%m%d_%H%M%S).sql.gz
	@echo "✅ Backup created: data/backups/backup_$$(date +%Y%m%d_%H%M%S).sql.gz"

# Restore database
restore:
	@if [ -z "$(FILE)" ]; then \
		echo "❌ Error: Please specify FILE=backup.sql.gz"; \
		exit 1; \
	fi
	@echo "Restoring database from $(FILE)..."
	@gunzip -c $(FILE) | docker compose exec -T postgres psql -U transcode_user -d transcode_db
	@echo "✅ Database restored from $(FILE)"

# Run tests
test:
	docker compose exec fastapi pytest

# Run tests with coverage
test-cov:
	docker compose exec fastapi pytest --cov=app --cov-report=html --cov-report=term

# Run database migrations
migrate:
	@echo "Running database migrations..."
	docker compose exec -T postgres psql -U transcode_user -d transcode_db < migrations/versions/001_initial_schema.sql
	@echo "✅ Migrations completed"

# Access FastAPI shell
shell-api:
	docker compose exec fastapi bash

# Access PostgreSQL shell
shell-pg:
	docker compose exec postgres psql -U transcode_user -d transcode_db

# Access Redis CLI
shell-redis:
	docker compose exec redis redis-cli

# Check health of all services
health:
	@echo "Checking service health..."
	@echo ""
	@echo "API Health:"
	@curl -s http://localhost:10080/health | python3 -m json.tool || echo "❌ API not responding"
	@echo ""
	@echo "Prometheus Health:"
	@curl -s http://localhost:19090/-/healthy || echo "❌ Prometheus not responding"
	@echo ""
	@echo "Grafana Health:"
	@curl -s http://localhost:13000/api/health | python3 -m json.tool || echo "❌ Grafana not responding"
	@echo ""
	@echo "MinIO Health:"
	@curl -s http://localhost:19000/minio/health/live || echo "❌ MinIO not responding"
	@echo ""
	@echo "Docker Compose Status:"
	@docker compose ps

# View API documentation
docs:
	@echo "Opening API documentation..."
	@xdg-open http://localhost:10080/docs 2>/dev/null || open http://localhost:10080/docs 2>/dev/null || echo "Visit: http://localhost:10080/docs"

# Update dependencies
update-deps:
	docker compose exec fastapi pip install --upgrade -r requirements.txt

# Format code
format:
	docker compose exec fastapi black app/
	docker compose exec fastapi isort app/

# Lint code
lint:
	docker compose exec fastapi flake8 app/
