# backend/django/app/__init__.py

from app.config.celery import app as celery_app

__all__ = ["celery_app"]
