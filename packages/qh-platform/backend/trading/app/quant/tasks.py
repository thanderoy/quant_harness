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


def _sync_trades_for_environment(env_name: str, mt5_url: str) -> dict:
    """Sync unsynched trades for a single MT5 environment."""
    trades = Trade.objects.filter(synched=False, environment=env_name.upper())
    total_count = trades.count()

    if total_count == 0:
        LOGGER.info(f"[{env_name}] No unsynched trades found")
        return {"synched": 0, "failed": 0, "still_open": 0, "rejected": 0, "total": 0}

    mt5_client = MT5APIClient(base_url=mt5_url)
    try:
        mt5_client.connect()
    except Exception as e:
        LOGGER.error(f"[{env_name}] Failed to connect to MT5: {e}")
        raise

    synched_count = 0
    failed_count = 0
    still_open_count = 0
    rejected_count = 0

    for trade in trades:
        try:
            ticket = int(trade.broker_id)

            position = mt5_client.get_position(ticket)
            if position is not None:
                trade.pnl = position.get("profit", 0.0)
                trade.save(update_fields=["pnl"])
                still_open_count += 1
                LOGGER.debug(
                    f"[{env_name}] Trade {trade.id}: OPEN, Updated PnL: {trade.pnl}"
                )
                continue

            order = mt5_client.get_order(ticket)
            if not order:
                LOGGER.warning(
                    f"[{env_name}] No order found for trade {trade.id} (ticket {ticket})"
                )
                failed_count += 1
                continue

            order_state = order.get("state", 0)

            if order_state == 4:  # ORDER_STATE_FILLED
                deals = mt5_client.get_deals(ticket)
                if not deals:
                    LOGGER.warning(
                        f"[{env_name}] No deals found for filled trade {trade.id}"
                    )
                    failed_count += 1
                    continue

                total_pnl = 0.0
                total_commission = 0.0
                total_swap = 0.0
                total_fee = 0.0
                exit_price = 0.0
                exit_time = None
                entry_price_actual = trade.entry_price or 0.0

                in_deals = [d for d in deals if d.get("entry") in (0, 2)]
                if in_deals:
                    first_in_deal = sorted(
                        in_deals, key=lambda x: x.get("time_msc", 0)
                    )[0]
                    entry_price_actual = first_in_deal.get("price", 0.0)

                out_deals = [d for d in deals if d.get("entry") in (1, 3)]
                if out_deals:
                    last_out_deal = sorted(
                        out_deals, key=lambda x: x.get("time_msc", 0)
                    )[-1]
                    exit_price = last_out_deal.get("price", 0.0)
                    time_raw = last_out_deal.get("time")
                    if time_raw:
                        if isinstance(time_raw, str):
                            exit_time = datetime.fromisoformat(
                                time_raw.replace("Z", "+00:00")
                            )
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
                trade.pnl = round(
                    total_pnl + total_commission + total_swap + total_fee, 2
                )

                if trade.tp and trade.exit_price:
                    if trade.direction == "BUY" and trade.exit_price >= trade.tp:
                        trade.exit_reason = "TP"
                    elif trade.direction == "SELL" and trade.exit_price <= trade.tp:
                        trade.exit_reason = "TP"
                    elif (
                        trade.sl
                        and trade.direction == "BUY"
                        and trade.exit_price <= trade.sl
                    ):
                        trade.exit_reason = "SL"
                    elif (
                        trade.sl
                        and trade.direction == "SELL"
                        and trade.exit_price >= trade.sl
                    ):
                        trade.exit_reason = "SL"
                    else:
                        trade.exit_reason = "MANUAL"
                else:
                    trade.exit_reason = "OTHER"

                trade.synched = True
                trade.status = "FILLED"
                trade.save(
                    update_fields=[
                        "entry_price",
                        "exit_price",
                        "exit_time",
                        "exit_reason",
                        "pnl",
                        "status",
                        "synched",
                    ]
                )
                synched_count += 1
                LOGGER.info(
                    f"[{env_name}] Trade {trade.id}: CLOSED, exit_price: {trade.exit_price}, pnl: {trade.pnl}"
                )

            elif order_state in (2, 5, 6):  # CANCELED, REJECTED or EXPIRED
                state_to_status = {2: "CANCELED", 5: "REJECTED", 6: "EXPIRED"}
                state_to_reason = {2: "CANCELED", 5: "REJECTED", 6: "EXPIRED"}

                trade.status = state_to_status.get(order_state, "REJECTED")
                trade.exit_reason = state_to_reason.get(order_state, "OTHER")
                trade.pnl = 0.0
                trade.synched = True
                trade.save(update_fields=["status", "exit_reason", "pnl", "synched"])
                rejected_count += 1
                LOGGER.info(
                    f"[{env_name}] Trade {trade.id}: {trade.status} - "
                    f"{order.get('comment', '')} "
                    f"(state: {order.get('state_description', order_state)})"
                )

            else:
                LOGGER.debug(
                    f"[{env_name}] Trade {trade.id}: {order.get('state_description')}"
                )
                still_open_count += 1

        except Exception as e:
            LOGGER.exception(f"[{env_name}] Error syncing trade {trade.id}: {e}")
            failed_count += 1

    mt5_client.close()
    return {
        "synched": synched_count,
        "failed": failed_count,
        "still_open": still_open_count,
        "rejected": rejected_count,
        "total": total_count,
    }


