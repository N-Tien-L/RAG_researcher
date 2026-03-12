# Stage 1: Giai đoạn xây dựng (Builder)
FROM python:3.12-slim AS builder

# Cài đặt uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Chỉ copy file quản lý thư viện để tận dụng cache của Docker
COPY pyproject.toml uv.lock ./

# Cài đặt dependencies vào folder .venv, không cài chính project
# --no-dev: loại bỏ các thư viện dùng để test/linting nếu có
RUN uv sync --frozen --no-cache --no-dev --no-install-project

# Stage 2: Giai đoạn chạy (Runtime) - Image cuối cùng sẽ dùng cái này
FROM python:3.12-slim

WORKDIR /app

# Ensure uv binary is available in the runtime image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Chỉ copy folder .venv (đã chứa mọi thư viện) từ stage builder
COPY --from=builder /app/.venv /app/.venv

# Copy source code và entrypoint
COPY . .

# Thiết kế entrypoint sử dụng môi trường ảo
ENV PATH="/app/.venv/bin:$PATH"
RUN chmod +x /app/docker-entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/app/docker-entrypoint.sh"]