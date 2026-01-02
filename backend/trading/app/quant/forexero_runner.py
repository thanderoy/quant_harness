import threading
import asyncio
import logging
from typing import Optional

from app.quant.strategies.fxz_strategy import ForexeroStrategy

LOGGER = logging.getLogger(__name__)

_started = False


def start_forexero_background(mt5_base_url: Optional[str] = None) -> None:
    global _started
    if _started:
        LOGGER.info("Forexero runner already started; skipping duplicate start")
        return

    _started = True

    def _run_loop():
        # Create a new event loop for this thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        strategy = ForexeroStrategy(mt5_base_url=mt5_base_url)
        tg_client = strategy.TELEGRAM_API_CLIENT

        async def main():
            # Wait for queue initialization if needed (though get_queue() handles it)
            # but we want to ensure everything is ready.
            # get_queue is async, so we can await it here to ensure it's bound to THIS loop.
            await tg_client.get_queue()

            await asyncio.gather(
                tg_client.stream_signals(),
                strategy.enter_trade(),
            )

        try:
            loop.run_until_complete(main())
        except Exception as e:
            LOGGER.exception(f"[FXZ] Async loop crashed: {e}")
        finally:
            loop.close()

    t = threading.Thread(
        target=_run_loop,
        name="ForexeroAsyncLoop",
        daemon=True,
    )
    t.start()
    LOGGER.info("[FXZ] Forexero background thread started")
