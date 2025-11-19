# Sprint 7: NGINX Streaming & API Key Management (Week 8)

**Goal:** Implement HLS streaming with NGINX and comprehensive API key management

**Duration:** 1 week
**Team Size:** 2 developers

---

## Tasks

- [ ] Configure NGINX for HLS streaming
- [ ] Implement secure streaming with token authentication
- [ ] Add CORS configuration for video players
- [ ] Implement bandwidth throttling
- [ ] Add CDN integration (optional: CloudFlare)
- [ ] Create API key generation endpoint
- [ ] Implement API key rotation
- [ ] Add API key permissions/scopes
- [ ] Implement rate limiting per API key
- [ ] Add API key usage analytics
- [ ] Create API key revocation endpoint
- [ ] Implement API key expiration dates
- [ ] Add IP whitelist/blacklist per API key
- [ ] Create API key management dashboard data
- [ ] Implement master API keys with sub-keys

---

## Deliverables

- ✅ NGINX serving HLS streams
- ✅ Secure token-based streaming
- ✅ API key management system complete
- ✅ Rate limiting enforced
- ✅ API key analytics available

---

## Acceptance Criteria

- [ ] HLS streams playable in video.js, hls.js
- [ ] Streaming requires valid authentication token
- [ ] CORS configured correctly for web players
- [ ] Rate limiting prevents abuse
- [ ] API keys can be created, rotated, revoked
- [ ] API key usage tracked and reported
- [ ] Bandwidth throttling works correctly

---

## Technical Details

### NGINX Configuration for HLS Streaming

```nginx
# nginx/nginx.conf

user nginx;
worker_processes auto;
error_log /var/log/nginx/error.log warn;
pid /var/run/nginx.pid;

events {
    worker_connections 4096;
    use epoll;
}

http {
    include /etc/nginx/mime.types;
    default_type application/octet-stream;

    # Logging
    log_format main '$remote_addr - $remote_user [$time_local] "$request" '
                    '$status $body_bytes_sent "$http_referer" '
                    '"$http_user_agent" "$http_x_forwarded_for"';

    access_log /var/log/nginx/access.log main;

    # Performance
    sendfile on;
    tcp_nopush on;
    tcp_nodelay on;
    keepalive_timeout 65;
    types_hash_max_size 2048;

    # Gzip compression
    gzip on;
    gzip_vary on;
    gzip_proxied any;
    gzip_comp_level 6;
    gzip_types text/plain text/css text/xml text/javascript
               application/json application/javascript application/xml+rss
               application/vnd.apple.mpegurl;

    # Rate limiting zones
    limit_req_zone $binary_remote_addr zone=api_limit:10m rate=10r/s;
    limit_req_zone $binary_remote_addr zone=stream_limit:10m rate=100r/s;

    # Upstream FastAPI
    upstream fastapi_backend {
        server fastapi:8000;
        keepalive 32;
    }

    # ========================================
    # Main Server Block
    # ========================================

    server {
        listen 80;
        server_name _;

        client_max_body_size 10G;
        client_body_timeout 600s;
        client_header_timeout 600s;

        # ========================================
        # API Endpoints (Proxy to FastAPI)
        # ========================================

        location /api/ {
            limit_req zone=api_limit burst=20 nodelay;

            proxy_pass http://fastapi_backend;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;

            # Timeouts
            proxy_connect_timeout 600s;
            proxy_send_timeout 600s;
            proxy_read_timeout 600s;

            # WebSocket support (for SSE)
            proxy_http_version 1.1;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection "upgrade";
        }

        # ========================================
        # HLS Streaming
        # ========================================

        location /stream/ {
            limit_req zone=stream_limit burst=50 nodelay;

            # Secure link validation
            secure_link $arg_token;
            secure_link_md5 "$secure_link_expires$uri$remote_addr SECRET_KEY";

            if ($secure_link = "") {
                return 403;
            }

            if ($secure_link = "0") {
                return 410;  # Link expired
            }

            # CORS headers
            add_header 'Access-Control-Allow-Origin' '*' always;
            add_header 'Access-Control-Allow-Methods' 'GET, OPTIONS' always;
            add_header 'Access-Control-Allow-Headers' 'Range' always;
            add_header 'Access-Control-Expose-Headers' 'Content-Length,Content-Range' always;

            # HLS-specific headers
            add_header Cache-Control "public, max-age=3600";

            # Handle OPTIONS for CORS preflight
            if ($request_method = 'OPTIONS') {
                add_header 'Access-Control-Allow-Origin' '*';
                add_header 'Access-Control-Allow-Methods' 'GET, OPTIONS';
                add_header 'Access-Control-Max-Age' 1728000;
                add_header 'Content-Type' 'text/plain; charset=utf-8';
                add_header 'Content-Length' 0;
                return 204;
            }

            # Serve from MinIO
            # Pattern: /stream/{job_id}/{resolution}/playlist.m3u8
            # Pattern: /stream/{job_id}/{resolution}/segment_000.ts

            proxy_pass http://minio:9000/videos/processed/$1/$2/$3;
            proxy_buffering off;
            proxy_set_header Host $host;

            # Bandwidth throttling (optional)
            # limit_rate 2m;  # 2MB/s per connection
        }

        # ========================================
        # Health Check
        # ========================================

        location /health {
            access_log off;
            return 200 "healthy\n";
            add_header Content-Type text/plain;
        }

        # ========================================
        # Metrics (Prometheus)
        # ========================================

        location /metrics {
            proxy_pass http://fastapi_backend/metrics;
            allow 10.0.0.0/8;  # Internal network only
            deny all;
        }
    }

    # ========================================
    # SSL/TLS Configuration (Production)
    # ========================================

    # Uncomment for production with SSL certificates

    # server {
    #     listen 443 ssl http2;
    #     server_name transcode-flow.example.com;
    #
    #     ssl_certificate /etc/nginx/ssl/cert.pem;
    #     ssl_certificate_key /etc/nginx/ssl/key.pem;
    #     ssl_protocols TLSv1.2 TLSv1.3;
    #     ssl_ciphers HIGH:!aNULL:!MD5;
    #     ssl_prefer_server_ciphers on;
    #
    #     # ... (rest of configuration same as above)
    # }
    #
    # # Redirect HTTP to HTTPS
    # server {
    #     listen 80;
    #     server_name transcode-flow.example.com;
    #     return 301 https://$server_name$request_uri;
    # }
}
```

