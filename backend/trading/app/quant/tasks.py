import logging
from datetime import datetime

from celery import shared_task

from app.quant.strategies.forexero.tasks import (
    execute_forexero_trade,
    run_forexero_listener,
)
from app.adapters.mt5_api import MT5APIClient
from app.config import settings
from app.trades.models import Trade

LOGGER = logging.getLogger(__name__)

__all__ = [
    "execute_forexero_trade",
    "run_forexero_listener",
    "sync_trades",
]


@shared_task(bind=True, name="app.quant.tasks.sync_trades")
def sync_trades(self):
    """
    Celery task to sync unsynched trades with broker.

    Runs hourly to check all trades where synched=False.
    For each trade, fetches position/order data from broker using broker_id
    and updates: pnl, exit_price, exit_time, exit_reason.
    """
    LOGGER.info("Starting trade sync task...")

    # Get all unsynched trades
    unsynched_trades = Trade.objects.filter(synched=False)
    total_count = unsynched_trades.count()

    if total_count == 0:
        LOGGER.info("No unsynched trades found")
        return {"synched": 0, "failed": 0, "still_open": 0}

    LOGGER.info(f"Found {total_count} unsynched trades to process")

    # Initialize MT5 client
    mt5_client = MT5APIClient(base_url=settings.MT5_API_URL)

    try:
        mt5_client.connect()
    except Exception as e:
        LOGGER.error(f"Failed to connect to MT5: {e}")
        raise self.retry(exc=e, countdown=300)  # Retry in 5 minutes

    synched_count = 0
    failed_count = 0
    still_open_count = 0

    for trade in unsynched_trades:
        try:
            ticket = int(trade.broker_id)

            # First, check if position is still open
            position = mt5_client.get_position(ticket)

            if position is not None:
                # Position is still open - update current PnL but don't mark as synched
                trade.pnl = position.get("profit", 0.0)
                trade.save(update_fields=["pnl"])
                still_open_count += 1
                LOGGER.debug(f"Trade {trade.id}: OPEN, Updated PnL: {trade.pnl}")
                continue

            # Position is closed - get order history
            order = mt5_client.get_order(ticket)

            if not order:
                LOGGER.warning(f"No order found for trade {trade.id} (ticket {ticket})")
                failed_count += 1
                continue

            # Check order state - 4 = FILLED, 2 = CANCELED, 6 = EXPIRED
            order_state = order.get("state", 0)

            if order_state == 4:  # ORDER_STATE_FILLED
                trade.exit_price = order.get("price_current") or order.get("price_open")
                time_done = order.get("time_done")
                if time_done:
                    if isinstance(time_done, str):
                        trade.exit_time = datetime.fromisoformat(time_done.replace("Z", "+00:00"))
                    else:
                        trade.exit_time = time_done

                # Calculate PnL for closed trade
                if trade.exit_price and trade.entry_price and trade.order_volume:
                    price_diff = trade.exit_price - trade.entry_price
                    if trade.direction == "SELL":
                        price_diff = -price_diff  # Reverse for sell orders

                    # For forex/gold, PnL = price_diff * volume * contract_size
                    # Contract size for XAUUSD is typically 100 (1 lot = 100 oz)
                    contract_size = 100  # TODO: make this configurable per symbol
                    trade.pnl = round(price_diff * trade.order_volume * contract_size, 2)

                # Determine exit reason based on exit price vs TP/SL
                if trade.tp and trade.exit_price:
                    if trade.direction == "BUY" and trade.exit_price >= trade.tp:
                        trade.exit_reason = "TP"
                    elif trade.direction == "SELL" and trade.exit_price <= trade.tp:
                        trade.exit_reason = "TP"
                    elif trade.sl and trade.direction == "BUY" and trade.exit_price <= trade.sl:
                        trade.exit_reason = "SL"
                    elif trade.sl and trade.direction == "SELL" and trade.exit_price >= trade.sl:
                        trade.exit_reason = "SL"
                    else:
                        trade.exit_reason = "MANUAL"
                else:
                    trade.exit_reason = "OTHER"

                trade.synched = True
                trade.save(update_fields=[
                    "exit_price", "exit_time", "exit_reason", "pnl", "synched"
                ])
                synched_count += 1
                LOGGER.info(
                    f"Trade {trade.id}: CLOSED, exit_price: {trade.exit_price}, pnl: {trade.pnl}"
                )

            elif order_state in (2, 6):  # CANCELED or EXPIRED
                trade.exit_reason = "OTHER"
                trade.synched = True
                trade.save(update_fields=["exit_reason", "synched"])
                synched_count += 1
                LOGGER.info(f"Trade {trade.id}: {order.get('state_description')}")

            else:
                # Order still pending or other state
                LOGGER.debug(f"Trade {trade.id}: {order.get('state_description')}")
                still_open_count += 1

        except Exception as e:
            LOGGER.exception(f"Error syncing trade {trade.id}: {e}")
            failed_count += 1

    mt5_client.close()

    result = {
        "synched": synched_count,
        "failed": failed_count,
        "still_open": still_open_count,
        "total": total_count,
    }
    LOGGER.info(f"Trade sync completed: {result}")
    return result