@shared_task(bind=True, name="app.quant.tasks.sync_trades")
def sync_trades(self):
    """
    Celery task to sync unsynched trades with broker.

    Runs hourly. Iterates over all MT5 environments and syncs trades tagged
    to each environment against its corresponding MT5 instance.
    """
    LOGGER.info("Starting trade sync task...")

    aggregated = {"synched": 0, "failed": 0, "still_open": 0, "rejected": 0, "total": 0}

    for env_name, mt5_url in settings.MT5_ENVIRONMENTS.items():
        try:
            result = _sync_trades_for_environment(env_name, mt5_url)
            for key in aggregated:
                aggregated[key] += result[key]
        except Exception as e:
            LOGGER.error(f"[{env_name}] Sync failed, skipping: {e}")

    LOGGER.info(f"Trade sync completed: {aggregated}")
    return aggregated


def _sync_account_for_environment(env_name: str, mt5_url: str) -> dict:
    """Sync account status and snapshot for a single MT5 environment."""
    from app.trades.models import Account, AccountSnapshot
    from django.utils import timezone

    mt5_client = MT5APIClient(base_url=mt5_url)
    try:
        mt5_client.connect()
        account_info = dict(mt5_client.get_account_info())
    except Exception as e:
        LOGGER.error(f"[{env_name}] Failed to connect or get account info: {e}")
        mt5_client.close()
        raise

    try:
        login = account_info.get("login")
        if not login:
            LOGGER.error(f"[{env_name}] Account info returned no login, aborting sync.")
            return {"error": "no login"}

        account, created = Account.objects.update_or_create(
            login=login,
            environment=env_name.upper(),
            defaults={
                "name": account_info.get("name", ""),
                "server": account_info.get("server", ""),
                "currency": account_info.get("currency", ""),
                "trade_mode": account_info.get("trade_mode", 0),
            },
        )

        today = timezone.now().date()

        current_balance = float(account_info.get("balance", 0.0))
        current_equity = float(account_info.get("equity", 0.0))
        current_margin = float(account_info.get("margin", 0.0))
        current_margin_free = float(account_info.get("margin_free", 0.0))
        current_margin_level = float(account_info.get("margin_level", 0.0))
        current_leverage = int(account_info.get("leverage", 0))
        latest_snapshot = account.snapshots.order_by("-date").first()

        if latest_snapshot:
            current_profit = calculate_realized_profit(
                mt5_client,
                date_from=latest_snapshot.date.isoformat(),
                date_to=today.isoformat(),
                fallback_balance_diff=current_balance - latest_snapshot.balance,
            )
        else:
            current_profit = 0.0

        if latest_snapshot and (
            latest_snapshot.balance == current_balance
            and latest_snapshot.equity == current_equity
            and latest_snapshot.margin == current_margin
            and latest_snapshot.margin_free == current_margin_free
            and latest_snapshot.margin_level == current_margin_level
            and latest_snapshot.leverage == current_leverage
            and latest_snapshot.profit == current_profit
        ):
            LOGGER.info(f"[{env_name}] Account {login} unchanged, skipping snapshot.")
            return {
                "login": login,
                "snapshot_updated": False,
                "created": False,
                "reason": "unchanged",
            }

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
            },
        )

        LOGGER.info(
            f"[{env_name}] Account {login} sync completed. Snapshot created: {s_created}"
        )
        return {"login": login, "snapshot_updated": True, "created": s_created}
    except Exception as e:
        LOGGER.exception(f"[{env_name}] Error saving account sync details: {e}")
        raise
    finally:
        mt5_client.close()


@shared_task(bind=True, name="app.quant.tasks.sync_account_status")
def sync_account_status(self):
    """
    Celery task to sync MT5 account status and take daily snapshots.

    Iterates over all MT5 environments so both prod and test accounts
    are snapshotted in a single task run.
    """
    LOGGER.info("Starting account sync task...")

    results = {}
    for env_name, mt5_url in settings.MT5_ENVIRONMENTS.items():
        try:
            results[env_name] = _sync_account_for_environment(env_name, mt5_url)
        except Exception as e:
            LOGGER.error(f"[{env_name}] Account sync failed, skipping: {e}")
            results[env_name] = {"error": str(e)}

    return results
