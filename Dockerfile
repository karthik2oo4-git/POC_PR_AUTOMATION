FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim

WORKDIR /app

COPY pyproject.toml README.md ./
RUN uv sync --no-dev --no-install-project

COPY src ./src
COPY .env.example ./.env.example

RUN uv sync --no-dev

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "github_ci_governance_app.main:app", "--host", "0.0.0.0", "--port", "8000"]

# Made with Bob
