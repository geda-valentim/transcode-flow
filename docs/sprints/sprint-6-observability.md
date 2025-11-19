# Sprint 6: Monitoring & Observability (Week 7)

**Goal:** Implement comprehensive monitoring, metrics, and observability

**Duration:** 1 week
**Team Size:** 2 developers

---

## Tasks

- [ ] Set up Prometheus metrics collection
- [ ] Implement application metrics (counters, gauges, histograms)
- [ ] Create custom metrics for video processing
- [ ] Set up Grafana dashboards
- [ ] Implement log aggregation and structured logging
- [ ] Add distributed tracing (optional: Jaeger/Tempo)
- [ ] Create alerting rules in Prometheus
- [ ] Implement alert notification channels (email, Slack)
- [ ] Add performance profiling endpoints
- [ ] Create system resource dashboards (CPU, RAM, disk, network)
- [ ] Implement job queue monitoring
- [ ] Add Celery worker monitoring
- [ ] Create business metrics dashboard
- [ ] Implement SLA tracking
- [ ] Add custom exporters for MinIO and Airflow

---

## Deliverables

- ✅ Prometheus collecting all metrics
- ✅ 4 Grafana dashboards operational
- ✅ Alerting rules configured
- ✅ Structured logging implemented
- ✅ Performance monitoring active

---

## Acceptance Criteria

- [ ] Prometheus scraping all targets
- [ ] Grafana dashboards showing live data
- [ ] Alerts trigger and send notifications
- [ ] Logs are structured (JSON format)
- [ ] All critical metrics tracked
- [ ] SLA metrics calculated correctly
- [ ] Performance bottlenecks identifiable

---

## Technical Details

### Prometheus Configuration

```yaml
# prometheus/prometheus.yml

global:
  scrape_interval: 15s
  evaluation_interval: 15s

# Alertmanager configuration
alerting:
  alertmanagers:
    - static_configs:
        - targets:
            - alertmanager:9093

# Load alerting rules
rule_files:
  - "alerts/*.yml"

scrape_configs:
  # FastAPI application
  - job_name: 'fastapi'
    static_configs:
      - targets: ['fastapi:8000']
    metrics_path: '/metrics'

  # PostgreSQL exporter
  - job_name: 'postgres'
    static_configs:
      - targets: ['postgres-exporter:9187']

  # Redis exporter
  - job_name: 'redis'
    static_configs:
      - targets: ['redis-exporter:9121']

  # MinIO exporter
  - job_name: 'minio'
    static_configs:
      - targets: ['minio:9000']
    metrics_path: '/minio/v2/metrics/cluster'

  # Node exporter (system metrics)
  - job_name: 'node'
    static_configs:
      - targets: ['node-exporter:9100']

  # Celery exporter
  - job_name: 'celery'
    static_configs:
      - targets: ['celery-exporter:9540']

  # Airflow exporter
  - job_name: 'airflow'
    static_configs:
      - targets: ['airflow-exporter:9112']
```

---

### Application Metrics (FastAPI)

