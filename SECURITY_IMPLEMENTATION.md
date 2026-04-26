# Security Implementation Guide

Complete implementation of tasks from NEXT_STEPS.md lines 57-130: authentication, service protection, and structured logging.

## Quick Reference

### Files Changed/Created

**New Files:**
- `langgraph_service/auth.py` - Token validation
- `langgraph_service/logging_config.py` - JSON logging + redaction
- `langgraph_service/service_protections.py` - Rate limits, concurrency, size limits
- `tests/test_service_security.py` - Unit tests

**Modified Files:**
- `langgraph_service/app.py` - Added middleware + auth dependency
- `langgraph_client.py` - Added token header support

### Quick Start

```bash
# Start service with auth
export LANGGRAPH_SERVICE_TOKEN="test-token-123"
python -m pr_validation_agent.langgraph_service.app

# Test endpoint
curl -X POST http://localhost:8000/v1/analyze/failure \
  -H "Authorization: Bearer test-token-123" \
  -H "Content-Type: application/json" \
  -d '{
    "pr": {
      "owner": "org", "repo": "repo", "number": 1,
      "head_sha": "abc123", "base_sha": "def456",
      "head_ref": "feature", "base_ref": "main", "author": "user"
    },
    "files_changed": ["src/main.py"]
  }'
```

### Status Codes

| Code | Condition |
|------|-----------|
| 200 | Success (or auth disabled) |
| 400 | Invalid/missing PR fields |
| 401 | Invalid/missing token |
| 413 | Payload > 2 MB |
| 429 | Too many requests |
| 500 | Service error |

---

## 1. Service Authentication

### Implementation

**Module:** `langgraph_service/auth.py`

- HTTPBearer token validation via FastAPI security
- Constant-time comparison prevents timing attacks
- Optional: Auth disabled if `LANGGRAPH_SERVICE_TOKEN` env var not set
- Invalid token → `401 Unauthorized`

### Configuration

```bash
# Enable authentication
export LANGGRAPH_SERVICE_TOKEN="your-secure-token-here"

# Or disable by not setting it (endpoint becomes public)
```

### Client Usage

```python
from pr_validation_agent.langgraph_client import LangGraphClient

# Token auto-read from environment
client = LangGraphClient()  # LANGGRAPH_SERVICE_TOKEN env var
response = client.analyze(request, mode="failure")

# Or pass explicitly
client = LangGraphClient(base_url="http://localhost:8000", token="my-token")
```

The client automatically sends:
```
Authorization: Bearer my-token
```

### GitHub Actions Setup

```yaml
env:
  LANGGRAPH_SERVICE_TOKEN: ${{ secrets.LANGGRAPH_SERVICE_TOKEN }}
  LANGGRAPH_SERVICE_URL: ${{ secrets.LANGGRAPH_SERVICE_URL }}
```

---

## 2. Service Perimeter Protection

### Implementation

**Module:** `langgraph_service/service_protections.py`

Four protection layers via middleware:

| Protection | Limit | Response | Configurable |
|-----------|-------|----------|--------------|
| Request Size | 2 MB | 413 | Yes |
| Rate Limiting | 100 req/60s per token/IP | 429 | Yes |
| Concurrency | 10 max concurrent | Queue + timeout | Yes |
| Request Validation | All PR fields required | 400 | Via model |

### Configuration

In `app.py`, adjust middleware parameters:

```python
# Rate limiting: requests per window per key
RateLimitMiddleware(max_requests=100, window_seconds=60)

# Concurrency: max simultaneous requests
ConcurrencyLimitMiddleware(max_concurrent=10)

# Size: max body bytes
RequestSizeLimitMiddleware(max_body_bytes=2*1024*1024)
```

### Request Validation

Required PR fields (all non-empty):
- `owner`, `repo`, `number`, `head_sha`, `base_sha`, `head_ref`, `base_ref`, `author`
- `files_changed` must be array

