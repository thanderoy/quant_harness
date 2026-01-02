#!/usr/bin/env python3
import os
import asyncio
import logging

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
    tg_client: TelegramAPIClient = strategy.TELEGRAM_API_CLIENT

    async def async_main():
        # Ensure queue is created on this loop
        await tg_client.get_queue()

        LOGGER.info("Starting Telegram stream and Strategy consumer...")
        await asyncio.gather(
            tg_client.stream_signals(),
            strategy.enter_trade()
        )

    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        LOGGER.info("Shutting down FXZ runner...")


if __name__ == "__main__":
    main()
