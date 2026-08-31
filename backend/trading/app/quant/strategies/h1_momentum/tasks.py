import time as _time

from celery import shared_task

from app.config import settings
from app.quant.strategies.h1_momentum.strategy import (
    SHORT_NAME,
    H1MomentumStrategy,
)
from app.quant.strategies.logging_utils import get_strategy_logger

LOGGER = get_strategy_logger(__name__, SHORT_NAME)


@shared_task(
    name="quant.h1_momentum.run",
    bind=True,
    max_retries=0,
    time_limit=180,
    soft_time_limit=150,
)
def run_h1_momentum(self) -> dict:
    """
    Runs every 60 minutes, aligned to H1 candle close (fires at HH:02).

    Fires one minute later than crest_n_keel did because this task pulls 50,000
    bars to reconstruct the entry percentile, which takes a few seconds; the
    extra minute keeps it clear of the hour boundary.

    Manages exits BEFORE considering an entry, so a position reaching its
    12-bar hold frees the slot in the same pass. Catches and logs everything --
    the task must never crash silently.
    """
    start = _time.monotonic()
    LOGGER.info("quant.h1_momentum.run started")
    try:
        strategy = H1MomentumStrategy()
        LOGGER.info(
            "h1_momentum.task_start env=%s mt5_url=%s",
            strategy.environment,
            settings.get_mt5_url(strategy.environment),
        )
        signal = strategy.evaluate()
        duration = round(_time.monotonic() - start, 2)
        LOGGER.info(
            f"quant.h1_momentum.run completed: signal={signal} duration={duration}s"
        )
        return {"signal": signal, "duration": duration}
    except Exception as e:
        duration = round(_time.monotonic() - start, 2)
        LOGGER.exception(f"quant.h1_momentum.run failed after {duration}s: {e}")
        return {"signal": None, "error": str(e), "duration": duration}
