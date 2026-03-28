# Stage 1: Build dependencies
FROM python:3.12-slim AS builder

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Copy dependency metadata first for better layer caching.
# Note: backend build context does not include the repository-level uv.lock.
COPY pyproject.toml ./

# Install runtime dependencies into .venv without installing the local project.
RUN uv sync --no-cache --no-dev --no-install-project

# Stage 2: Runtime image
FROM python:3.12-slim

WORKDIR /app

# Ensure uv binary is available in the runtime image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Copy only the prepared virtual environment from the builder stage.
COPY --from=builder /app/.venv /app/.venv

# Install postgres client utilities (pg_isready)
RUN apt-get update \
	&& apt-get install -y --no-install-recommends postgresql-client \
	&& rm -rf /var/lib/apt/lists/*

# Copy application source code and entrypoint.
COPY . .

# Use the virtual environment by default.
ENV PATH="/app/.venv/bin:$PATH"
RUN chmod +x /app/docker-entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8000"]