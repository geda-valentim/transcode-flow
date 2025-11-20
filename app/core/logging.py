"""
Structured logging configuration with JSON formatter.

This module provides:
- JSONFormatter for structured JSON logging
- Request ID tracking for distributed tracing
- Contextual logging with additional fields
- ELK/Splunk compatible output format
"""
import logging
import json
import traceback
from datetime import datetime, timezone
from typing import Any, Dict, Optional
import sys


class JSONFormatter(logging.Formatter):
    """
    Custom JSON formatter for structured logging.

    Outputs logs in JSON format with:
    - Timestamp (ISO 8601)
    - Log level
    - Logger name
    - Message
    - Exception info (if present)
    - Additional context fields

    Example output:
    {
        "timestamp": "2025-01-19T10:30:45.123456Z",
        "level": "INFO",
        "logger": "app.api.v1.endpoints.jobs",
        "message": "Job created successfully",
        "job_id": "abc123",
        "api_key_prefix": "sk_live_"
    }
    """

    def __init__(
        self,
        fmt_keys: Optional[Dict[str, str]] = None,
        datefmt: str = "%Y-%m-%dT%H:%M:%S"
    ):
        """
        Initialize JSON formatter.

        Args:
            fmt_keys: Dictionary mapping log record attributes to JSON keys
            datefmt: Date format string (default: ISO 8601)
        """
        super().__init__()
        self.fmt_keys = fmt_keys or {
            "timestamp": "timestamp",
            "level": "levelname",
            "logger": "name",
            "message": "message",
            "module": "module",
            "function": "funcName",
            "line": "lineno",
        }
        self.datefmt = datefmt

    def format(self, record: logging.LogRecord) -> str:
        """
        Format log record as JSON string.

        Args:
            record: Log record to format

        Returns:
            JSON-formatted log string
        """
        # Build base log entry
        log_entry: Dict[str, Any] = {}

        # Add timestamp with microseconds
        log_entry["timestamp"] = datetime.fromtimestamp(
            record.created,
            tz=timezone.utc
        ).isoformat()

        # Add standard fields
        log_entry["level"] = record.levelname
        log_entry["logger"] = record.name
        log_entry["message"] = record.getMessage()

        # Add optional location information
        if hasattr(record, 'pathname'):
            log_entry["file"] = record.pathname
        if hasattr(record, 'lineno'):
            log_entry["line"] = record.lineno
        if hasattr(record, 'funcName'):
            log_entry["function"] = record.funcName

        # Add process/thread information
        if hasattr(record, 'process'):
            log_entry["process_id"] = record.process
        if hasattr(record, 'thread'):
            log_entry["thread_id"] = record.thread
        if hasattr(record, 'threadName'):
            log_entry["thread_name"] = record.threadName

        # Add exception information if present
        if record.exc_info:
            log_entry["exception"] = {
                "type": record.exc_info[0].__name__ if record.exc_info[0] else None,
                "message": str(record.exc_info[1]) if record.exc_info[1] else None,
                "traceback": self.formatException(record.exc_info) if record.exc_info else None
            }

        # Add stack info if present
        if hasattr(record, 'stack_info') and record.stack_info:
            log_entry["stack_info"] = record.stack_info

        # Add custom fields from extra parameter
        # These are added to the record by passing extra={'key': 'value'} to logger
        for key, value in record.__dict__.items():
            # Skip standard logging fields
            if key not in [
                'name', 'msg', 'args', 'created', 'filename', 'funcName',
                'levelname', 'levelno', 'lineno', 'module', 'msecs',
                'pathname', 'process', 'processName', 'relativeCreated',
                'thread', 'threadName', 'exc_info', 'exc_text', 'stack_info',
                'getMessage', 'message'
            ]:
                # Add custom field to log entry
                log_entry[key] = self._serialize_value(value)

        # Return JSON string
        return json.dumps(log_entry, default=str, ensure_ascii=False)

    def _serialize_value(self, value: Any) -> Any:
        """
        Serialize value for JSON output.

        Handles common Python types that aren't JSON serializable.

        Args:
            value: Value to serialize

        Returns:
            JSON-serializable value
        """
        # Handle datetime objects
        if isinstance(value, datetime):
            return value.isoformat()

        # Handle bytes
        if isinstance(value, bytes):
            try:
                return value.decode('utf-8')
            except UnicodeDecodeError:
                return f"<binary data: {len(value)} bytes>"

        # Handle exceptions
        if isinstance(value, Exception):
            return {
                "type": type(value).__name__,
                "message": str(value),
                "traceback": traceback.format_exc() if sys.exc_info()[0] else None
            }

        # Handle other objects with __dict__
        if hasattr(value, '__dict__'):
            return str(value)

        return value


