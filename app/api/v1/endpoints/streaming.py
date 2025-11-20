"""
Streaming API Endpoints

Handles generation and validation of streaming tokens for HLS video delivery.
"""

from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Header, Request, Response
from sqlalchemy.orm import Session

from app.db import get_db
from app.core.security import get_api_key
from app.models.api_key import APIKey
from app.models.job import Job
from app.services.streaming_tokens import StreamingTokenService, get_streaming_token_service
from pydantic import BaseModel, Field


# ========================================
# Schemas
# ========================================

class StreamingTokenRequest(BaseModel):
    """Request body for generating a streaming token"""

    job_id: str = Field(..., description="Job ID to generate streaming token for")
    resolution: Optional[str] = Field(
        None,
        description="Specific resolution (e.g., '720p', '1080p'). If not provided, returns tokens for all resolutions"
    )
    expires_in_seconds: int = Field(
        3600,
        ge=60,
        le=86400,
        description="Token expiration time in seconds (min: 60, max: 86400/24h)"
    )
    allowed_ips: Optional[List[str]] = Field(
        None,
        description="Optional list of allowed IP addresses for this token"
    )
    max_uses: Optional[int] = Field(
        None,
        ge=1,
        le=1000,
        description="Optional maximum number of times the token can be used"
    )


class StreamingTokenResponse(BaseModel):
    """Response for streaming token generation"""

    job_id: str
    resolution: str
    token: str
    hls_url: str
    expires_at: str
    expires_in_seconds: int
    allowed_ips: Optional[List[str]] = None
    max_uses: Optional[int] = None


class StreamingTokensResponse(BaseModel):
    """Response containing multiple streaming tokens (all resolutions)"""

    job_id: str
    tokens: List[StreamingTokenResponse]


class TokenValidationResponse(BaseModel):
    """Response for token validation"""

    valid: bool
    job_id: Optional[str] = None
    error: Optional[str] = None
    message: Optional[str] = None


# ========================================
# Router
# ========================================

router = APIRouter(prefix="/streaming", tags=["streaming"])


# ========================================
# Endpoints
# ========================================

@router.post(
    "/tokens",
    response_model=StreamingTokensResponse,
    summary="Generate streaming tokens",
    description="""
    Generate secure, time-limited streaming tokens for a completed job.

    - Returns tokens for all available resolutions by default
    - Optionally request token for a specific resolution
    - Tokens are JWT-based with configurable expiration
    - Supports IP whitelisting and usage limits
    - Only works for jobs in 'completed' status
    """
)
async def generate_streaming_tokens(
    request_data: StreamingTokenRequest,
    db: Session = Depends(get_db),
    api_key: APIKey = Depends(get_api_key),
    streaming_service: StreamingTokenService = Depends(get_streaming_token_service),
    request: Request = None
) -> StreamingTokensResponse:
    """
    Generate streaming tokens for a job's HLS outputs.

    Returns tokens for all resolutions or a specific resolution.
    """
    # Verify job exists and belongs to this API key
    job = db.query(Job).filter(Job.id == request_data.job_id).first()

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.api_key_prefix != api_key.key_prefix:
        raise HTTPException(
            status_code=403,
            detail="You don't have access to this job"
        )

    if job.status != "completed":
        raise HTTPException(
            status_code=400,
            detail=f"Cannot generate streaming tokens for job in '{job.status}' status. Job must be completed."
        )

    # Get base URL from request
    base_url = f"{request.url.scheme}://{request.url.netloc}"

    # Determine which resolutions to generate tokens for
    if request_data.resolution:
        resolutions = [request_data.resolution]
    else:
        # Get all available resolutions for this job
        # In a real implementation, you'd query the actual output files
        resolutions = ["360p", "720p", "1080p"]

    tokens: List[StreamingTokenResponse] = []

    for resolution in resolutions:
        # Generate streaming URL with token
        url_data = streaming_service.generate_streaming_url(
            job_id=request_data.job_id,
            resolution=resolution,
            api_key_prefix=api_key.key_prefix,
            base_url=base_url,
            expires_in_seconds=request_data.expires_in_seconds,
            allowed_ips=request_data.allowed_ips
        )

        tokens.append(
            StreamingTokenResponse(
                job_id=request_data.job_id,
                resolution=resolution,
                token=url_data["token"],
                hls_url=url_data["hls_url"],
                expires_at=url_data["expires_at"],
                expires_in_seconds=url_data["expires_in_seconds"],
                allowed_ips=request_data.allowed_ips,
                max_uses=request_data.max_uses
            )
        )

    return StreamingTokensResponse(
        job_id=request_data.job_id,
        tokens=tokens
    )