Validation error (400):
```json
{
  "detail": {
    "errors": [
      "Missing required field: pr.owner",
      "Field 'files_changed' must be an array"
    ]
  }
}
```

---

## 3. Structured Logging & Redaction

### Implementation

**Module:** `langgraph_service/logging_config.py`

- JSON structured logs for all HTTP requests/responses
- Automatic secret redaction
- Safe PR context logging (owner, repo, number, mode, truncated SHA)
- Latency measurement

### Log Examples

Analysis request:
```json
{
  "event": "analysis_request",
  "owner": "myorg",
  "repo": "myrepo",
  "pr_number": 42,
  "mode": "failure",
  "head_sha": "abc12345",
  "base_branch": "main",
  "files_count": 5
}
```

Analysis response:
```json
{
  "event": "analysis_response",
  "owner": "myorg",
  "repo": "myrepo",
  "pr_number": 42,
  "mode": "failure",
  "latency_ms": 5333.45,
  "status": "success"
}
```

### Secret Redaction

Automatically redacts:
- `api_key`, `apikey`, `API_KEY`
- `token`, `authorization`, `LANGGRAPH_SERVICE_TOKEN`
- `password`
- `secret`
- Connection strings

Example:
```python
text = 'API_KEY="sk-1234567890abcdefghij"'
redacted = redact_secrets(text)
# Result: 'API_KEY="***REDACTED***"'
```

---

## Testing

### Unit Tests

Run all security tests:
```bash
python -m pytest tests/test_service_security.py -v
```

Run specific test class:
```bash
python -m pytest tests/test_service_security.py::TestAuthentication -v
```

Test coverage:
- Authentication (constant-time comparison, token validation)
- Secret redaction (text patterns, dictionary keys)
- Rate limiting (per-key tracking, window management)
- Request validation (required fields, types)
- Endpoint integration (auth required, public endpoints)

### Manual Testing

**1. Authentication**

```bash
# Valid token
curl -X POST http://localhost:8000/v1/analyze/failure \
  -H "Authorization: Bearer test-token" \
  -H "Content-Type: application/json" \
  -d '{"pr": {...}, "files_changed": []}'
# Expected: 200 or 400 (invalid request)

# Missing token (if enabled)
curl -X POST http://localhost:8000/v1/analyze/failure \
  -H "Content-Type: application/json" \
  -d '{"pr": {...}, "files_changed": []}'
# Expected: 401 Unauthorized

# Wrong token
curl -X POST http://localhost:8000/v1/analyze/failure \
  -H "Authorization: Bearer wrong-token" \
  -H "Content-Type: application/json" \
  -d '{"pr": {...}, "files_changed": []}'
# Expected: 401 Unauthorized
```

**2. Request Size Limits**

```bash
# Generate 3MB payload
python -c "import json; print(json.dumps({'pr': {'owner': 'x', 'repo': 'x', 'number': 1, 'head_sha': 'x'*3000000, 'base_sha': 'x', 'head_ref': 'x', 'base_ref': 'x'}, 'files_changed': []}))" > large.json

curl -X POST http://localhost:8000/v1/analyze/failure \
  -H "Authorization: Bearer token" \
  -H "Content-Type: application/json" \
  -d @large.json
# Expected: 413 Payload Too Large
```

**3. Rate Limiting**

```bash
# Send 101 requests (limit is 100/60s)
for i in {1..101}; do
  curl -X POST http://localhost:8000/v1/analyze/failure \
    -H "Authorization: Bearer token" \
    -H "Content-Type: application/json" \
    -d '{"pr": {...}, "files_changed": []}'
done
# Request 101 expected: 429 Too Many Requests
```

**4. Request Validation**