---

### Secure Streaming Token Generation

```python
# streaming/tokens.py

import hashlib
import base64
from datetime import datetime, timedelta
from urllib.parse import quote

class StreamingTokenGenerator:
    def __init__(self, secret_key: str):
        self.secret_key = secret_key

    def generate_token(
        self,
        job_id: str,
        resolution: str,
        filename: str,
        expires_in: timedelta = timedelta(hours=1)
    ) -> dict:
        """
        Generate secure token for HLS streaming

        Returns dict with:
        - url: Full streaming URL with token
        - token: Token string
        - expires_at: Expiration timestamp
        """

        # Calculate expiration
        expires_at = datetime.now() + expires_in
        expires_timestamp = int(expires_at.timestamp())

        # Build URI path
        uri = f"/stream/{job_id}/{resolution}/{filename}"

        # Create secure link hash
        # Format: md5(expires + uri + remote_addr + secret_key)
        # Note: For simplicity, we exclude remote_addr (can be added for stricter security)
        hash_input = f"{expires_timestamp}{uri}{self.secret_key}"
        token = hashlib.md5(hash_input.encode()).hexdigest()

        # Encode token for URL
        token_encoded = base64.urlsafe_b64encode(token.encode()).decode().rstrip('=')

        # Build full URL
        url = f"{uri}?token={token_encoded}&expires={expires_timestamp}"

        return {
            'url': url,
            'token': token_encoded,
            'expires_at': expires_at.isoformat(),
            'expires_in_seconds': expires_in.total_seconds()
        }

    def verify_token(self, uri: str, token: str, expires: int, remote_addr: str = None) -> bool:
        """Verify streaming token (used by NGINX or reverse proxy)"""

        # Check expiration
        if int(datetime.now().timestamp()) > expires:
            return False

        # Rebuild hash
        hash_input = f"{expires}{uri}{self.secret_key}"
        expected_token = hashlib.md5(hash_input.encode()).hexdigest()
        expected_token_encoded = base64.urlsafe_b64encode(expected_token.encode()).decode().rstrip('=')

        return token == expected_token_encoded
```