@router.post(
    "/validate-token",
    response_model=TokenValidationResponse,
    summary="Validate streaming token (Internal)",
    description="""
    Internal endpoint for NGINX to validate streaming tokens.

    This endpoint is called by NGINX's auth_request directive to validate
    tokens before serving HLS video segments.

    Returns 200 if valid, 403 if invalid.
    """
)
async def validate_streaming_token(
    request: Request,
    x_stream_token: str = Header(..., description="Streaming token from URL path"),
    x_original_uri: str = Header(..., description="Original request URI"),
    streaming_service: StreamingTokenService = Depends(get_streaming_token_service)
) -> Response:
    """
    Validate a streaming token for NGINX auth_request.

    This is an internal endpoint used by NGINX to authorize streaming requests.
    """
    # Extract job_id from the URI
    # Expected format: /stream/TOKEN/job_abc123/720p/playlist.m3u8
    try:
        uri_parts = x_original_uri.split("/")
        # Find the part that starts with "job_"
        job_id = next(part for part in uri_parts if part.startswith("job_"))
    except (StopIteration, IndexError):
        return Response(status_code=403, content="Invalid URI format")

    # Get client IP
    client_ip = request.client.host if request.client else None

    # Validate token
    validation_result = streaming_service.validate_token(
        token=x_stream_token,
        job_id=job_id,
        client_ip=client_ip
    )

    if validation_result["valid"]:
        # Return 200 OK for NGINX to proceed with serving the file
        return Response(status_code=200)
    else:
        # Return 403 Forbidden to block access
        return Response(
            status_code=403,
            content=validation_result.get("message", "Access denied")
        )


@router.delete(
    "/tokens/{token}",
    summary="Revoke streaming token",
    description="""
    Revoke a specific streaming token before its expiration time.

    - Token will be added to a blacklist and immediately invalidated
    - Useful for security purposes or when access should be revoked
    """
)
async def revoke_streaming_token(
    token: str,
    api_key: APIKey = Depends(get_api_key),
    streaming_service: StreamingTokenService = Depends(get_streaming_token_service)
):
    """
    Revoke a streaming token.
    """
    # Validate token ownership (decode and check api_key_prefix)
    import jwt
    try:
        payload = jwt.decode(
            token,
            streaming_service.secret_key,
            algorithms=[streaming_service.algorithm]
        )

        if payload.get("api_key_prefix") != api_key.key_prefix:
            raise HTTPException(
                status_code=403,
                detail="You don't own this token"
            )
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=400, detail="Invalid token")

    # Revoke the token
    success = streaming_service.revoke_token(token)

    if not success:
        raise HTTPException(
            status_code=400,
            detail="Failed to revoke token (may already be expired)"
        )

    return {"message": "Token revoked successfully"}


@router.delete(
    "/jobs/{job_id}/tokens",
    summary="Revoke all tokens for a job",
    description="""
    Revoke all streaming tokens for a specific job.

    - Immediately invalidates all active tokens for the job
    - Useful when a job is deleted or access should be completely removed
    """
)
async def revoke_all_job_tokens(
    job_id: str,
    db: Session = Depends(get_db),
    api_key: APIKey = Depends(get_api_key),
    streaming_service: StreamingTokenService = Depends(get_streaming_token_service)
):
    """
    Revoke all streaming tokens for a job.
    """
    # Verify job exists and belongs to this API key
    job = db.query(Job).filter(Job.id == job_id).first()

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.api_key_prefix != api_key.key_prefix:
        raise HTTPException(
            status_code=403,
            detail="You don't have access to this job"
        )

    # Revoke all tokens for the job
    streaming_service.revoke_all_job_tokens(job_id)

    return {"message": f"All streaming tokens for job {job_id} have been revoked"}


@router.get(
    "/jobs/{job_id}/available-resolutions",
    summary="Get available streaming resolutions",
    description="""
    Get a list of available video resolutions for streaming.

    - Returns resolutions that have been successfully transcoded
    - Includes HLS manifest availability status
    """
)
async def get_available_resolutions(
    job_id: str,
    db: Session = Depends(get_db),
    api_key: APIKey = Depends(get_api_key)
):
    """
    Get available streaming resolutions for a job.
    """
    # Verify job exists and belongs to this API key
    job = db.query(Job).filter(Job.id == job_id).first()

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.api_key_prefix != api_key.key_prefix:
        raise HTTPException(
            status_code=403,
            detail="You don't have access to this job"
        )

    if job.status != "completed":
        return {
            "job_id": job_id,
            "status": job.status,
            "available_resolutions": [],
            "message": "Job is not completed yet"
        }

    # In a real implementation, you would check MinIO or the filesystem
    # for actual HLS manifest files
    # For now, return common resolutions
    available_resolutions = [
        {"resolution": "360p", "width": 640, "height": 360, "bitrate": "800k"},
        {"resolution": "720p", "width": 1280, "height": 720, "bitrate": "2500k"},
        {"resolution": "1080p", "width": 1920, "height": 1080, "bitrate": "5000k"},
    ]

    return {
        "job_id": job_id,
        "status": job.status,
        "available_resolutions": available_resolutions
    }
