import logging
from typing import List, Dict, Any

from app.adapters.mt5_api import MT5APIClient

LOGGER = logging.getLogger(__name__)

# MT5 deal types that represent actual trades (not balance ops, bonuses, etc.)
TRADING_DEAL_TYPES = (0, 1)  # DEAL_TYPE_BUY, DEAL_TYPE_SELL


def calculate_realized_profit(
    mt5_client: MT5APIClient,
    date_from: str,
    date_to: str,
    fallback_balance_diff: float = 0.0,
) -> float:
    """
    Calculate realized trading profit from MT5 deal history in a date range.

    Sums profit + commission + swap + fee for all BUY/SELL deals,
    excluding non-trading operations (deposits, withdrawals, bonuses, etc.).

    Args:
        mt5_client: Connected MT5APIClient instance.
        date_from: Start date in ISO format (e.g. 2024-01-01).
        date_to: End date in ISO format (e.g. 2024-01-31).
        fallback_balance_diff: Value to return if deal history fetch fails.

    Returns:
        Realized profit rounded to 2 decimal places.
    """
    try:
        deals = mt5_client.get_deals(date_from=date_from, date_to=date_to)
        return sum_deal_profits(deals)
    except Exception as e:
        LOGGER.warning(
            f"Failed to fetch deal history for profit calc: {e}. "
            f"Falling back to balance diff: {fallback_balance_diff}"
        )
        return round(fallback_balance_diff, 2)


def sum_deal_profits(deals: List[Dict[str, Any]]) -> float:
    """
    Sum net profit (profit + commission + swap + fee) from trading deals only.

    Args:
        deals: List of deal dicts from the MT5 API.

    Returns:
        Total realized profit rounded to 2 decimal places.
    """
    return round(
        sum(
            d.get("profit", 0.0)
            + d.get("commission", 0.0)
            + d.get("swap", 0.0)
            + d.get("fee", 0.0)
            for d in deals
            if d.get("type") in TRADING_DEAL_TYPES
        ),
        2,
    )
