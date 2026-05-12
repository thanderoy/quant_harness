import logging
import time as _time

from celery import shared_task

from app.quant.strategies.asqs.strategy import ASQSafeScalpingStrategy

LOGGER = logging.getLogger(__name__)


@shared_task(name="quant.asqs.run")
def run_asqs() -> dict:
    """
    Runs every 5 minutes, aligned to M5 candle close
    (fires at HH:01, HH:06, ..., HH:56).
    Catches and logs all exceptions — task must never crash silently.
    """
    start = _time.monotonic()
    LOGGER.info("quant.asqs.run started")
    try:
        strategy = ASQSafeScalpingStrategy()
        signal = strategy.evaluate()
        duration = round(_time.monotonic() - start, 2)
        LOGGER.info(f"quant.asqs.run completed: signal={signal} duration={duration}s")
        return {"signal": signal, "duration": duration}
    except Exception as e:
        duration = round(_time.monotonic() - start, 2)
        LOGGER.exception(f"quant.asqs.run failed after {duration}s: {e}")
        return {"signal": None, "error": str(e), "duration": duration}
