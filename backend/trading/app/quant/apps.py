from django.apps import AppConfig
from django.conf import settings
import logging
import os

LOGGER = logging.getLogger(__name__)


class QuantConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'app.quant'

    def ready(self):
        # Autostart Forexero on app startup; can be disabled via env var
        should_start = os.getenv('START_FOREXERO_ON_START', 'true').lower() in ('1', 'true', 'yes')
        if not should_start:
            return
        try:
            from app.quant.forexero_runner import start_forexero_background
            start_forexero_background(mt5_base_url=settings.MT5_API_URL)
            LOGGER.info("Forexero auto-start kicked off from AppConfig.ready()")
        except Exception:
            LOGGER.exception("Failed to auto-start Forexero strategy")
