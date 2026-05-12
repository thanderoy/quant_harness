"""
Celery tasks for London Breakout strategy.
"""

import logging
from celery import shared_task

from app.quant.strategies.london_breakout.strategy import LondonBreakoutStrategy

LOGGER = logging.getLogger(__name__)


@shared_task(
    bind=True, name="app.quant.strategies.london_breakout.tasks.run_london_breakout"
)
def run_london_breakout(
    self,
    symbol: str = "XAUUSD",
    volume: float = 0.01,
    ema_period: int = 200,
    atr_period: int = 14,
    min_breakout_pips: float = 2.0,
    risk_reward_ratio: float = 3.0,
    environment: str = "prod",
):
    """
    Celery task to run London Breakout strategy.

    Should be scheduled to run every 15 minutes via Celery Beat.

    Example Celery Beat schedule in settings:

        CELERY_BEAT_SCHEDULE = {
            'london-breakout-every-15-min': {
                'task': 'app.quant.strategies.london_breakout.tasks.run_london_breakout',
                'schedule': crontab(minute='*/15'),
                'kwargs': {'symbol': 'XAUUSD', 'volume': 0.01},
            },
        }
    """
    try:
        LOGGER.info(f"Running London Breakout: symbol={symbol}, volume={volume}")

        strategy = LondonBreakoutStrategy(
            environment=environment,
            symbol=symbol,
            volume_per_order=volume,
            ema_period=ema_period,
            atr_period=atr_period,
            min_breakout_pips=min_breakout_pips,
            risk_reward_ratio=risk_reward_ratio,
        )
        strategy.run()

        return {
            "status": "success",
            "symbol": symbol,
            "range_high": strategy.range_high,
            "range_low": strategy.range_low,
            "trade_taken": strategy.daily_trade_taken,
        }

    except Exception as e:
        LOGGER.exception(f"London Breakout task error: {e}")
        raise self.retry(exc=e, countdown=60, max_retries=3)