```python
# metrics/prometheus.py

from prometheus_client import Counter, Gauge, Histogram, Summary
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from fastapi import Response

# ============================================
# API Metrics
# ============================================

# Request counters
api_requests_total = Counter(
    'api_requests_total',
    'Total API requests',
    ['method', 'endpoint', 'status']
)

# Request duration
api_request_duration_seconds = Histogram(
    'api_request_duration_seconds',
    'API request duration in seconds',
    ['method', 'endpoint'],
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0, 10.0]
)

# Active requests
api_requests_in_progress = Gauge(
    'api_requests_in_progress',
    'Number of API requests in progress',
    ['method', 'endpoint']
)

# ============================================
# Job Metrics
# ============================================

# Job counters
jobs_total = Counter(
    'jobs_total',
    'Total number of jobs',
    ['status']
)

jobs_created_total = Counter(
    'jobs_created_total',
    'Total number of jobs created'
)

jobs_completed_total = Counter(
    'jobs_completed_total',
    'Total number of completed jobs'
)

jobs_failed_total = Counter(
    'jobs_failed_total',
    'Total number of failed jobs',
    ['error_type']
)

# Job gauges
jobs_queued = Gauge(
    'jobs_queued',
    'Number of jobs in queue'
)

jobs_processing = Gauge(
    'jobs_processing',
    'Number of jobs currently processing'
)

# Job durations
job_processing_duration_seconds = Histogram(
    'job_processing_duration_seconds',
    'Job processing duration in seconds',
    buckets=[60, 300, 600, 1800, 3600, 7200, 14400]  # 1m to 4h
)

job_queue_time_seconds = Histogram(
    'job_queue_time_seconds',
    'Time job spent in queue before processing',
    buckets=[1, 5, 10, 30, 60, 300, 600]
)

# ============================================
# Video Processing Metrics
# ============================================

# Transcoding metrics
video_transcode_duration_seconds = Histogram(
    'video_transcode_duration_seconds',
    'Video transcoding duration',
    ['resolution'],
    buckets=[30, 60, 120, 300, 600, 1200, 1800, 3600]
)

video_transcoded_bytes = Counter(
    'video_transcoded_bytes_total',
    'Total bytes transcoded',
    ['resolution']
)

video_compression_ratio = Histogram(
    'video_compression_ratio',
    'Video compression ratio',
    ['resolution'],
    buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
)

# Transcription metrics
transcription_duration_seconds = Histogram(
    'transcription_duration_seconds',
    'Transcription duration',
    ['whisper_model'],
    buckets=[30, 60, 120, 300, 600, 1200, 1800]
)

transcription_word_count = Histogram(
    'transcription_word_count',
    'Number of words transcribed',
    buckets=[100, 500, 1000, 2000, 5000, 10000]
)

# ============================================
# Storage Metrics
# ============================================

storage_used_bytes = Gauge(
    'storage_used_bytes',
    'Storage used in bytes',
    ['api_key']
)

storage_quota_bytes = Gauge(
    'storage_quota_bytes',
    'Storage quota in bytes',
    ['api_key']
)

# ============================================
# Worker Metrics
# ============================================

celery_workers_active = Gauge(
    'celery_workers_active',
    'Number of active Celery workers'
)

celery_tasks_active = Gauge(
    'celery_tasks_active',
    'Number of active Celery tasks'
)

# ============================================
# Metrics Endpoint
# ============================================

@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint"""
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST
    )
```

---

### Metrics Middleware

```python
# middleware/metrics.py

import time
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        method = request.method
        endpoint = request.url.path

        # Track request
        api_requests_in_progress.labels(method=method, endpoint=endpoint).inc()

        start_time = time.time()

        try:
            response = await call_next(request)
            status = response.status_code

            # Record metrics
            api_requests_total.labels(
                method=method,
                endpoint=endpoint,
                status=status
            ).inc()

            duration = time.time() - start_time
            api_request_duration_seconds.labels(
                method=method,
                endpoint=endpoint
            ).observe(duration)

            return response

        except Exception as e:
            api_requests_total.labels(
                method=method,
                endpoint=endpoint,
                status=500
            ).inc()
            raise

        finally:
            api_requests_in_progress.labels(method=method, endpoint=endpoint).dec()

# Add to FastAPI app
app.add_middleware(MetricsMiddleware)
```

---

### Update Job Metrics

