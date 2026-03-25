import os

# -------------------------------------------------------------------
# Superset configuration
# https://superset.apache.org/docs/configuration/configuring-superset
# -------------------------------------------------------------------

SECRET_KEY = os.environ.get("SUPERSET_SECRET_KEY", "")

# Metadata database — shares the postgres service, separate DB
SQLALCHEMY_DATABASE_URI = (
    f"postgresql+psycopg2://"
    f"{os.environ['POSTGRES_USER']}:{os.environ['POSTGRES_PASSWORD']}"
    f"@{os.environ.get('POSTGRES_HOST', 'postgres')}:"
    f"{os.environ.get('POSTGRES_PORT', '5432')}/superset"
)

# Redis for caching & Celery results
REDIS_HOST = os.environ.get("REDIS_HOST", "redis")
REDIS_PORT = os.environ.get("REDIS_PORT", "6379")
REDIS_CELERY_DB = os.environ.get("REDIS_CELERY_DB", "4")
REDIS_RESULTS_DB = os.environ.get("REDIS_RESULTS_DB", "5")

CACHE_CONFIG = {
    "CACHE_TYPE": "RedisCache",
    "CACHE_DEFAULT_TIMEOUT": 300,
    "CACHE_KEY_PREFIX": "superset_",
    "CACHE_REDIS_HOST": REDIS_HOST,
    "CACHE_REDIS_PORT": REDIS_PORT,
    "CACHE_REDIS_DB": REDIS_RESULTS_DB,
}

DATA_CACHE_CONFIG = CACHE_CONFIG

# Celery (async queries, reports, thumbnails)
class CeleryConfig:
    broker_url = f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_CELERY_DB}"
    imports = ("superset.sql_lab",)
    result_backend = f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_RESULTS_DB}"
    worker_prefetch_multiplier = 10
    task_acks_late = True

CELERY_CONFIG = CeleryConfig

# Feature flags
FEATURE_FLAGS = {
    "ENABLE_TEMPLATE_PROCESSING": True,
}

# Allow embedding in iframes (if needed behind reverse proxy)
HTTP_HEADERS = {"X-Frame-Options": "ALLOWALL"}

# Webserver
ENABLE_PROXY_FIX = True
SUPERSET_WEBSERVER_PORT = 8088
