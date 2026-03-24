FROM python:3.12-slim

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Install Node.js (required for any npx-based MCP tools)
RUN apt-get update && apt-get install -y nodejs npm && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
RUN uv sync --no-dev

COPY agent/ ./agent/

ENV PYTHONUNBUFFERED=1
ENV PORT=8080

EXPOSE 8080

CMD ["uv", "run", "uvicorn", "agent.fast_api_app:app", "--host", "0.0.0.0", "--port", "8080"]
