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
# --group test: bundle pytest tooling so `docker compose exec trading pytest -n 2`
#   works without ad-hoc installs. The env is dev/test/demo and there is no
#   separate prod image today, so the few MB of test tooling is acceptable.
#   Stricter prod/test image separation (multi-stage) is a deliberate follow-up.
# Paths below are relative to the REPOSITORY ROOT, not to this directory.
# Phase 3 step 3a widened the build context so the image can install
# packages/qh-resources, which lives outside backend/trading. See
# docs/phase3_spec.md section 3a and the repo-root .dockerignore.
COPY packages/qh-platform/backend/trading/pyproject.toml \
     packages/qh-platform/backend/trading/uv.lock /app/
RUN uv sync --frozen --no-dev --group test --no-install-project

# The instrument-neutral core, installed with --no-deps on purpose. This app
# already pins numpy==1.26.4 and pandas==2.2.1, which satisfy qh-resources'
# requirements (numpy>=1.24, pandas>=2.0), so installing without deps adds the
# `resources` package while leaving the locked dependency set untouched and
# `uv sync --frozen` still valid. Resolving them again here would let the
# platform's pins drift from the lockfile that was verified against them.
# --system because UV_PROJECT_ENVIRONMENT (set above) steers `uv sync` but not
# `uv pip install`, which looks for an active virtualenv and fails without it.
COPY packages/qh-resources /opt/qh-resources
RUN uv pip install --system --no-deps /opt/qh-resources

# Copy project
COPY packages/qh-platform/backend/trading/ /app/

RUN mkdir -p /app/logs && \
    mkdir -p /app/static && \
    mkdir -p /app/session && \
    mkdir -p /var/lib/quant_harness && \
    chmod 777 /app/logs && \
    chmod 777 /app/session && \
    chmod 777 /var/lib/quant_harness

RUN chmod +x /app/entrypoint.sh


# Run the Django development server
ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "120", "app.config.wsgi:application"]
