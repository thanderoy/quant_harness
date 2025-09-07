# WARP.md

This file provides guidance to WARP (warp.dev) when working with code in this repository.

Project scope
- Docker-orchestrated stack to run MetaTrader 5 (MT5) under Wine, expose an MT5 HTTP API (Flask), and a Django app that consumes it. Traefik fronts external access. Postgres/Redis backends and a full monitoring stack (Grafana, Prometheus, Loki, Promtail, Alertmanager, cAdvisor, Node Exporter).

Common commands
- Environment setup
  - Copy and edit environment variables:
    ```bash
    cp .env.example .env
    ```
  - Optional: compute a hashed password for Traefik basic auth (store the value into .env as TRAEFIK_HASHED_PASSWORD). Do not echo secrets; compute then paste into .env.
    ```bash
    # Example generation (PASSWORD must be set in your shell prior to this step)
    TRAEFIK_HASHED_PASSWORD=$(openssl passwd -apr1 "$PASSWORD")
    ```
  - Create the shared Traefik network (one-time):
    ```bash
    docker network create traefik-public
    ```
- Boot the full stack
  ```bash
  docker-compose up -d
  ```
- Stop the stack
  ```bash
  docker-compose down
  ```
- Rebuild services after code changes
  - This repo bakes code into images (no bind mounts), so you must rebuild affected services to pick up changes:
    ```bash
    # Rebuild and restart Django only
    docker-compose up -d --build django

    # Rebuild and restart MT5 API only
    docker-compose up -d --build mt5

    # Rebuild multiple services
    docker-compose build django mt5 && docker-compose up -d django mt5
    ```
- Logs and status
  ```bash
  docker-compose ps
  docker-compose logs -f django
  docker-compose logs -f mt5
  docker-compose logs -f celery
  docker-compose logs -f celery-beat
  ```

Django workflows (containerized)
- Migrations
  ```bash
  docker-compose exec django python manage.py makemigrations
  docker-compose exec django python manage.py migrate
  ```
- Admin user (example)
  ```bash
  docker-compose exec django python manage.py createsuperuser
  ```
- Shell
  ```bash
  # django-extensions is enabled; shell_plus is available
  docker-compose exec django python manage.py shell_plus
  ```
- Management command (quant algorithms)
  ```bash
  docker-compose exec django python manage.py run_algorithms
  ```
- Tests
  ```bash
  # All tests (Django test runner)
  docker-compose exec django python manage.py test

  # Single module
  docker-compose exec django python manage.py test app.quant.tests

  # Single test case or method (pattern)
  docker-compose exec django python manage.py test app.quant.tests:YourTestCase
  docker-compose exec django python manage.py test app.quant.tests:YourTestCase.test_method
  ```

MT5 API service checks
- Health check from inside the mt5 container
  ```bash
  docker-compose exec mt5 curl -s http://localhost:5001/health
  ```
- Django talks to MT5 via MT5_API_URL (set in .env). Default internal URL in this stack is http://mt5:5001.

Monitoring quick access (when running locally with published ports)
- Grafana: http://localhost:3000
- Prometheus: http://localhost:9090
- Alertmanager: http://localhost:9093
- Uncomplicated Alert Receiver: http://localhost:9094
- Loki: http://localhost:3100

Architecture and flow
- Edge and routing (Traefik)
  - Traefik runs on ports 80/443, terminates TLS (Let’s Encrypt), and routes by host rules using environment-configured domains.
  - Key domains (from .env):
    - TRAEFIK_DOMAIN: Traefik dashboard (basic auth via TRAEFIK_USERNAME/TRAEFIK_HASHED_PASSWORD).
    - VNC_DOMAIN: VNC web UI for MT5 (routes to mt5:3000).
    - API_DOMAIN: MT5 HTTP API (routes to mt5:5001).
    - DJANGO_DOMAIN: Django app (routes to django:8000).
- MT5 service (backend/mt5)
  - Image: debian-based KasmVNC base; installs Wine (WINEARCH=win64), prepares /config/.wine, installs Python deps.
  - App: Flask app (backend/mt5/app/app.py) with blueprints under routes/ (data, order, position, symbol, history, health, error). Swagger docs enabled.
  - Exposes ports 3000 (VNC), 5001 (API). Traefik proxies external access via VNC_DOMAIN and API_DOMAIN.
- Django service (backend/django)
  - Project: app/ with two core apps
    - app.nexus: domain/admin/serializers/filters
    - app.quant: algorithms (mean_reversion, trailing, close), Celery tasks, management command run_algorithms
  - Integration with MT5 API via app/utils/api/*.py (e.g., data.py, order.py). BASE_URL comes from MT5_API_URL.
  - DB: Postgres via env (POSTGRES_*). Static served via WhiteNoise; collectstatic executed at build time.
  - REST stack: Django REST Framework, django-filter, CORS enabled (CORS_ALLOW_ALL_ORIGINS=True).
- Asynchronous processing (Celery)
  - Separate containers: celery (worker) and celery-beat (scheduler), both built from the Django image.
  - Broker/Result backend: Redis (redis://redis:6379/0) by default.
  - Periodic tasks (from settings.py):
    - quant.tasks.run_quant_entry_algorithm: every 60s
    - quant.tasks.run_quant_trailing_stop_algorithm: every 15s
    - quant.tasks.run_quant_close_algorithm: every 15s
- State and storage
  - Postgres volume: postgres-data
  - Django static files: static_volume
  - Traefik certificates: traefik-public-certificates
  - Grafana/Prometheus data volumes as defined in docker-compose.yml

Environment variables (selected)
- From .env.example:
  - MT5/Traefik: CUSTOM_USER, PASSWORD, VNC_DOMAIN, API_DOMAIN, TRAEFIK_DOMAIN, TRAEFIK_USERNAME, ACME_EMAIL, MT5_API_PORT
  - Monitoring: GRAFANA_DOMAIN
  - Django: MT5_API_URL, DJANGO_DOMAIN
  - Database: POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD
  - Celery: CELERY_BROKER_URL, CELERY_RESULT_BACKEND

Notes for working inside this repo
- Prefer docker-compose exec for any app commands; do not run manage.py on the host.
- Because application code is copied into images, rebuilding is required to pick up Python code changes.
- Traefik requires DNS hostnames to resolve to your machine for external access; for purely local testing without DNS, interact via container networking or published localhost ports (see monitoring services).
- No Python linter or pytest configuration is present in this repo as of now; tests use Django’s built-in runner.