**API Endpoint:**

```python
# api/routes/streaming.py

from fastapi import APIRouter, Depends, HTTPException
from streaming.tokens import StreamingTokenGenerator

router = APIRouter(prefix="/streaming", tags=["streaming"])

@router.get("/token/{job_id}/{resolution}")
async def get_streaming_token(
    job_id: str,
    resolution: str,  # 360p or 720p
    api_key: str = Depends(verify_api_key)
):
    """Generate streaming token for HLS playlist"""

    # Verify job ownership
    job = db.query(Job).filter(Job.id == job_id).first()

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.api_key != api_key:
        raise HTTPException(status_code=403, detail="Access denied")

    if job.status != 'completed':
        raise HTTPException(status_code=400, detail="Job not completed")

    # Verify resolution available
    if resolution == '360p' and not job.output_hls_360p_path:
        raise HTTPException(status_code=404, detail="360p not available")

    if resolution == '720p' and not job.output_hls_720p_path:
        raise HTTPException(status_code=404, detail="720p not available")

    # Generate token
    generator = StreamingTokenGenerator(secret_key=os.getenv("STREAMING_SECRET_KEY"))

    token_data = generator.generate_token(
        job_id=job_id,
        resolution=resolution,
        filename='playlist.m3u8',
        expires_in=timedelta(hours=2)
    )

    return {
        "job_id": job_id,
        "resolution": resolution,
        "playlist_url": f"http://your-domain.com{token_data['url']}",
        "token": token_data['token'],
        "expires_at": token_data['expires_at'],
        "expires_in_seconds": token_data['expires_in_seconds']
    }
```

---

### API Key Management

#### Enhanced API Key Model

```python
# models/api_key.py

from sqlalchemy import Column, String, Integer, Boolean, DateTime, JSON, ARRAY
from datetime import datetime, timedelta
import secrets

class ApiKey(Base):
    __tablename__ = 'api_keys'

    id = Column(Integer, primary_key=True)
    key_hash = Column(String(64), unique=True, nullable=False, index=True)
    key_prefix = Column(String(8), nullable=False)  # First 8 chars for identification
    name = Column(String(100), nullable=False)
    description = Column(String(500))

    # Ownership
    user_id = Column(String(100))  # Optional: link to user system
    master_key_id = Column(Integer, ForeignKey('api_keys.id'), nullable=True)

    # Permissions
    scopes = Column(ARRAY(String), default=['read', 'write'])  # read, write, delete, admin
    rate_limit_per_minute = Column(Integer, default=100)
    rate_limit_per_hour = Column(Integer, default=1000)
    rate_limit_per_day = Column(Integer, default=10000)

    # Quotas
    storage_quota_bytes = Column(BigInteger, nullable=True)  # NULL = unlimited
    max_concurrent_jobs = Column(Integer, default=8)
    max_video_size_bytes = Column(BigInteger, default=10737418240)  # 10GB

    # Security
    ip_whitelist = Column(ARRAY(String), default=[])  # Empty = all IPs allowed
    ip_blacklist = Column(ARRAY(String), default=[])
    webhook_url = Column(String(500), nullable=True)
    webhook_secret = Column(String(64), nullable=True)

    # Status
    is_active = Column(Boolean, default=True)
    is_revoked = Column(Boolean, default=False)
    expires_at = Column(DateTime, nullable=True)  # NULL = never expires

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    last_used_at = Column(DateTime, nullable=True)
    revoked_at = Column(DateTime, nullable=True)

    # Usage tracking
    total_requests = Column(BigInteger, default=0)
    total_jobs_created = Column(Integer, default=0)

    # Indexes
    __table_args__ = (
        Index('idx_api_keys_active', 'is_active', 'is_revoked'),
        Index('idx_api_keys_expires', 'expires_at'),
    )

    @staticmethod
    def generate_key() -> tuple[str, str]:
        """
        Generate new API key

        Returns: (raw_key, key_hash)
        """
        # Generate random key (32 bytes = 64 hex chars)
        raw_key = secrets.token_hex(32)

        # Hash for storage
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

        return raw_key, key_hash

    def check_expired(self) -> bool:
        """Check if API key is expired"""
        if not self.expires_at:
            return False

        return datetime.utcnow() > self.expires_at

    def check_ip_allowed(self, ip_address: str) -> bool:
        """Check if IP address is allowed"""

        # Check blacklist first
        if ip_address in self.ip_blacklist:
            return False

        # If whitelist empty, allow all
        if not self.ip_whitelist:
            return True

        # Check whitelist
        return ip_address in self.ip_whitelist
```

