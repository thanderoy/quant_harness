from django.core.management.base import BaseCommand
import logging
from app.quant.forexero_runner import start_forexero_background
import time

LOGGER = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Start Forexero strategy (Telegram stream + MT5 orders) in background threads"

    def handle(self, *args, **options):
        start_forexero_background()
        LOGGER.info("Forexero runner started in background; press Ctrl+C to exit.")
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            LOGGER.info("Stopping run_forexero command...")
