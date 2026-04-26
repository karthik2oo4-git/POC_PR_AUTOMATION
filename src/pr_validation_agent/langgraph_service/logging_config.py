"""Structured logging with secret redaction."""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp


# Common secret patterns to redact
SECRET_PATTERNS = [
    (r"(?i)(api[_-]?key)[:\s=]+['\"]?([a-zA-Z0-9_\-]{20,})['\"]?", r"\1=***REDACTED***"),
    (r"(?i)(token)[:\s=]+['\"]?([a-zA-Z0-9_\-]{20,})['\"]?", r"\1=***REDACTED***"),
    (r"(?i)(password)[:\s=]+['\"]?([^\s'\"]+)['\"]?", r"\1=***REDACTED***"),
    (r"(?i)(secret)[:\s=]+['\"]?([a-zA-Z0-9_\-]{20,})['\"]?", r"\1=***REDACTED***"),
    (r"(?i)(authorization)[:\s=]+Bearer\s+[a-zA-Z0-9_\-\.]+", r"\1=Bearer ***REDACTED***"),
    (r"(?i)(x-api-key)[:\s=]+['\"]?([a-zA-Z0-9_\-]{20,})['\"]?", r"\1=***REDACTED***"),
]


def redact_secrets(text: str) -> str:
    """Redact sensitive information from text.
    
    Args:
        text: The text to redact
        
    Returns:
        Text with secrets replaced with ***REDACTED***
    """
    for pattern, replacement in SECRET_PATTERNS:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    return text


def redact_dict(data: dict[str, Any]) -> dict[str, Any]:
    """Redact sensitive keys in a dictionary.
    
    Args:
        data: Dictionary to redact
        
    Returns:
        Dictionary with sensitive values replaced
    """
    redacted = {}
    sensitive_keys = {
        "token", "api_key", "apikey", "password", "secret",
        "authorization", "x-api-key", "x_api_key",
        "langgraph_service_token"
    }
    
    for key, value in data.items():
        if key.lower() in sensitive_keys:
            redacted[key] = "***REDACTED***"
        elif isinstance(value, dict):
            redacted[key] = redact_dict(value)
        elif isinstance(value, str):
            redacted[key] = redact_secrets(value)
        else:
            redacted[key] = value
    
    return redacted


class StructuredLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware for structured JSON logging with redaction."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)
        self.logger = logging.getLogger("pr_validation_agent.service")
        
        # Ensure we have a JSON formatter
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '{"time": "%(asctime)s", "level": "%(levelname)s", "message": "%(message)s"}'
            )
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.INFO)

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        """Log request and response with structured format."""
        start_time = time.monotonic()
        
        # Extract safe request info
        request_log = {
            "method": request.method,
            "path": request.url.path,
            "query": str(request.query_params),
        }
        
        try:
            response = await call_next(request)
            duration_ms = round((time.monotonic() - start_time) * 1000, 2)
            
            self.logger.info(
                json.dumps({
                    "event": "http_request",
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "duration_ms": duration_ms,
                })
            )
            
            return response
        except Exception as exc:
            duration_ms = round((time.monotonic() - start_time) * 1000, 2)
            
            self.logger.error(
                json.dumps({
                    "event": "http_error",
                    "method": request.method,
                    "path": request.url.path,
                    "error": str(exc),
                    "duration_ms": duration_ms,
                })
            )
            raise


def create_structured_logger(name: str) -> logging.Logger:
    """Create a structured logger that redacts secrets.
    
    Args:
        name: Logger name
        
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            '{"time": "%(asctime)s", "level": "%(levelname)s", "message": "%(message)s"}'
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    
    return logger


def log_analysis_request(
    owner: str,
    repo: str,
    pr_number: int,
    mode: str,
    head_sha: str,
    base_branch: str,
    files_count: int,
) -> None:
    """Log an analysis request with safe fields."""
    logger = create_structured_logger("pr_validation_agent.analysis")
    logger.info(
        json.dumps({
            "event": "analysis_request",
            "owner": owner,
            "repo": repo,
            "pr_number": pr_number,
            "mode": mode,
            "head_sha": head_sha[:8],  # Log only first 8 chars of SHA
            "base_branch": base_branch,
            "files_count": files_count,
        })
    )


def log_analysis_response(
    owner: str,
    repo: str,
    pr_number: int,
    mode: str,
    latency_ms: float,
    status: str,
) -> None:
    """Log an analysis response with safe fields."""
    logger = create_structured_logger("pr_validation_agent.analysis")
    logger.info(
        json.dumps({
            "event": "analysis_response",
            "owner": owner,
            "repo": repo,
            "pr_number": pr_number,
            "mode": mode,
            "latency_ms": latency_ms,
            "status": status,
        })
    )