---

### API Key Management Endpoints

```python
# api/routes/api_keys.py

from fastapi import APIRouter, Depends, HTTPException
from schemas import ApiKeyCreate, ApiKeyResponse, ApiKeyUpdate

router = APIRouter(prefix="/api-keys", tags=["api-keys"])

@router.post("/", response_model=ApiKeyResponse)
async def create_api_key(
    data: ApiKeyCreate,
    master_api_key: str = Depends(verify_admin_api_key)  # Requires admin scope
):
    """Create new API key"""

    # Generate key
    raw_key, key_hash = ApiKey.generate_key()
    key_prefix = raw_key[:8]

    # Create API key
    api_key = ApiKey(
        key_hash=key_hash,
        key_prefix=key_prefix,
        name=data.name,
        description=data.description,
        scopes=data.scopes or ['read', 'write'],
        rate_limit_per_minute=data.rate_limit_per_minute or 100,
        storage_quota_bytes=data.storage_quota_bytes,
        expires_at=data.expires_at,
        ip_whitelist=data.ip_whitelist or [],
        webhook_url=data.webhook_url
    )

    db.add(api_key)
    db.commit()

    # Log creation
    logger.info(f"API key created: {api_key.name}", extra={'key_id': api_key.id})

    return {
        "id": api_key.id,
        "key": raw_key,  # Only returned once!
        "key_prefix": key_prefix,
        "name": api_key.name,
        "scopes": api_key.scopes,
        "created_at": api_key.created_at,
        "expires_at": api_key.expires_at,
        "warning": "Save this key securely. It will not be shown again."
    }

@router.get("/", response_model=List[ApiKeyResponse])
async def list_api_keys(
    master_api_key: str = Depends(verify_admin_api_key)
):
    """List all API keys (admin only)"""

    keys = db.query(ApiKey).all()

    return [
        {
            "id": key.id,
            "key_prefix": key.key_prefix,
            "name": key.name,
            "description": key.description,
            "scopes": key.scopes,
            "is_active": key.is_active,
            "is_revoked": key.is_revoked,
            "created_at": key.created_at,
            "last_used_at": key.last_used_at,
            "expires_at": key.expires_at,
            "total_requests": key.total_requests,
            "total_jobs_created": key.total_jobs_created
        }
        for key in keys
    ]

@router.put("/{key_id}", response_model=ApiKeyResponse)
async def update_api_key(
    key_id: int,
    data: ApiKeyUpdate,
    master_api_key: str = Depends(verify_admin_api_key)
):
    """Update API key settings"""

    key = db.query(ApiKey).filter(ApiKey.id == key_id).first()

    if not key:
        raise HTTPException(status_code=404, detail="API key not found")

    # Update fields
    if data.name:
        key.name = data.name

    if data.description is not None:
        key.description = data.description

    if data.scopes:
        key.scopes = data.scopes

    if data.rate_limit_per_minute:
        key.rate_limit_per_minute = data.rate_limit_per_minute

    if data.storage_quota_bytes is not None:
        key.storage_quota_bytes = data.storage_quota_bytes

    if data.is_active is not None:
        key.is_active = data.is_active

    if data.expires_at is not None:
        key.expires_at = data.expires_at

    if data.ip_whitelist is not None:
        key.ip_whitelist = data.ip_whitelist

    db.commit()

    return {"message": "API key updated", "key_id": key_id}

@router.post("/{key_id}/rotate")
async def rotate_api_key(
    key_id: int,
    master_api_key: str = Depends(verify_admin_api_key)
):
    """Rotate API key (generate new key, invalidate old)"""

    old_key = db.query(ApiKey).filter(ApiKey.id == key_id).first()

    if not old_key:
        raise HTTPException(status_code=404, detail="API key not found")

    # Generate new key
    raw_key, key_hash = ApiKey.generate_key()
    key_prefix = raw_key[:8]

    # Update existing record
    old_key.key_hash = key_hash
    old_key.key_prefix = key_prefix

    db.commit()

    return {
        "message": "API key rotated successfully",
        "new_key": raw_key,
        "warning": "Update your applications with the new key immediately."
    }

@router.post("/{key_id}/revoke")
async def revoke_api_key(
    key_id: int,
    master_api_key: str = Depends(verify_admin_api_key)
):
    """Revoke API key (cannot be undone)"""

    key = db.query(ApiKey).filter(ApiKey.id == key_id).first()

    if not key:
        raise HTTPException(status_code=404, detail="API key not found")

    key.is_revoked = True
    key.is_active = False
    key.revoked_at = datetime.utcnow()

    db.commit()

    return {
        "message": "API key revoked successfully",
        "key_id": key_id,
        "revoked_at": key.revoked_at
    }

@router.get("/{key_id}/usage")
async def get_api_key_usage(
    key_id: int,
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
    master_api_key: str = Depends(verify_admin_api_key)
):
    """Get usage statistics for API key"""

    key = db.query(ApiKey).filter(ApiKey.id == key_id).first()

    if not key:
        raise HTTPException(status_code=404, detail="API key not found")

    # Query jobs for this API key
    query = db.query(Job).filter(Job.api_key == key.key_hash)

    if from_date:
        query = query.filter(Job.created_at >= from_date)

    if to_date:
        query = query.filter(Job.created_at <= to_date)

    jobs = query.all()

    # Calculate statistics
    total_jobs = len(jobs)
    completed_jobs = sum(1 for j in jobs if j.status == 'completed')
    failed_jobs = sum(1 for j in jobs if j.status == 'failed')

    total_processing_time = sum(
        j.total_processing_time_seconds or 0
        for j in jobs if j.status == 'completed'
    )

    # Storage usage
    quota_manager = StorageQuotaManager(db)
    storage_usage = quota_manager.get_usage(key.key_hash)

    return {
        "key_id": key_id,
        "key_name": key.name,
        "date_range": {
            "from": from_date.isoformat() if from_date else None,
            "to": to_date.isoformat() if to_date else None
        },
        "usage": {
            "total_requests": key.total_requests,
            "total_jobs": total_jobs,
            "completed_jobs": completed_jobs,
            "failed_jobs": failed_jobs,
            "success_rate": (completed_jobs / total_jobs * 100) if total_jobs > 0 else 0,
            "total_processing_hours": round(total_processing_time / 3600, 2)
        },
        "storage": storage_usage,
        "rate_limits": {
            "per_minute": key.rate_limit_per_minute,
            "per_hour": key.rate_limit_per_hour,
            "per_day": key.rate_limit_per_day
        }
    }
```

