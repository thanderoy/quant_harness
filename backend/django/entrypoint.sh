#!/usr/bin/env sh
set -e

# Run Django setup tasks at container startup
# Assumes the database is healthy (Compose waits for Postgres healthcheck)

# Collect static files into STATIC_ROOT
python manage.py collectstatic --noinput

# Apply database migrations
python manage.py migrate --noinput

# Optionally create a superuser if credentials are provided
if [ -n "${DJANGO_SUPERUSER_USERNAME:-}" ] && [ -n "${DJANGO_SUPERUSER_PASSWORD:-}" ]; then
python - <<'PY'
import os
import sys
import django

try:
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'app.settings')
    django.setup()
    from django.contrib.auth import get_user_model
    User = get_user_model()
    username = os.environ['DJANGO_SUPERUSER_USERNAME']
    email = os.environ.get('DJANGO_SUPERUSER_EMAIL', '')
    password = os.environ['DJANGO_SUPERUSER_PASSWORD']
    if not User.objects.filter(username=username).exists():
        User.objects.create_superuser(username=username, email=email, password=password)
        print(f"Created superuser: {username}")
    else:
        print(f"Superuser already exists: {username}")
except Exception as e:
    print(f"Error creating superuser: {e}", file=sys.stderr)
    sys.exit(1)
PY
fi

# Exec the main process (Gunicorn command provided via CMD)
exec "$@"