```python
# In DAG tasks - record metrics

def update_database_task(**context):
    job_id = context['dag_run'].conf['job_id']
    job = get_job(job_id)

    if job.status == 'completed':
        # Increment completed counter
        jobs_completed_total.inc()

        # Record processing duration
        processing_time = (job.completed_at - job.created_at).total_seconds()
        job_processing_duration_seconds.observe(processing_time)

        # Record queue time
        if job.started_at:
            queue_time = (job.started_at - job.created_at).total_seconds()
            job_queue_time_seconds.observe(queue_time)

        # Record transcoding metrics
        if job.transcode_360p_time_seconds:
            video_transcode_duration_seconds.labels(resolution='360p').observe(
                job.transcode_360p_time_seconds
            )
            video_transcoded_bytes.labels(resolution='360p').inc(
                job.output_360p_size_bytes or 0
            )
            if job.compression_ratio_360p:
                video_compression_ratio.labels(resolution='360p').observe(
                    job.compression_ratio_360p
                )

        if job.transcode_720p_time_seconds:
            video_transcode_duration_seconds.labels(resolution='720p').observe(
                job.transcode_720p_time_seconds
            )
            video_transcoded_bytes.labels(resolution='720p').inc(
                job.output_720p_size_bytes or 0
            )
            if job.compression_ratio_720p:
                video_compression_ratio.labels(resolution='720p').observe(
                    job.compression_ratio_720p
                )

        # Record transcription metrics
        if job.transcription_time_seconds:
            transcription_duration_seconds.labels(
                whisper_model=job.whisper_model
            ).observe(job.transcription_time_seconds)

            if job.transcription_word_count:
                transcription_word_count.observe(job.transcription_word_count)

    elif job.status == 'failed':
        jobs_failed_total.labels(error_type=job.failed_task or 'unknown').inc()

    # Update gauge metrics
    update_gauge_metrics()

def update_gauge_metrics():
    """Update gauge metrics from database"""

    # Jobs by status
    jobs_queued.set(db.query(Job).filter(Job.status == 'queued').count())
    jobs_processing.set(db.query(Job).filter(Job.status == 'processing').count())

    # Storage usage per API key
    for api_key in db.query(ApiKey).all():
        quota_manager = StorageQuotaManager(db)
        usage = quota_manager.get_usage(api_key.key_hash)

        storage_used_bytes.labels(api_key=api_key.name).set(usage['total_bytes'])

        if api_key.storage_quota_bytes:
            storage_quota_bytes.labels(api_key=api_key.name).set(
                api_key.storage_quota_bytes
            )
```

---

### Structured Logging

```python
# logging_config.py

import logging
import json
from datetime import datetime

class JSONFormatter(logging.Formatter):
    """Format logs as JSON"""

    def format(self, record):
        log_data = {
            'timestamp': datetime.utcnow().isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno
        }

        # Add exception info if present
        if record.exc_info:
            log_data['exception'] = self.formatException(record.exc_info)

        # Add extra fields
        if hasattr(record, 'job_id'):
            log_data['job_id'] = record.job_id

        if hasattr(record, 'api_key'):
            log_data['api_key'] = record.api_key

        if hasattr(record, 'duration_ms'):
            log_data['duration_ms'] = record.duration_ms

        return json.dumps(log_data)

# Configure logging
def setup_logging():
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    # Console handler with JSON format
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(JSONFormatter())
    logger.addHandler(console_handler)

    # File handler
    file_handler = logging.FileHandler('/data/logs/app.log')
    file_handler.setFormatter(JSONFormatter())
    logger.addHandler(file_handler)

# Usage in application
import logging

logger = logging.getLogger(__name__)

logger.info(
    "Job created",
    extra={
        'job_id': job.id,
        'api_key': job.api_key,
        'filename': job.original_filename
    }
)
```

---

### Alert Rules

```yaml
# prometheus/alerts/job_alerts.yml

groups:
  - name: job_alerts
    interval: 30s
    rules:
      # Too many failed jobs
      - alert: HighJobFailureRate
        expr: |
          rate(jobs_failed_total[5m]) > 0.1
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High job failure rate"
          description: "Job failure rate is {{ $value }} per second"

      # Jobs stuck in queue
      - alert: JobsStuckInQueue
        expr: |
          jobs_queued > 50
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "Too many jobs in queue"
          description: "{{ $value }} jobs stuck in queue for over 10 minutes"

      # Long processing times
      - alert: SlowJobProcessing
        expr: |
          job_processing_duration_seconds{quantile="0.95"} > 3600
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Jobs taking too long to process"
          description: "95th percentile processing time is {{ $value }} seconds"

      # No jobs completed recently
      - alert: NoJobsCompleted
        expr: |
          rate(jobs_completed_total[30m]) == 0
        for: 30m
        labels:
          severity: critical
        annotations:
          summary: "No jobs completed in 30 minutes"
          description: "Processing pipeline may be stuck"
```