class ContextualLogger:
    """
    Wrapper for logger that adds contextual information to all log messages.

    Usage:
        logger = ContextualLogger(logging.getLogger(__name__))
        logger.set_context(job_id="abc123", api_key_prefix="sk_live_")
        logger.info("Processing job")  # Will include job_id and api_key_prefix
    """

    def __init__(self, logger: logging.Logger):
        """
        Initialize contextual logger.

        Args:
            logger: Base logger to wrap
        """
        self.logger = logger
        self.context: Dict[str, Any] = {}

    def set_context(self, **kwargs):
        """
        Set context fields that will be added to all log messages.

        Args:
            **kwargs: Key-value pairs to add to context
        """
        self.context.update(kwargs)

    def clear_context(self):
        """Clear all context fields."""
        self.context.clear()

    def _log_with_context(self, level: int, msg: str, *args, **kwargs):
        """
        Log message with context.

        Args:
            level: Log level
            msg: Log message
            *args: Positional arguments for message formatting
            **kwargs: Additional context fields
        """
        # Merge context with extra kwargs
        extra = kwargs.get('extra', {})
        extra.update(self.context)
        kwargs['extra'] = extra

        # Log message
        self.logger.log(level, msg, *args, **kwargs)

    def debug(self, msg: str, *args, **kwargs):
        """Log debug message with context."""
        self._log_with_context(logging.DEBUG, msg, *args, **kwargs)

    def info(self, msg: str, *args, **kwargs):
        """Log info message with context."""
        self._log_with_context(logging.INFO, msg, *args, **kwargs)

    def warning(self, msg: str, *args, **kwargs):
        """Log warning message with context."""
        self._log_with_context(logging.WARNING, msg, *args, **kwargs)

    def error(self, msg: str, *args, **kwargs):
        """Log error message with context."""
        self._log_with_context(logging.ERROR, msg, *args, **kwargs)

    def critical(self, msg: str, *args, **kwargs):
        """Log critical message with context."""
        self._log_with_context(logging.CRITICAL, msg, *args, **kwargs)

    def exception(self, msg: str, *args, **kwargs):
        """Log exception with context."""
        kwargs['exc_info'] = True
        self._log_with_context(logging.ERROR, msg, *args, **kwargs)


def setup_json_logging(
    level: str = "INFO",
    logger_name: Optional[str] = None
) -> logging.Logger:
    """
    Setup JSON logging for a logger.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        logger_name: Name of logger to configure (None for root logger)

    Returns:
        Configured logger with JSON formatter
    """
    # Get logger
    logger = logging.getLogger(logger_name)
    logger.setLevel(getattr(logging, level.upper()))

    # Remove existing handlers
    logger.handlers.clear()

    # Create console handler with JSON formatter
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(JSONFormatter())
    logger.addHandler(console_handler)

    # Prevent propagation to root logger
    logger.propagate = False

    return logger


def get_logger(name: str, with_context: bool = False) -> logging.Logger:
    """
    Get logger with optional contextual logging support.

    Args:
        name: Logger name (typically __name__)
        with_context: Whether to return ContextualLogger wrapper

    Returns:
        Logger instance (plain or contextual)
    """
    logger = logging.getLogger(name)

    if with_context:
        return ContextualLogger(logger)

    return logger
