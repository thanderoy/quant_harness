#!/usr/bin/env bash
set -euo pipefail

# ---------------------------------------------------------------
# Superset bootstrap script
# Creates the metadata DB, runs migrations, creates admin, starts.
# ---------------------------------------------------------------

echo "==> Waiting for Postgres to be ready..."
until PGPASSWORD="${POSTGRES_PASSWORD}" psql \
    -h "${POSTGRES_HOST:-postgres}" \
    -p "${POSTGRES_PORT:-5432}" \
    -U "${POSTGRES_USER}" \
    -d "${POSTGRES_DB:-postgres}" \
    -c '\q' 2>/dev/null; do
  sleep 2
done
echo "==> Postgres is ready!"

echo "==> Installing psycopg2-binary (PostgreSQL driver)..."
python -m pip install psycopg2-binary --quiet

echo "==> Ensuring 'superset' database exists..."
PGPASSWORD="${POSTGRES_PASSWORD}" psql \
    -h "${POSTGRES_HOST:-postgres}" \
    -p "${POSTGRES_PORT:-5432}" \
    -U "${POSTGRES_USER}" \
    -d "${POSTGRES_DB:-postgres}" \
    -tc "SELECT 1 FROM pg_database WHERE datname = 'superset'" \
  | grep -q 1 \
  || PGPASSWORD="${POSTGRES_PASSWORD}" createdb \
    -h "${POSTGRES_HOST:-postgres}" \
    -p "${POSTGRES_PORT:-5432}" \
    -U "${POSTGRES_USER}" \
    superset

echo "==> Running Superset DB upgrade (migrations)..."
superset db upgrade

echo "==> Initialising Superset (roles, permissions)..."
superset init

echo "==> Creating admin user (if not exists)..."
superset fab create-admin \
    --username "${SUPERSET_ADMIN_USER:-admin}" \
    --firstname "Admin" \
    --lastname "User" \
    --email "${SUPERSET_ADMIN_EMAIL:-admin@superset.local}" \
    --password "${SUPERSET_ADMIN_PASSWORD:-admin}" \
  || true   # ignore error if user already exists

echo "==> Starting Superset server on port 8088..."
exec gunicorn \
    --bind "0.0.0.0:8088" \
    --workers 2 \
    --timeout 120 \
    --limit-request-line 0 \
    --limit-request-field_size 0 \
    "superset.app:create_app()"
