import logging
import time as _time

from celery import shared_task

from app.quant.strategies.hma_stoch_m15.strategy import HMAStochM15Strategy

LOGGER = logging.getLogger(__name__)


@shared_task(name="quant.hma_stoch_m15.run")
def run_hma_stoch_m15() -> dict:
    """
    Runs every 15 minutes, aligned to M15 candle close (fires at HH:01, HH:16, HH:31, HH:46).
    Catches and logs all exceptions — task must never crash silently.
    """
    start = _time.monotonic()
    LOGGER.info("quant.hma_stoch_m15.run started")
    try:
        strategy = HMAStochM15Strategy()
        signal = strategy.evaluate()
        duration = round(_time.monotonic() - start, 2)
        LOGGER.info(f"quant.hma_stoch_m15.run completed: signal={signal} duration={duration}s")
        return {"signal": signal, "duration": duration}
    except Exception as e:
        duration = round(_time.monotonic() - start, 2)
        LOGGER.exception(f"quant.hma_stoch_m15.run failed after {duration}s: {e}")
        return {"signal": None, "error": str(e), "duration": duration}
