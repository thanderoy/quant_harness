from django.apps import AppConfig
import os
import sys
import logging

LOGGER = logging.getLogger(__name__)

class QuantConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'app.quant'

    def ready(self):
        if os.environ.get('START_FOREXERO_ON_START') == 'true':
            # Avoid starting the task from Celery workers or management commands
            # We target the main web server process (Gunicorn)
            executable = sys.argv[0]
            if 'celery' not in executable and 'manage.py' not in executable:
                try:
                    from app.quant.tasks import run_forexero_listener
                    LOGGER.info("Triggering Forexero listener task on startup...")
                    run_forexero_listener.delay()
                except Exception as e:
                    LOGGER.error(f"Failed to auto-start Forexero listener: {e}")
