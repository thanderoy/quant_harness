#!/usr/bin/env python3
import os
import asyncio
import logging
import threading

# Ensure Django settings are loaded when running as a standalone script
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "app.config.settings")

import django  # noqa: E402

django.setup()

from app.quant.strategies.fxz_strategy import ForexeroStrategy  # noqa: E402
from app.adapters.telegram import TelegramAPIClient  # noqa: E402


logging.basicConfig(
    level=logging.INFO, format='[FXZ] %(asctime)s %(levelname)s %(message)s')
LOGGER = logging.getLogger("FXZRunner")


def main():
    strategy = ForexeroStrategy()

    # Start Telegram streaming in a background thread
    tg_client: TelegramAPIClient = strategy.TELEGRAM_API_CLIENT
    t = threading.Thread(
        target=tg_client.stream_signals, name="TelegramStream", daemon=True)
    t.start()
    LOGGER.info("Started Telegram stream thread")

    # Run the consumer loop
    try:
        asyncio.run(strategy.enter_trade())
    except KeyboardInterrupt:
        LOGGER.info("Shutting down FXZ runner...")


if __name__ == "__main__":
    main()
