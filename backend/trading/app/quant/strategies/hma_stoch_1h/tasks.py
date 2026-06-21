import logging
import time as _time

from celery import shared_task

from app.config import settings
from app.quant.strategies.hma_stoch_1h.strategy import HMAStoch1HStrategy

LOGGER = logging.getLogger(__name__)


@shared_task(name="quant.hma_stoch_1h.run")
def run_hma_stoch_1h() -> dict:
    """
    Runs every 60 minutes, aligned to H1 candle close (fires at HH:01).
    Catches and logs all exceptions — task must never crash silently.
    """
    start = _time.monotonic()
    LOGGER.info("quant.hma_stoch_1h.run started")
    try:
        strategy = HMAStoch1HStrategy()
        # One-line env-routing audit per fire (guards against demo→prod typos).
        LOGGER.info(
            "crest_n_keel.task_start env=%s mt5_url=%s",
            strategy.environment,
            settings.get_mt5_url(strategy.environment),
        )
        signal = strategy.evaluate()
        duration = round(_time.monotonic() - start, 2)
        LOGGER.info(
            f"quant.hma_stoch_1h.run completed: signal={signal} duration={duration}s"
        )
        return {"signal": signal, "duration": duration}
    except Exception as e:
        duration = round(_time.monotonic() - start, 2)
        LOGGER.exception(f"quant.hma_stoch_1h.run failed after {duration}s: {e}")
        return {"signal": None, "error": str(e), "duration": duration}