```bash
# Missing PR field
curl -X POST http://localhost:8000/v1/analyze/failure \
  -H "Authorization: Bearer token" \
  -H "Content-Type: application/json" \
  -d '{"pr": {"owner": "x"}, "files_changed": []}'
# Expected: 400 Bad Request

# Missing files_changed
curl -X POST http://localhost:8000/v1/analyze/failure \
  -H "Authorization: Bearer token" \
  -H "Content-Type: application/json" \
  -d '{"pr": {"owner": "x", "repo": "y", "number": 1, "head_sha": "a", "base_sha": "b", "head_ref": "c", "base_ref": "d"}}'
# Expected: 400 Bad Request
```

**5. Logging Output**

Check logs contain JSON structure without secrets:
```bash
# Service logs should show:
# {"time": "...", "level": "INFO", "message": "{\"event\": \"analysis_request\", ...}"}
# No raw tokens visible
```

---

## Deployment

### Environment Variables

```bash
# Required to enable service
LANGGRAPH_SERVICE_URL="http://localhost:8000"

# Optional - enables authentication
LANGGRAPH_SERVICE_TOKEN="your-secure-token-here"
```

### GitHub Actions Workflow

```yaml
name: PR Validation
on:
  pull_request:
    types: [opened, synchronize, reopened]

jobs:
  validate:
    runs-on: ubuntu-latest
    env:
      LANGGRAPH_SERVICE_TOKEN: ${{ secrets.LANGGRAPH_SERVICE_TOKEN }}
      LANGGRAPH_SERVICE_URL: ${{ secrets.LANGGRAPH_SERVICE_URL }}
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - run: pip install -e .
      - run: python -m pr_validation_agent.ci.runner
        continue-on-error: true
```

### Generate Service Token

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

Then add to GitHub Secrets:
1. Settings → Secrets and variables → Actions
2. New repository secret
3. Name: `LANGGRAPH_SERVICE_TOKEN`
4. Value: Paste generated token

### Docker Deployment

**Dockerfile:**
```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY pyproject.toml .
RUN pip install -e .

RUN useradd -m -u 1000 appuser
USER appuser

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s \
  CMD curl -f http://localhost:8000/healthz || exit 1

CMD ["python", "-m", "pr_validation_agent.langgraph_service.app"]
```

**Build and run:**
```bash
docker build -t pr-validation:latest .

docker run -p 8000:8000 \
  -e LANGGRAPH_SERVICE_TOKEN="your-token" \
  -e OPENAI_API_KEY="sk-..." \
  pr-validation:latest
```

### Kubernetes Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: pr-validation-service
spec:
  replicas: 2
  selector:
    matchLabels:
      app: pr-validation-service
  template:
    metadata:
      labels:
        app: pr-validation-service
    spec:
      containers:
      - name: service
        image: pr-validation:latest
        ports:
        - containerPort: 8000
        env:
        - name: LANGGRAPH_SERVICE_TOKEN
          valueFrom:
            secretKeyRef:
              name: pr-validation-secrets
              key: service-token
        - name: OPENAI_API_KEY
          valueFrom:
            secretKeyRef:
              name: pr-validation-secrets
              key: openai-api-key
        resources:
          requests:
            memory: "512Mi"
            cpu: "250m"
          limits:
            memory: "1Gi"
            cpu: "500m"
        livenessProbe:
          httpGet:
            path: /healthz
            port: 8000
          initialDelaySeconds: 10
          periodSeconds: 30
        readinessProbe:
          httpGet:
            path: /healthz
            port: 8000
          initialDelaySeconds: 5
          periodSeconds: 10
---
apiVersion: v1
kind: Secret
metadata:
  name: pr-validation-secrets
type: Opaque
stringData:
  service-token: "your-token-here"
  openai-api-key: "sk-..."
```

---

## Monitoring & Logging Integration

### Log Aggregation

Service outputs JSON structured logs to stdout. Configure your logging system:

**CloudWatch:**
```yaml
logs:
  - eventSource: arn:aws:logs:region:account:log-group:/aws/ecs/pr-validation
    subscriptionFilters:
    - filterPattern: "ERROR"
      destinationArn: arn:aws:lambda:region:account:function:alert
