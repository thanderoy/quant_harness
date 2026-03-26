#!/usr/bin/env bash
set -euo pipefail

# ---------------------------------------------------------------
# Superset bootstrap script
# Creates the metadata DB, runs migrations, creates admin, starts.
# ---------------------------------------------------------------

echo "==> Waiting for Postgres to be ready..."
PG_HOST="${POSTGRES_HOST:-postgres}"
PG_PORT="${POSTGRES_PORT:-5432}"
until python -c "
import socket, sys
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(3)
try:
    s.connect(('${PG_HOST}', ${PG_PORT}))
    s.close()
except Exception:
    sys.exit(1)
" 2>/dev/null; do
  echo "    Postgres not ready yet – retrying in 2s..."
  sleep 2
done
echo "==> Postgres is ready!"

echo "==> Installing psycopg2-binary (PostgreSQL driver)..."
pip install psycopg2-binary --quiet

echo "==> Ensuring 'superset' database exists..."
python -c "
import psycopg2, os
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
conn = psycopg2.connect(
    host=os.environ.get('POSTGRES_HOST', 'postgres'),
    port=int(os.environ.get('POSTGRES_PORT', '5432')),
    user=os.environ['POSTGRES_USER'],
    password=os.environ['POSTGRES_PASSWORD'],
    dbname=os.environ.get('POSTGRES_DB', 'postgres'),
)
conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
cur = conn.cursor()
cur.execute(\"SELECT 1 FROM pg_database WHERE datname = 'superset'\")
if not cur.fetchone():
    cur.execute('CREATE DATABASE superset')
    print('    Created database: superset')
else:
    print('    Database superset already exists')
cur.close()
conn.close()
"

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
