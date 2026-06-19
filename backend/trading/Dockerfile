# Use the official Python image from the Docker Hub
FROM python:3.12-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    # Install into the image's system Python so gunicorn/manage.py stay on PATH
    UV_PROJECT_ENVIRONMENT=/usr/local

# Set work directory
WORKDIR /app

# Install system dependencies
RUN apt-get update -y && \
    apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev && \
    rm -rf /var/lib/apt/lists/*

# Install uv (pinned)
COPY --from=ghcr.io/astral-sh/uv:0.11.8 /uv /uvx /bin/

# Install Python dependencies straight from the lockfile (cached layer).
# --no-install-project: only deps, the Django app is copied in below.
COPY pyproject.toml uv.lock /app/
RUN uv sync --frozen --no-dev --no-install-project

# Copy project
COPY . /app/

RUN mkdir -p /app/logs && \
    mkdir -p /app/static && \
    mkdir -p /app/session && \
    mkdir -p /var/lib/qhf && \
    chmod 777 /app/logs && \
    chmod 777 /app/session && \
    chmod 777 /var/lib/qhf

RUN chmod +x /app/entrypoint.sh


# Run the Django development server
ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "120", "app.config.wsgi:application"]