```

**Datadog:**
```yaml
logs:
  - service: pr-validation
    source: docker
    log_processing_rules:
    - type: parse-json
```

### Metrics to Monitor

- `duration_ms`: Request latency
- HTTP status codes: 400, 401, 413, 429, 500
- `event`: Type of operation (analysis_request, analysis_response, http_error)

---

## Security Checklist

- [ ] Token generated using `secrets.token_urlsafe()`
- [ ] Token stored in GitHub secrets, not in code
- [ ] Service deployed over HTTPS
- [ ] Rate limits tuned to expected usage
- [ ] Logs redacted before sending to third parties
- [ ] Service runs as non-root user
- [ ] No internal stack traces in error responses
- [ ] All required PR fields validated
- [ ] Concurrency limits prevent resource exhaustion
- [ ] Health check monitored
- [ ] Secrets rotated regularly (monthly recommended)

---

## Token Rotation

When rotating the service token:

1. **Generate new token:**
   ```bash
   python3 -c "import secrets; print(secrets.token_urlsafe(32))"
   ```

2. **Update GitHub secret:**
   - Settings → Secrets and variables → Actions
   - Edit `LANGGRAPH_SERVICE_TOKEN`
   - Paste new token

3. **Update service environment:**
   - Update `LANGGRAPH_SERVICE_TOKEN` in deployment
   - Restart service

4. **Monitor logs:**
   - Watch for `401` responses from old clients
   - Update client tokens

---

## Troubleshooting

### Service returns 401

```bash
# Verify token is correct
echo $LANGGRAPH_SERVICE_TOKEN

# Test with explicit token
curl -X POST http://localhost:8000/v1/analyze/failure \
  -H "Authorization: Bearer ${LANGGRAPH_SERVICE_TOKEN}" \
  ...
```

### Service returns 413 (Too Large)

- Reduce payload size
- Or increase `max_body_bytes` in `RequestSizeLimitMiddleware`

### Service returns 429 (Too Many Requests)

- Wait for rate limit window to pass (default 60s)
- Or increase `max_requests` in `RateLimitMiddleware`

### Service returns 500

- Check service logs for details
- Verify LLM API keys are valid
- Check LLM service availability

### Logs don't show secret redaction

- Verify `logging_config.py` imported in `app.py`
- Check `StructuredLoggingMiddleware` is added to app
- Test with known secret patterns

---

## Performance Tuning

Adjust these in `app.py` middleware configuration:

```python
# Higher concurrency for more throughput
app.add_middleware(ConcurrencyLimitMiddleware, max_concurrent=20)

# Higher rate limit for more requests per window
app.add_middleware(RateLimitMiddleware, max_requests=200, window_seconds=60)

# Larger request size for bigger payloads
app.add_middleware(RequestSizeLimitMiddleware, max_body_bytes=5*1024*1024)
```

---

## Exit Criteria - All Met ✓

### Authentication
- [x] CI-to-service authentication enforced when configured
- [x] Unauthorized requests blocked (401)
- [x] Token never hardcoded in repo
- [x] Timing attack protection

### Service Protection
- [x] Oversized payloads rejected (413)
- [x] Timeouts don't hang service
- [x] Load spikes don't crash
- [x] Rate limits enforced
- [x] Concurrency limited

### Logging & Redaction
- [x] JSON structured logs
- [x] All secrets redacted
- [x] Safe PR context logged
- [x] Latency measured
- [x] No stack traces in responses

---

## Next Steps

1. **Centralized Logging**: Set up CloudWatch/Datadog/ELK for log aggregation
2. **Metrics**: Export Prometheus metrics for monitoring
3. **Alerts**: Create alert rules for error spikes, rate limit violations
4. **Secrets Manager**: Use AWS Secrets Manager or HashiCorp Vault for token rotation
5. **IP Allowlisting**: Add optional IP range validation
6. **Request Signing**: Consider HMAC request signing for additional security
7. **Audit Logging**: Track all API calls with user/service context
