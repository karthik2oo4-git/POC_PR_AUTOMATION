"""Service authentication and token validation."""

from __future__ import annotations

import os
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthenticationCredentials, HTTPBearer

security = HTTPBearer(auto_error=False)


def get_service_token() -> str | None:
    """Get the expected service token from environment.
    
    Returns None if not configured, indicating auth is disabled.
    """
    return os.getenv("LANGGRAPH_SERVICE_TOKEN")


async def verify_token(credentials: Annotated[HTTPAuthenticationCredentials | None, Depends(security)]) -> None:
    """Verify the Authorization header contains a valid bearer token.
    
    Args:
        credentials: HTTPAuthenticationCredentials from the request
        
    Raises:
        HTTPException: 401 if token is missing or invalid
    """
    expected_token = get_service_token()
    
    # If no token is configured in the environment, auth is disabled
    if not expected_token:
        return
    
    # If auth is required but no credentials provided
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Verify the token matches (use constant-time comparison to prevent timing attacks)
    if not _constant_time_equal(credentials.credentials, expected_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )


def _constant_time_equal(a: str, b: str) -> bool:
    """Compare two strings in constant time to prevent timing attacks."""
    if len(a) != len(b):
        return False
    return sum(ca == cb for ca, cb in zip(a, b, strict=False)) == len(a)
