import os
import threading
import asyncio
import logging
from typing import Optional

from app.quant.strategies.fxz_strategy import ForexeroStrategy
from app.adapters.telegram import TelegramAPIClient

LOGGER = logging.getLogger(__name__)

_started = False


def start_forexero_background(mt5_base_url: Optional[str] = None) -> None:
    global _started
    if _started:
        LOGGER.info("Forexero runner already started; skipping duplicate start")
        return

    _started = True

    strategy = ForexeroStrategy(mt5_base_url=mt5_base_url)

    # Start Telegram streaming in a background thread
    tg_client: TelegramAPIClient = strategy.TELEGRAM_API_CLIENT
    t_stream = threading.Thread(
        target=tg_client.stream_signals,
        name="TelegramStream",
        daemon=True,
    )
    t_stream.start()
    LOGGER.info("[FXZ] Telegram stream thread started")

    # Run the consumer loop in another background thread
    def _consumer_loop():
        try:
            asyncio.run(strategy.enter_trade())
        except Exception as e:
            LOGGER.exception(f"[FXZ] Consumer loop crashed: {e}")

    t_consumer = threading.Thread(
        target=_consumer_loop,
        name="ForexeroConsumer",
        daemon=True,
    )
    t_consumer.start()
    LOGGER.info("[FXZ] Forexero consumer thread started")
