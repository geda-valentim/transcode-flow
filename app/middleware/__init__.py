"""
Middleware module for FastAPI application.

This module contains custom middleware for:
- Prometheus metrics collection
- Request tracking
"""
from app.middleware.metrics import MetricsMiddleware

__all__ = ["MetricsMiddleware"]
