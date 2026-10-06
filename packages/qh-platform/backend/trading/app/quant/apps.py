from django.apps import AppConfig
import logging

LOGGER = logging.getLogger(__name__)


class QuantConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "app.quant"
