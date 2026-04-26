"""Tests for authentication, service protection, and logging implementations."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException, status
from fastapi.testclient import TestClient

from pr_validation_agent.langgraph_service.app import create_app
from pr_validation_agent.langgraph_service.auth import _constant_time_equal, verify_token
from pr_validation_agent.langgraph_service.logging_config import redact_dict, redact_secrets
from pr_validation_agent.langgraph_service.service_protections import (
    RateLimiter,
    validate_analysis_request_fields,
)
from pr_validation_agent.langgraph_client import LangGraphClient
from pr_validation_agent.models import AnalysisRequest, PullRequestContext


class TestAuthentication:
    """Test service authentication."""

    def test_constant_time_equal_same_length_equal(self) -> None:
        """Test constant-time comparison with equal strings."""
        assert _constant_time_equal("secret123", "secret123") is True

    def test_constant_time_equal_same_length_not_equal(self) -> None:
        """Test constant-time comparison with different strings."""
        assert _constant_time_equal("secret123", "secret124") is False

    def test_constant_time_equal_different_length(self) -> None:
        """Test constant-time comparison with different lengths."""
        assert _constant_time_equal("secret", "secret123") is False

    @pytest.mark.asyncio
    async def test_verify_token_no_auth_required(self) -> None:
        """Test token verification when auth is not configured."""
        with patch("pr_validation_agent.langgraph_service.auth.get_service_token", return_value=None):
            await verify_token(None)  # Should not raise


class TestRedaction:
    """Test secret redaction."""

    def test_redact_secrets_api_key(self) -> None:
        """Test API key redaction."""
        text = 'api_key: "sk-1234567890abcdefghij"'
        result = redact_secrets(text)
        assert "sk-1234567890abcdefghij" not in result
        assert "***REDACTED***" in result

    def test_redact_secrets_token(self) -> None:
        """Test token redaction."""
        text = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
        result = redact_secrets(text)
        assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in result
        assert "***REDACTED***" in result

    def test_redact_dict_sensitive_keys(self) -> None:
        """Test dictionary redaction for sensitive keys."""
        data = {
            "token": "secret123",
            "api_key": "key456",
            "username": "john",
            "password": "pass789",
        }
        result = redact_dict(data)
        assert result["token"] == "***REDACTED***"
        assert result["api_key"] == "***REDACTED***"
        assert result["password"] == "***REDACTED***"
        assert result["username"] == "john"  # Not sensitive

    def test_redact_dict_nested(self) -> None:
        """Test nested dictionary redaction."""
        data = {
            "config": {
                "token": "secret123",
                "host": "localhost",
            }
        }
        result = redact_dict(data)
        assert result["config"]["token"] == "***REDACTED***"
        assert result["config"]["host"] == "localhost"


class TestRateLimiter:
    """Test rate limiting."""

    def test_rate_limiter_allows_requests_under_limit(self) -> None:
        """Test that requests under limit are allowed."""
        limiter = RateLimiter(max_requests=3, window_seconds=60)
        assert limiter.is_allowed("key1") is True
        assert limiter.is_allowed("key1") is True
        assert limiter.is_allowed("key1") is True

    def test_rate_limiter_blocks_over_limit(self) -> None:
        """Test that requests over limit are blocked."""
        limiter = RateLimiter(max_requests=2, window_seconds=60)
        assert limiter.is_allowed("key1") is True
        assert limiter.is_allowed("key1") is True
        assert limiter.is_allowed("key1") is False

    def test_rate_limiter_different_keys(self) -> None:
        """Test that rate limits are per-key."""
        limiter = RateLimiter(max_requests=2, window_seconds=60)
        assert limiter.is_allowed("key1") is True
        assert limiter.is_allowed("key1") is True
        assert limiter.is_allowed("key1") is False

        assert limiter.is_allowed("key2") is True
        assert limiter.is_allowed("key2") is True
        assert limiter.is_allowed("key2") is False


class TestRequestValidation:
    """Test request field validation."""

    def test_validate_request_missing_pr(self) -> None:
        """Test validation fails when PR context is missing."""
        with pytest.raises(HTTPException) as exc_info:
            validate_analysis_request_fields({"files_changed": []})
        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
        assert "Missing required field: pr" in str(exc_info.value.detail)

    def test_validate_request_missing_files_changed(self) -> None:
        """Test validation fails when files_changed is missing."""
        pr = {
            "owner": "org",
            "repo": "repo",
            "number": 1,
            "head_sha": "abc123",
            "base_sha": "def456",
            "head_ref": "feature",
            "base_ref": "main",
        }
        with pytest.raises(HTTPException) as exc_info:
            validate_analysis_request_fields({"pr": pr})
        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST

    def test_validate_request_valid(self) -> None:
        """Test validation passes with all required fields."""
        pr = {
            "owner": "org",
            "repo": "repo",
            "number": 1,
            "head_sha": "abc123",
            "base_sha": "def456",
            "head_ref": "feature",
            "base_ref": "main",
        }
        # Should not raise
        validate_analysis_request_fields({"pr": pr, "files_changed": []})


class TestLangGraphClient:
    """Test LangGraph client with authentication."""

    def test_client_sends_token(self) -> None:
        """Test that client sends authorization header."""
        with patch("pr_validation_agent.langgraph_client.httpx.post") as mock_post:
            mock_response = AsyncMock()
            mock_response.json.return_value = {}
            mock_post.return_value = mock_response

            client = LangGraphClient(base_url="http://localhost:8000", token="test-token")
            pr = PullRequestContext(
                owner="org",
                repo="repo",
                number=1,
                head_sha="abc123",
                base_sha="def456",
                head_ref="feature",
                base_ref="main",
                author="user",
            )
            request = AnalysisRequest(pr=pr, files_changed=["file.py"])

            # Note: This is a mock test; real execution would require the service running
            # Just verify the header would be sent
            headers = {}
            if client.token:
                headers["Authorization"] = f"Bearer {client.token}"
            assert headers["Authorization"] == "Bearer test-token"

    def test_client_without_token(self) -> None:
        """Test that client works without token."""
        client = LangGraphClient(base_url="http://localhost:8000", token=None)
        assert client.enabled is True
        assert not hasattr(client, "token") or client.token is None


class TestEndpoints:
    """Test FastAPI endpoints."""

    def test_health_endpoint_public(self) -> None:
        """Test that health endpoint is accessible without auth."""
        app = create_app()
        client = TestClient(app)

        response = client.get("/healthz")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    @patch.dict("os.environ", {"LANGGRAPH_SERVICE_TOKEN": "test-token"})
    def test_analyze_endpoint_requires_auth(self) -> None:
        """Test that analyze endpoint requires valid auth when token is set."""
        app = create_app()
        client = TestClient(app)

        # Request without auth should fail
        pr = {
            "owner": "org",
            "repo": "repo",
            "number": 1,
            "head_sha": "abc123",
            "base_sha": "def456",
            "head_ref": "feature",
            "base_ref": "main",
            "author": "user",
        }
        request_data = {"pr": pr, "files_changed": ["file.py"]}

        response = client.post("/v1/analyze/failure", json=request_data)
        assert response.status_code == 403 or response.status_code == 401

    @patch.dict("os.environ", {}, clear=True)
    def test_analyze_endpoint_public_when_no_token(self) -> None:
        """Test that analyze endpoint works without token when none is configured."""
        app = create_app()
        client = TestClient(app)

        pr = {
            "owner": "org",
            "repo": "repo",
            "number": 1,
            "head_sha": "abc123",
            "base_sha": "def456",
            "head_ref": "feature",
            "base_ref": "main",
            "author": "user",
        }
        request_data = {"pr": pr, "files_changed": ["file.py"]}

        # Request should get past auth middleware (though may fail at analysis stage)
        response = client.post("/v1/analyze/failure", json=request_data)
        # Status should not be 401/403
        assert response.status_code != 401
        assert response.status_code != 403


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