```yaml
# prometheus/alerts/system_alerts.yml

groups:
  - name: system_alerts
    interval: 30s
    rules:
      # Low disk space
      - alert: LowDiskSpace
        expr: |
          (node_filesystem_avail_bytes{mountpoint="/data"} / node_filesystem_size_bytes{mountpoint="/data"}) * 100 < 10
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "Low disk space on /data"
          description: "Only {{ $value }}% disk space remaining"

      # High CPU usage
      - alert: HighCPUUsage
        expr: |
          100 - (avg by(instance) (irate(node_cpu_seconds_total{mode="idle"}[5m])) * 100) > 90
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "High CPU usage"
          description: "CPU usage is {{ $value }}%"

      # High memory usage
      - alert: HighMemoryUsage
        expr: |
          (1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)) * 100 > 90
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "High memory usage"
          description: "Memory usage is {{ $value }}%"

      # Service down
      - alert: ServiceDown
        expr: |
          up == 0
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "Service {{ $labels.job }} is down"
          description: "{{ $labels.job }} has been down for more than 2 minutes"

      # Database connection issues
      - alert: PostgreSQLDown
        expr: |
          pg_up == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "PostgreSQL is down"
          description: "Cannot connect to PostgreSQL database"

      # Redis down
      - alert: RedisDown
        expr: |
          redis_up == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "Redis is down"
          description: "Cannot connect to Redis"
```

---

### Alertmanager Configuration

```yaml
# alertmanager/alertmanager.yml

global:
  resolve_timeout: 5m
  smtp_smarthost: 'smtp.gmail.com:587'
  smtp_from: 'alerts@transcode-flow.com'
  smtp_auth_username: 'alerts@transcode-flow.com'
  smtp_auth_password: 'PASSWORD'

# Email notification template
templates:
  - '/etc/alertmanager/templates/*.tmpl'

# Routing tree
route:
  receiver: 'default'
  group_by: ['alertname', 'cluster']
  group_wait: 10s
  group_interval: 10s
  repeat_interval: 12h

  routes:
    # Critical alerts to email + Slack
    - match:
        severity: critical
      receiver: 'critical-alerts'
      continue: true

    # Warning alerts to Slack only
    - match:
        severity: warning
      receiver: 'slack-warnings'

# Receivers
receivers:
  - name: 'default'
    email_configs:
      - to: 'team@transcode-flow.com'

  - name: 'critical-alerts'
    email_configs:
      - to: 'oncall@transcode-flow.com'
        headers:
          Subject: '[CRITICAL] {{ .GroupLabels.alertname }}'
    slack_configs:
      - api_url: 'YOUR_SLACK_WEBHOOK_URL'
        channel: '#alerts-critical'
        title: '[CRITICAL] {{ .GroupLabels.alertname }}'
        text: '{{ range .Alerts }}{{ .Annotations.description }}{{ end }}'

  - name: 'slack-warnings'
    slack_configs:
      - api_url: 'YOUR_SLACK_WEBHOOK_URL'
        channel: '#alerts-warnings'
        title: '[WARNING] {{ .GroupLabels.alertname }}'
        text: '{{ range .Alerts }}{{ .Annotations.description }}{{ end }}'
```

---

### Grafana Dashboards

#### Dashboard 1: System Overview

