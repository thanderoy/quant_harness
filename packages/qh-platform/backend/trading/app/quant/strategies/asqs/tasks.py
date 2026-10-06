import time as _time
from datetime import datetime, timedelta, timezone

from celery import shared_task

from app.quant.strategies.asqs.strategy import SHORT_NAME, ASQSafeScalpingStrategy
from app.quant.strategies.logging_utils import get_strategy_logger

LOGGER = get_strategy_logger(__name__, SHORT_NAME)

# Informational threshold only. Hard staleness gating is done by the beat
# schedule's `expires` option, which discards the task before it runs if it
# has not been picked up in time. This value just flags a late pickup in logs.
LATE_PICKUP_WARN_S = 240


def _evaluated_bar_open(now: datetime) -> datetime:
    """
    Open time of the M5 bar that iloc[-2] references when the task fires.

    M5 bars open at :00, :05, :10, ... The task fires ~1 min after a bar
    close (:01, :06, ...). At fire time the most recent boundary is the open
    of the still-forming bar (iloc[-1]); the bar we evaluate (iloc[-2]) opened
    one M5 period earlier.
    """
    boundary_minute = (now.minute // 5) * 5
    boundary = now.replace(minute=boundary_minute, second=0, microsecond=0)
    return boundary - timedelta(minutes=5)


@shared_task(
    name="quant.asqs.run",
    bind=True,
    max_retries=0,
    time_limit=120,
    soft_time_limit=90,
)
def run_asqs(self) -> dict:
    """
    Runs every 5 minutes, aligned to M5 candle close
    (fires at HH:01, HH:06, ..., HH:56).

    Logs full timing context for post-hoc signal auditing. Staleness is
    enforced by the beat `expires` option, not in here. Catches and logs all
    exceptions — task must never crash silently.
    """
    start = _time.monotonic()
    now = datetime.now(timezone.utc)

    evaluated_bar = _evaluated_bar_open(now)
    delay_s = (now - (evaluated_bar + timedelta(minutes=5))).total_seconds()

    LOGGER.info(
        f"Task fired at {now.isoformat()} | "
        f"Evaluating bar (open): {evaluated_bar.strftime('%H:%M')} | "
        f"Pickup delay: {delay_s:.1f}s"
    )
    if delay_s > LATE_PICKUP_WARN_S:
        LOGGER.warning(
            f"Late pickup: {delay_s:.0f}s after bar close "
            f"(warn threshold {LATE_PICKUP_WARN_S}s). Check Celery queue "
            f"backlog or worker health."
        )

    try:
        strategy = ASQSafeScalpingStrategy()
        signal = strategy.evaluate()
        duration = round(_time.monotonic() - start, 2)
        LOGGER.info(
            f"{'SIGNAL ' + signal if signal else 'No signal'} | "
            f"Bar: {evaluated_bar.strftime('%H:%M')} | duration={duration}s"
        )
        return {
            "status": "OK",
            "signal": signal,
            "evaluated_bar": evaluated_bar.strftime("%Y-%m-%d %H:%M"),
            "fired_at": now.isoformat(),
            "delay_s": round(delay_s, 1),
            "duration_s": duration,
        }
    except Exception as e:
        duration = round(_time.monotonic() - start, 2)
        LOGGER.exception(f"Task failed after {duration}s: {e}")
        return {
            "status": "ERROR",
            "signal": None,
            "error": str(e),
            "fired_at": now.isoformat(),
            "duration_s": duration,
        }


@shared_task(
    name="quant.asqs.audit",
    bind=True,
    max_retries=0,
    time_limit=300,
)
def run_asqs_audit(self) -> dict:
    """
    Daily audit task — runs once after session close.

    Replays the day's M5 bars to count how many signals the strategy would
    have generated, compares against trades actually executed, and logs the
    gap for Grafana/Loki dashboards.
    """
    LOGGER.info("AUDIT: Starting daily signal audit")

    try:
        import pandas as pd
        from django.utils import timezone as dj_tz

        from app.trades.models import Trade

        strategy = ASQSafeScalpingStrategy()
        data = strategy.mt5_client.get_market_rates("XAUUSD", "M5", count=300)
        if not data or "rates" not in data:
            LOGGER.warning("AUDIT: Could not fetch candle data")
            return {"status": "NO_DATA"}

        df = pd.DataFrame(data["rates"])
        if not pd.api.types.is_datetime64_any_dtype(df["time"]):
            df["time"] = pd.to_datetime(df["time"])

        signal_count = 0
        for i in range(strategy.ema_slow_period + 25, len(df) - 1):
            window = df.iloc[: i + 2]
            sig, _ = strategy._generate_signal(window)
            if sig is not None:
                signal_count += 1

        today = dj_tz.now().date()
        executed = Trade.objects.filter(
            strategy="ASQSafeScalpingStrategy",
            entry_time__date=today,
        ).count()

        result = {
            "status": "OK",
            "date": str(today),
            "chart_signals": signal_count,
            "executed_trades": executed,
            "missed": max(0, signal_count - executed),
        }

        if signal_count > 0 and executed == 0:
            LOGGER.warning(
                f"AUDIT: {signal_count} chart signals existed today "
                f"but 0 were executed — check filters, H1 confirmation, "
                f"or Celery task health"
            )
        else:
            LOGGER.info(f"AUDIT: {result}")

        return result

    except Exception as exc:
        LOGGER.exception(f"AUDIT: Failed: {exc}")
        return {"status": "ERROR", "error": str(exc)}
