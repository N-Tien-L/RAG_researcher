FROM python:3.11-slim

# Prevent Python from writing .pyc files and enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install dependencies using uv
RUN uv sync --frozen --no-cache

# copy the rest of the app
COPY . .

# streamlit use port 8501 by default
EXPOSE 8501

CMD ["uv", "run", "streamlit", "run", "app/app.py", "--server.address=0.0.0.0"]