```json
{
  "dashboard": {
    "title": "System Overview",
    "panels": [
      {
        "title": "CPU Usage",
        "targets": [{
          "expr": "100 - (avg(irate(node_cpu_seconds_total{mode=\"idle\"}[5m])) * 100)"
        }],
        "type": "graph"
      },
      {
        "title": "Memory Usage",
        "targets": [{
          "expr": "(1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)) * 100"
        }],
        "type": "graph"
      },
      {
        "title": "Disk Usage (/data)",
        "targets": [{
          "expr": "(node_filesystem_size_bytes{mountpoint=\"/data\"} - node_filesystem_avail_bytes{mountpoint=\"/data\"}) / node_filesystem_size_bytes{mountpoint=\"/data\"} * 100"
        }],
        "type": "gauge"
      },
      {
        "title": "Network Traffic",
        "targets": [
          {
            "expr": "rate(node_network_receive_bytes_total[5m])",
            "legendFormat": "Receive"
          },
          {
            "expr": "rate(node_network_transmit_bytes_total[5m])",
            "legendFormat": "Transmit"
          }
        ],
        "type": "graph"
      }
    ]
  }
}
```

#### Dashboard 2: Job Processing

```json
{
  "dashboard": {
    "title": "Job Processing",
    "panels": [
      {
        "title": "Jobs by Status",
        "targets": [
          {
            "expr": "jobs_queued",
            "legendFormat": "Queued"
          },
          {
            "expr": "jobs_processing",
            "legendFormat": "Processing"
          }
        ],
        "type": "graph"
      },
      {
        "title": "Job Completion Rate",
        "targets": [{
          "expr": "rate(jobs_completed_total[5m]) * 60"
        }],
        "type": "stat",
        "unit": "jobs/min"
      },
      {
        "title": "Job Success Rate",
        "targets": [{
          "expr": "rate(jobs_completed_total[5m]) / (rate(jobs_completed_total[5m]) + rate(jobs_failed_total[5m])) * 100"
        }],
        "type": "gauge",
        "unit": "percent"
      },
      {
        "title": "Processing Duration (p95)",
        "targets": [{
          "expr": "histogram_quantile(0.95, rate(job_processing_duration_seconds_bucket[5m]))"
        }],
        "type": "graph",
        "unit": "seconds"
      }
    ]
  }
}
```

#### Dashboard 3: Video Processing Metrics

```json
{
  "dashboard": {
    "title": "Video Processing",
    "panels": [
      {
        "title": "Transcoding Duration by Resolution",
        "targets": [
          {
            "expr": "histogram_quantile(0.50, rate(video_transcode_duration_seconds_bucket{resolution=\"360p\"}[5m]))",
            "legendFormat": "360p (median)"
          },
          {
            "expr": "histogram_quantile(0.50, rate(video_transcode_duration_seconds_bucket{resolution=\"720p\"}[5m]))",
            "legendFormat": "720p (median)"
          }
        ],
        "type": "graph"
      },
      {
        "title": "Compression Ratio",
        "targets": [
          {
            "expr": "histogram_quantile(0.50, rate(video_compression_ratio_bucket{resolution=\"360p\"}[5m]))",
            "legendFormat": "360p"
          },
          {
            "expr": "histogram_quantile(0.50, rate(video_compression_ratio_bucket{resolution=\"720p\"}[5m]))",
            "legendFormat": "720p"
          }
        ],
        "type": "graph"
      },
      {
        "title": "Bytes Transcoded",
        "targets": [
          {
            "expr": "rate(video_transcoded_bytes_total{resolution=\"360p\"}[5m])",
            "legendFormat": "360p"
          },
          {
            "expr": "rate(video_transcoded_bytes_total{resolution=\"720p\"}[5m])",
            "legendFormat": "720p"
          }
        ],
        "type": "graph",
        "unit": "bytes"
      }
    ]
  }
}
```

#### Dashboard 4: API Performance