---

### Enhanced Rate Limiting

```python
# middleware/rate_limit.py

import redis
from datetime import datetime
from fastapi import Request, HTTPException

class RateLimiter:
    def __init__(self):
        self.redis_client = redis.Redis(host='redis', port=6379, db=1)

    def check_rate_limit(self, api_key_obj: ApiKey, ip_address: str) -> bool:
        """Check rate limits for API key"""

        key_hash = api_key_obj.key_hash
        now = datetime.utcnow()

        # Check per-minute limit
        minute_key = f"ratelimit:minute:{key_hash}:{now.strftime('%Y%m%d%H%M')}"
        minute_count = self.redis_client.incr(minute_key)
        self.redis_client.expire(minute_key, 60)

        if minute_count > api_key_obj.rate_limit_per_minute:
            return False

        # Check per-hour limit
        hour_key = f"ratelimit:hour:{key_hash}:{now.strftime('%Y%m%d%H')}"
        hour_count = self.redis_client.incr(hour_key)
        self.redis_client.expire(hour_key, 3600)

        if hour_count > api_key_obj.rate_limit_per_hour:
            return False

        # Check per-day limit
        day_key = f"ratelimit:day:{key_hash}:{now.strftime('%Y%m%d')}"
        day_count = self.redis_client.incr(day_key)
        self.redis_client.expire(day_key, 86400)

        if day_count > api_key_obj.rate_limit_per_day:
            return False

        return True

    def get_rate_limit_status(self, api_key_obj: ApiKey) -> dict:
        """Get current rate limit usage"""

        key_hash = api_key_obj.key_hash
        now = datetime.utcnow()

        minute_key = f"ratelimit:minute:{key_hash}:{now.strftime('%Y%m%d%H%M')}"
        hour_key = f"ratelimit:hour:{key_hash}:{now.strftime('%Y%m%d%H')}"
        day_key = f"ratelimit:day:{key_hash}:{now.strftime('%Y%m%d')}"

        minute_count = int(self.redis_client.get(minute_key) or 0)
        hour_count = int(self.redis_client.get(hour_key) or 0)
        day_count = int(self.redis_client.get(day_key) or 0)

        return {
            "per_minute": {
                "limit": api_key_obj.rate_limit_per_minute,
                "used": minute_count,
                "remaining": max(0, api_key_obj.rate_limit_per_minute - minute_count)
            },
            "per_hour": {
                "limit": api_key_obj.rate_limit_per_hour,
                "used": hour_count,
                "remaining": max(0, api_key_obj.rate_limit_per_hour - hour_count)
            },
            "per_day": {
                "limit": api_key_obj.rate_limit_per_day,
                "used": day_count,
                "remaining": max(0, api_key_obj.rate_limit_per_day - day_count)
            }
        }

# Add to API key verification
def verify_api_key(request: Request, x_api_key: str = Header(...)):
    # ... (existing verification)

    rate_limiter = RateLimiter()

    if not rate_limiter.check_rate_limit(api_key_obj, request.client.host):
        status = rate_limiter.get_rate_limit_status(api_key_obj)

        raise HTTPException(
            status_code=429,
            detail={
                "error": "Rate limit exceeded",
                "rate_limits": status
            }
        )

    # Update usage tracking
    api_key_obj.total_requests += 1
    api_key_obj.last_used_at = datetime.utcnow()
    db.commit()

    return api_key_obj.key_hash
```

