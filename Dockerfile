FROM ghcr.io/astral-sh/uv:0.10.7 AS uv

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app
COPY --from=uv /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock README.md ./
COPY src ./src

RUN uv sync --frozen --no-dev

CMD ["pr-validation-ci"]
