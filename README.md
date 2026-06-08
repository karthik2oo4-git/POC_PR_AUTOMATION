# GitHub CI Governance App

Production-grade GitHub-native CI orchestration and validation platform built with FastAPI and managed entirely with UV.

## Core capabilities

- GitHub App authentication with JWT and installation tokens
- FastAPI webhook ingestion at `/webhooks/github`
- SHA-aware staged validation orchestration
- Lightweight and heavy workflow dispatch coordination
- Intelligent test enforcement for newly added source files
- GitHub Checks and PR comment integration
- Idempotent webhook processing with duplicate delivery protection
- Docker-ready local and production deployment flow

## UV-based project setup

Initialize and work with the project using UV only.

```bash
uv venv
source .venv/bin/activate
uv sync
```

If starting from scratch in a new directory, the equivalent initialization flow is:

```bash
uv init github-ci-governance-app
cd github-ci-governance-app
uv venv
source .venv/bin/activate
```

## Dependency management strategy

Runtime dependencies are declared in [`pyproject.toml`](pyproject.toml) and locked reproducibly through [`uv.lock`](uv.lock).

Install runtime and development dependencies:

```bash
uv sync
```

Add new runtime dependencies:

```bash
uv add package-name
```

Add new development dependencies:

```bash
uv add --dev package-name
```

Refresh the lockfile after dependency changes:

```bash
uv lock
```

## Required dependencies

This implementation is designed around the following UV-managed packages:

```bash
uv add fastapi
uv add uvicorn
uv add pygithub
uv add pyjwt
uv add cryptography
uv add httpx
uv add pydantic
uv add pydantic-settings

uv add --dev pytest
uv add --dev pytest-asyncio
uv add --dev ruff
uv add --dev mypy
```

## Environment configuration

Create a local environment file from the example:

```bash
cp .env.example .env
```

Populate the following values:

- `APP_NAME`
- `APP_ENV`
- `APP_HOST`
- `APP_PORT`
- `LOG_LEVEL`
- `GITHUB_APP_ID`
- `GITHUB_WEBHOOK_SECRET`
- `GITHUB_PRIVATE_KEY` or `GITHUB_PRIVATE_KEY_PATH`
- `GITHUB_API_URL`
- `GITHUB_ALLOWED_EVENTS`
- `BASIC_VALIDATION_WORKFLOW`
- `HEAVY_VALIDATION_WORKFLOW`

## Recommended local GitHub App key setup

For local development and POCs, prefer a file path instead of embedding the PEM in [`.env.example`](.env.example).

Example:

```bash
GITHUB_PRIVATE_KEY_PATH=/Users/karthikb/Downloads/pr-automation-poc.private-key.pem
```

The application will read the PEM file directly in [`build_app_jwt()`](src/github_ci_governance_app/integrations/github/auth.py:18).

Fallback option:

- use `GITHUB_PRIVATE_KEY` with full PEM content
- if stored in one line, replace real newlines with `\n`

## Local development

Run the API locally with UV:

```bash
uv run uvicorn github_ci_governance_app.main:app --host 0.0.0.0 --port 8000 --reload
```

## Testing

Run the test suite:

```bash
uv run pytest
```

## Linting and type checking

Run Ruff:

```bash
uv run ruff check .
```

Run Ruff formatting checks if added later:

```bash
uv run ruff format --check .
```

Run MyPy:

```bash
uv run mypy src
```

## Docker workflow

Build the container while preserving UV-based dependency management:

```bash
docker build -t github-ci-governance-app .
```

Run the container:

```bash
docker run --rm -p 8000:8000 --env-file .env github-ci-governance-app
```

## Project structure

```text
.
├── .env.example
├── .gitignore
├── .python-version
├── Dockerfile
├── README.md
├── ARCHITECTURE.md
├── DESIGN.md
├── IMPLEMENTATION_ROADMAP.md
├── pyproject.toml
├── uv.lock
├── src/
│   └── github_ci_governance_app/
│       ├── __init__.py
│       ├── main.py
│       ├── api/
│       ├── core/
│       ├── domain/
│       ├── integrations/
│       ├── orchestration/
│       └── services/
```

## Operational model

The backend never executes tests directly. It only:

- receives GitHub webhooks
- validates signatures and payloads
- coordinates staged workflow execution
- evaluates SHA freshness
- enforces test expectations for newly added files
- publishes GitHub Checks and PR comments

GitHub Actions remains responsible for workflow execution, retries, logs, and runner lifecycle.

## Documentation set

- [`ARCHITECTURE.md`](ARCHITECTURE.md) for system architecture and component boundaries
- [`DESIGN.md`](DESIGN.md) for implementation design details
- [`IMPLEMENTATION_ROADMAP.md`](IMPLEMENTATION_ROADMAP.md) for phased delivery guidance