---

## Testing

```python
# tests/test_streaming.py

def test_hls_streaming_with_token():
    """Test HLS streaming requires valid token"""

    # Get streaming token
    response = client.get(
        f"/streaming/token/{job_id}/360p",
        headers={"X-API-Key": api_key}
    )

    assert response.status_code == 200
    data = response.json()

    assert "playlist_url" in data
    assert "token" in data

    # Try to access playlist with token
    playlist_response = requests.get(data["playlist_url"])
    assert playlist_response.status_code == 200
    assert "#EXTM3U" in playlist_response.text

def test_api_key_creation():
    """Test API key creation"""

    response = client.post(
        "/api-keys/",
        json={
            "name": "Test Key",
            "scopes": ["read", "write"],
            "rate_limit_per_minute": 50
        },
        headers={"X-API-Key": admin_api_key}
    )

    assert response.status_code == 200
    data = response.json()

    assert "key" in data
    assert len(data["key"]) == 64
    assert data["name"] == "Test Key"

def test_api_key_rotation():
    """Test API key rotation"""

    # Rotate key
    response = client.post(
        f"/api-keys/{key_id}/rotate",
        headers={"X-API-Key": admin_api_key}
    )

    assert response.status_code == 200
    new_key = response.json()["new_key"]

    # Old key should not work
    response = client.get("/jobs", headers={"X-API-Key": old_key})
    assert response.status_code == 401

    # New key should work
    response = client.get("/jobs", headers={"X-API-Key": new_key})
    assert response.status_code == 200

def test_rate_limiting():
    """Test rate limiting enforcement"""

    # Make requests up to limit
    for i in range(100):
        response = client.get("/jobs", headers={"X-API-Key": api_key})
        assert response.status_code == 200

    # Next request should be rate limited
    response = client.get("/jobs", headers={"X-API-Key": api_key})
    assert response.status_code == 429
```

---

## Performance Targets

| Feature | Target | Notes |
|---------|--------|-------|
| HLS segment delivery | < 100ms | NGINX caching |
| Token generation | < 50ms | Simple hash |
| Rate limit check | < 10ms | Redis lookup |
| CORS preflight | < 20ms | Cached headers |
| Bandwidth per stream | 2-5 Mbps | Quality dependent |

---

## Next Sprint

Sprint 8: Testing & Performance Optimization
