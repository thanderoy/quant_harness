# backend/trading/app/celery.py

from __future__ import absolute_import, unicode_literals
import os
from celery import Celery

# Set the default Django settings module
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "app.config.settings")

app = Celery("app")

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
app.config_from_object("django.conf:settings", namespace="CELERY")

# Load task modules from all registered Django app configs.
app.autodiscover_tasks()

# Explicitly include strategy task modules (not at app root, not auto-discovered).
app.conf.include = [
    "app.quant.strategies.h1_momentum.tasks",
    "app.quant.strategies.crest_n_keel.tasks",
    "app.quant.strategies.asqs.tasks",
]

# Optional: Set a rate limit if necessary
# app.conf.worker_prefetch_multiplier = 1
