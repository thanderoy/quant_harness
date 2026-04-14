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
from app.trades.utils import calculate_realized_profit

LOGGER = logging.getLogger(__name__)

__all__ = [
    "execute_forexero_trade",
    "run_forexero_listener",
    "sync_trades",
    "sync_account_status",
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
    rejected_count = 0

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

            # Check order state - 4 = FILLED, 2 = CANCELED, 6 = EXPIRED, 5 = REJECTED
            order_state = order.get("state", 0)

            if order_state == 4:  # ORDER_STATE_FILLED
                # Get deals to calculate actual PnL
                deals = mt5_client.get_deals(ticket)  # ticket is position ID in this context

                if not deals:
                    LOGGER.warning(f"No deals found for filled trade {trade.id} (position {ticket})")
                    failed_count += 1
                    continue

                # Sum up PnL, commission, swap, and fee from all deals
                total_pnl = 0.0
                total_commission = 0.0
                total_swap = 0.0
                total_fee = 0.0
                exit_price = 0.0
                exit_time = None
                entry_price_actual = trade.entry_price or 0.0

                # In deals represent entries.
                in_deals = [d for d in deals if d.get("entry") in (0, 2)]  # 0=IN, 2=INOUT
                if in_deals:
                    # Use the first in deal for entry price
                    first_in_deal = sorted(in_deals, key=lambda x: x.get("time_msc", 0))[0]
                    entry_price_actual = first_in_deal.get("price", 0.0)

                # Out deals represent closures.
                out_deals = [d for d in deals if d.get("entry") in (1, 3)] # 1=OUT, 3=OUT_BY

                if out_deals:
                    # Use the last out deal for exit time/price
                    last_out_deal = sorted(out_deals, key=lambda x: x.get("time_msc", 0))[-1]
                    exit_price = last_out_deal.get("price", 0.0)

                    time_raw = last_out_deal.get("time")
                    if time_raw:
                        if isinstance(time_raw, str):
                            exit_time = datetime.fromisoformat(time_raw.replace("Z", "+00:00"))
                        else:
                            exit_time = time_raw

                for deal in deals:
                    total_pnl += deal.get("profit", 0.0)
                    total_commission += deal.get("commission", 0.0)
                    total_swap += deal.get("swap", 0.0)
                    total_fee += deal.get("fee", 0.0)

                if entry_price_actual:
                    trade.entry_price = entry_price_actual
                trade.exit_price = exit_price
                trade.exit_time = exit_time

                # Net PnL is profit + commission + swap + fee
                trade.pnl = round(total_pnl + total_commission + total_swap + total_fee, 2)

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
                trade.status = "FILLED"
                trade.save(update_fields=[
                    "entry_price", "exit_price", "exit_time", "exit_reason",
                    "pnl", "status", "synched",
                ])
                synched_count += 1
                LOGGER.info(
                    f"Trade {trade.id}: CLOSED, exit_price: {trade.exit_price}, pnl: {trade.pnl}"
                )

            elif order_state in (2, 5, 6):  # CANCELED, REJECTED or EXPIRED
                # Map MT5 order state to our status
                state_to_status = {2: "CANCELED", 5: "REJECTED", 6: "EXPIRED"}
                state_to_reason = {2: "CANCELED", 5: "REJECTED", 6: "EXPIRED"}

                trade.status = state_to_status.get(order_state, "REJECTED")
                trade.exit_reason = state_to_reason.get(order_state, "OTHER")
                trade.pnl = 0.0
                trade.synched = True
                trade.save(update_fields=["status", "exit_reason", "pnl", "synched"])
                rejected_count += 1
                LOGGER.info(
                    f"Trade {trade.id}: {trade.status} - "
                    f"{order.get('comment', '')} "
                    f"(state: {order.get('state_description', order_state)})"
                )

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
        "rejected": rejected_count,
        "total": total_count,
    }
    LOGGER.info(f"Trade sync completed: {result}")
    return result


@shared_task(bind=True, name="app.quant.tasks.sync_account_status")
def sync_account_status(self):
    """
    Celery task to sync the MT5 account status and take a daily snapshot.
    """
    LOGGER.info("Starting account sync task...")
    from app.trades.models import Account, AccountSnapshot
    from django.utils import timezone

    mt5_client = MT5APIClient(base_url=settings.MT5_API_URL)

    try:
        mt5_client.connect()
        account_info = dict(mt5_client.get_account_info())
    except Exception as e:
        LOGGER.error(f"Failed to connect or get account info from MT5: {e}")
        mt5_client.close()
        raise self.retry(exc=e, countdown=300)

    try:
        login = account_info.get("login")
        if not login:
            LOGGER.error("Account info returned no login, aborting sync.")
            return {"error": "no login"}

        # Update or create the immutable Account
        account, created = Account.objects.update_or_create(
            login=login,
            defaults={
                "name": account_info.get("name", ""),
                "server": account_info.get("server", ""),
                "currency": account_info.get("currency", ""),
                "trade_mode": account_info.get("trade_mode", 0),
            }
        )

        today = timezone.now().date()

        current_balance = float(account_info.get("balance", 0.0))
        current_equity = float(account_info.get("equity", 0.0))
        current_margin = float(account_info.get("margin", 0.0))
        current_margin_free = float(account_info.get("margin_free", 0.0))
        current_margin_level = float(account_info.get("margin_level", 0.0))
        current_leverage = int(account_info.get("leverage", 0))
        latest_snapshot = account.snapshots.order_by("-date").first()

        # Calculate realized profit from deal history since last snapshot
        if latest_snapshot:
            current_profit = calculate_realized_profit(
                mt5_client,
                date_from=latest_snapshot.date.isoformat(),
                date_to=today.isoformat(),
                fallback_balance_diff=current_balance - latest_snapshot.balance,
            )
        else:
            current_profit = 0.0

        if latest_snapshot:
            # Check if all relevant metrics are unchanged
            if (
                latest_snapshot.balance == current_balance
                and latest_snapshot.equity == current_equity
                and latest_snapshot.margin == current_margin
                and latest_snapshot.margin_free == current_margin_free
                and latest_snapshot.margin_level == current_margin_level
                and latest_snapshot.leverage == current_leverage
                and latest_snapshot.profit == current_profit
            ):
                LOGGER.info(f"Account {login} sync completed. No changes from previous snapshot.")
                return {"login": login, "snapshot_updated": False, "created": False, "reason": "unchanged"}

        # Create or update today's snapshot
        snapshot, s_created = AccountSnapshot.objects.update_or_create(
            account=account,
            date=today,
            defaults={
                "balance": current_balance,
                "equity": current_equity,
                "margin": current_margin,
                "margin_free": current_margin_free,
                "margin_level": current_margin_level,
                "leverage": current_leverage,
                "profit": current_profit,
            }
        )

        LOGGER.info(f"Account {login} sync completed. Snapshot created: {s_created}")
        return {"login": login, "snapshot_updated": True, "created": s_created}
    except Exception as e:
        LOGGER.exception(f"Error saving account sync details: {e}")
        raise self.retry(exc=e, countdown=300)
    finally:
        mt5_client.close()