```json
{
  "dashboard": {
    "title": "API Performance",
    "panels": [
      {
        "title": "Request Rate",
        "targets": [{
          "expr": "sum(rate(api_requests_total[5m])) by (endpoint)"
        }],
        "type": "graph"
      },
      {
        "title": "Request Duration (p95)",
        "targets": [{
          "expr": "histogram_quantile(0.95, rate(api_request_duration_seconds_bucket[5m]))"
        }],
        "type": "graph"
      },
      {
        "title": "Error Rate",
        "targets": [{
          "expr": "sum(rate(api_requests_total{status=~\"5..\"}[5m])) / sum(rate(api_requests_total[5m])) * 100"
        }],
        "type": "graph",
        "unit": "percent"
      },
      {
        "title": "Requests in Progress",
        "targets": [{
          "expr": "sum(api_requests_in_progress)"
        }],
        "type": "stat"
      }
    ]
  }
}
```

---

## Docker Compose Updates

```yaml
# docker compose.yml additions

  prometheus:
    image: prom/prometheus:latest
    container_name: prometheus
    volumes:
      - ./prometheus/prometheus.yml:/etc/prometheus/prometheus.yml
      - ./prometheus/alerts:/etc/prometheus/alerts
      - /data/prometheus:/prometheus
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'
      - '--web.console.libraries=/usr/share/prometheus/console_libraries'
      - '--web.console.templates=/usr/share/prometheus/consoles'
    ports:
      - "9090:9090"
    restart: unless-stopped

  alertmanager:
    image: prom/alertmanager:latest
    container_name: alertmanager
    volumes:
      - ./alertmanager/alertmanager.yml:/etc/alertmanager/alertmanager.yml
      - /data/alertmanager:/alertmanager
    command:
      - '--config.file=/etc/alertmanager/alertmanager.yml'
      - '--storage.path=/alertmanager'
    ports:
      - "9093:9093"
    restart: unless-stopped

  node-exporter:
    image: prom/node-exporter:latest
    container_name: node-exporter
    command:
      - '--path.rootfs=/host'
    volumes:
      - '/:/host:ro,rslave'
    ports:
      - "9100:9100"
    restart: unless-stopped

  postgres-exporter:
    image: prometheuscommunity/postgres-exporter:latest
    container_name: postgres-exporter
    environment:
      DATA_SOURCE_NAME: "postgresql://transcode_user:password@postgres:5432/transcode_db?sslmode=disable"
    ports:
      - "9187:9187"
    restart: unless-stopped

  redis-exporter:
    image: oliver006/redis_exporter:latest
    container_name: redis-exporter
    environment:
      REDIS_ADDR: "redis:6379"
    ports:
      - "9121:9121"
    restart: unless-stopped
```

---

## Testing

```python
# tests/test_metrics.py

def test_metrics_endpoint():
    """Test metrics endpoint returns Prometheus format"""
    response = client.get("/metrics")

    assert response.status_code == 200
    assert "api_requests_total" in response.text
    assert "jobs_total" in response.text

def test_job_metrics_incremented():
    """Test job metrics are incremented"""
    # Get initial metric value
    response = client.get("/metrics")
    initial_count = parse_metric(response.text, "jobs_created_total")

    # Create job
    create_job(api_key)

    # Check metric incremented
    response = client.get("/metrics")
    new_count = parse_metric(response.text, "jobs_created_total")

    assert new_count == initial_count + 1

def test_structured_logging():
    """Test logs are in JSON format"""
    logger.info("Test message", extra={'job_id': '12345'})

    # Read log file
    with open('/data/logs/app.log', 'r') as f:
        last_line = f.readlines()[-1]

    log_data = json.loads(last_line)

    assert log_data['message'] == "Test message"
    assert log_data['job_id'] == '12345'
    assert 'timestamp' in log_data
```

---

## Performance Targets

| Metric | Target | Notes |
|--------|--------|-------|
| Metrics collection interval | 15s | Prometheus scrape |
| Alert evaluation interval | 30s | Responsive alerting |
| Dashboard refresh rate | 5s | Real-time visibility |
| Log ingestion latency | < 100ms | Structured logs |
| Metrics endpoint response | < 50ms | /metrics endpoint |

---

## Next Sprint

Sprint 7: NGINX Streaming & API Key Management
