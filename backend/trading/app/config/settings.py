from pathlib import Path
import os  # Added for environment variables
from dotenv import load_dotenv  # Optional: If using a .env file
from celery.schedules import crontab

# Load environment variables from .env file if present
load_dotenv()

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# External services / integrations (centralized)
MT5_API_URL = os.getenv("MT5_API_URL", "http://mt5:5001")
MT5_TEST_API_URL = os.getenv("MT5_TEST_API_URL", "http://mt5-test:5001")
REQUEST_TIMEOUT = float(os.getenv("REQUEST_TIMEOUT", "10"))

# MT5 environment routing: maps environment name -> MT5 API URL
MT5_ENVIRONMENTS = {
    "prod": MT5_API_URL,
    "test": MT5_TEST_API_URL,
}


def get_mt5_url(environment: str) -> str:
    """Resolve MT5 API URL from environment name."""
    url = MT5_ENVIRONMENTS.get(environment.lower())
    if not url:
        raise ValueError(
            f"Unknown MT5 environment: '{environment}'. "
            f"Valid: {list(MT5_ENVIRONMENTS.keys())}"
        )
    return url


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/4.2/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY")

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.getenv("DJANGO_DEBUG", "False").lower() == "true"

DJANGO_SERVICE_DOMAIN = os.getenv("DJANGO_SERVICE_DOMAIN")
ALLOWED_HOSTS = list(
    filter(
        None,
        [
            os.getenv("HOST_IP"),
            "localhost",
            "127.0.0.1",
            DJANGO_SERVICE_DOMAIN,
        ],
    )
)

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# CSRF trusted origins must include scheme://host
CSRF_TRUSTED_ORIGINS = []
if DJANGO_SERVICE_DOMAIN:
    CSRF_TRUSTED_ORIGINS.extend(
        [
            f"https://{DJANGO_SERVICE_DOMAIN}",
            f"http://{DJANGO_SERVICE_DOMAIN}",
        ]
    )
# Common local dev origins
CSRF_TRUSTED_ORIGINS.extend(
    [
        "http://localhost",
        "http://127.0.0.1",
        "https://localhost",
        "https://127.0.0.1",
    ]
)

CSRF_COOKIE_SECURE = True
CSRF_COOKIE_DOMAIN = DJANGO_SERVICE_DOMAIN
SESSION_COOKIE_SECURE = True

LOGGING = {
    "version": 1,
    "formatters": {
        "verbose": {
            "format": "[TRADING] {levelname} {asctime} {module} {name}:{lineno} {message}",  # noqa: E501
            "style": "{",
        },
        "simple": {
            "format": "{levelname} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "level": "DEBUG",
            "formatter": "verbose",
        },
    },
    "loggers": {
        "quant": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": True,
        },
        "celery": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": True,
        },
        "gunicorn": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
    },
}

# Application definition
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework.authtoken",
    "django_filters",
    "corsheaders",
    "celery",
    "django_extensions",
    "app.trades",
    "app.quant",
]

REST_FRAMEWORK = {
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",  # noqa: E501
    "PAGE_SIZE": 50,
}

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOWED_ORIGINS = list(
    filter(
        None,
        [
            f"https://{DJANGO_SERVICE_DOMAIN}" if DJANGO_SERVICE_DOMAIN else None,
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ],
    )
)

STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

ROOT_URLCONF = "app.config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [os.path.join(BASE_DIR, "templates")],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "app.config.wsgi.application"


# Database
# https://docs.djangoproject.com/en/4.2/ref/settings/#databases

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("POSTGRES_DB"),
        "USER": os.getenv("POSTGRES_USER"),
        "PASSWORD": os.getenv("POSTGRES_PASSWORD"),
        "HOST": os.getenv("POSTGRES_HOST", "postgres"),
        "PORT": os.getenv("POSTGRES_PORT", "5432"),
    }
}


# Password validation
# https://docs.djangoproject.com/en/4.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",  # noqa: E501
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",  # noqa: E501
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",  # noqa: E501
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",  # noqa: E501
    },
]


# Internationalization
# https://docs.djangoproject.com/en/4.2/topics/i18n/

LANGUAGE_CODE = "en-us"

TIME_ZONE = "Africa/Nairobi"

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/4.2/howto/static-files/

STATIC_URL = "/static/"
STATIC_ROOT = os.path.join(BASE_DIR, "staticfiles")
STATICFILES_DIRS = [
    os.path.join(BASE_DIR, "static"),
]

# Default primary key field type
# https://docs.djangoproject.com/en/4.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

CELERY_BROKER_CONNECTION_RETRY = True
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://redis:6379/0")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://redis:6379/0")
CELERY_BEAT_SCHEDULE = {
    "sync-trades-hourly": {
        "task": "app.quant.tasks.sync_trades",
        "schedule": crontab(minute=0, day_of_week="mon-fri"),
    },
    "sync-account-daily": {
        "task": "app.quant.tasks.sync_account_status",
        "schedule": crontab(minute=0, hour=0, day_of_week="mon-fri"),
    },
    # crest_n_keel and asqs are RETIRED from the schedule. Both ran on demo
    # for months on evidence that has since been refuted, and leaving them
    # scheduled contaminates the read on anything deployed alongside them.
    #
    #   crest_n_keel (magic 1100001) — research log seq=49: the nested
    #     walk-forward showed training rank carries no out-of-sample
    #     information (selected beat the gate-passing pool in 17/32 folds,
    #     p=0.430); the full-history leader's apparent edge was 0.68-0.81
    #     Sharpe of pure lookahead. The deployed PULLBACK variant is
    #     separately confirmed edgeless (seq=45).
    #   asqs (magic 1500020) — research log seq=30: harness walk-forward
    #     returned OOS Sharpe ~-1 and net-losing, refuting the seeded
    #     5.14 Sharpe / 1.55 profit factor the strategy was deployed on.
    #     seq=51 adds DSR 0.038 at grid N.
    #
    # Verified flat before removal: 0 open XAUUSD positions on demo for both
    # magic numbers, so nothing was orphaned. Note that asqs.evaluate() also
    # drives manage_positions() (breakeven, trailing, partial close), so this
    # entry must NOT be removed while an asqs position is open.
    #
    # The strategy code and tasks are retained; only the schedule is removed.
    # Re-enabling requires new out-of-sample evidence, not just a re-run.
}

# Telegram API Credentials
TELEGRAM_API_ID = os.getenv("TELEGRAM_API_ID")
TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH")
TELEGRAM_API_TARGET_CHANNEL = os.getenv("TELEGRAM_API_TARGET_CHANNEL")
TELEGRAM_API_RESULTS_CHANNEL = os.getenv("TELEGRAM_API_RESULTS_CHANNEL")
