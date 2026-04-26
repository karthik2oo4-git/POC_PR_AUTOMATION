"""Service perimeter protections: rate limiting, request limits, timeouts."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException, Request, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp


# Default limits for the first rollout
DEFAULT_MAX_REQUEST_BODY_BYTES = 2 * 1024 * 1024  # 2 MB
DEFAULT_REQUEST_TIMEOUT_SECONDS = 90
DEFAULT_MAX_CONCURRENT_REQUESTS = 10
DEFAULT_RATE_LIMIT_REQUESTS = 100
DEFAULT_RATE_LIMIT_WINDOW_SECONDS = 60


class RateLimiter:
    """Simple in-memory rate limiter per token/repository."""

    def __init__(self, max_requests: int, window_seconds: int) -> None:
        """Initialize rate limiter.
        
        Args:
            max_requests: Max requests allowed in the window
            window_seconds: Time window in seconds
        """
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests: dict[str, list[datetime]] = {}

    def is_allowed(self, key: str) -> bool:
        """Check if request is allowed for the given key.
        
        Args:
            key: Rate limit key (e.g., token or repository)
            
        Returns:
            True if request is allowed, False otherwise
        """
        now = datetime.now(timezone.utc)
        window_start = now - timedelta(seconds=self.window_seconds)

        if key not in self.requests:
            self.requests[key] = []

        # Remove old requests outside the window
        self.requests[key] = [
            req_time
            for req_time in self.requests[key]
            if req_time > window_start
        ]

        if len(self.requests[key]) < self.max_requests:
            self.requests[key].append(now)
            return True

        return False


class ConcurrencyLimiter:
    """Simple concurrency limiter using semaphore."""

    def __init__(self, max_concurrent: int) -> None:
        """Initialize concurrency limiter.
        
        Args:
            max_concurrent: Maximum concurrent requests
        """
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.max_concurrent = max_concurrent

    async def acquire(self) -> Any:
        """Acquire a concurrency slot."""
        return await self.semaphore.acquire()

    def release(self) -> None:
        """Release a concurrency slot."""
        self.semaphore.release()

    def current_count(self) -> int:
        """Get current number of in-flight requests."""
        return self.max_concurrent - self.semaphore._value


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    """Middleware to enforce max request body size."""

    def __init__(self, app: ASGIApp, max_body_bytes: int = DEFAULT_MAX_REQUEST_BODY_BYTES) -> None:
        super().__init__(app)
        self.max_body_bytes = max_body_bytes

    async def dispatch(self, request: Request, call_next: Any) -> Any:
        """Check request size before processing."""
        if request.method in {"POST", "PUT", "PATCH"}:
            content_length = request.headers.get("content-length")
            if content_length and int(content_length) > self.max_body_bytes:
                raise HTTPException(
                    status_code=status.HTTP_413_PAYLOAD_TOO_LARGE,
                    detail=f"Request body exceeds maximum size of {self.max_body_bytes} bytes",
                )

        return await call_next(request)


class ConcurrencyLimitMiddleware(BaseHTTPMiddleware):
    """Middleware to enforce max concurrent requests."""

    def __init__(self, app: ASGIApp, max_concurrent: int = DEFAULT_MAX_CONCURRENT_REQUESTS) -> None:
        super().__init__(app)
        self.limiter = ConcurrencyLimiter(max_concurrent)

    async def dispatch(self, request: Request, call_next: Any) -> Any:
        """Enforce concurrency limit."""
        await self.limiter.acquire()
        try:
            return await call_next(request)
        finally:
            self.limiter.release()


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Middleware to enforce rate limiting per repository or token."""

    def __init__(
        self,
        app: ASGIApp,
        max_requests: int = DEFAULT_RATE_LIMIT_REQUESTS,
        window_seconds: int = DEFAULT_RATE_LIMIT_WINDOW_SECONDS,
    ) -> None:
        super().__init__(app)
        self.limiter = RateLimiter(max_requests, window_seconds)

    async def dispatch(self, request: Request, call_next: Any) -> Any:
        """Enforce rate limit."""
        # Use Authorization header as rate limit key, fallback to remote IP
        key = request.headers.get("authorization", request.client.host if request.client else "unknown")

        if not self.limiter.is_allowed(key):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded",
                headers={"Retry-After": str(self.limiter.window_seconds)},
            )

        return await call_next(request)


def validate_analysis_request_fields(data: dict[str, Any]) -> None:
    """Validate required fields in analysis request.
    
    Args:
        data: Request data dictionary
        
    Raises:
        HTTPException: 400 if required fields are missing or invalid
    """
    required_fields = {
        "pr": ["owner", "repo", "number", "head_sha", "base_sha", "head_ref", "base_ref"],
        "files_changed": None,  # Just needs to exist
    }

    errors = []

    # Check top-level fields
    if "pr" not in data:
        errors.append("Missing required field: pr")
    else:
        pr = data["pr"]
        if not isinstance(pr, dict):
            errors.append("Field 'pr' must be an object")
        else:
            for field in required_fields["pr"]:
                if field not in pr:
                    errors.append(f"Missing required field: pr.{field}")
                elif not pr[field]:  # Check for empty values
                    errors.append(f"Field 'pr.{field}' cannot be empty")

    if "files_changed" not in data:
        errors.append("Missing required field: files_changed")
    elif not isinstance(data["files_changed"], list):
        errors.append("Field 'files_changed' must be an array")

    if errors:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"errors": errors},
        )
