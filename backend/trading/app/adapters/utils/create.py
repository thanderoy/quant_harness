import logging
from datetime import datetime

from app.trades.models import Trade, TradeClosePricesMutation

logger = logging.getLogger(__name__)


def get_trading_session() -> str:
    """Determine current trading session based on UTC time."""
    hour = datetime.utcnow().hour
    if 0 <= hour < 8:
        return "ASIA"
    elif 8 <= hour < 16:
        return "LONDON"
    else:
        return "NEW_YORK"


def create_trade(
    order: dict,
    symbol: str,
    direction: str,
    entry_price: float,
    order_volume: float,
    market_type: str,
    strategy: str,
    timeframe: str,
    sl: float = None,
    tp: float = None,
    account=None,
    environment: str = "prod",
):
    """
    Create a Trade record from an executed order.
    
    Args:
        order: The order response from MT5 API containing 'order' ticket
        symbol: Trading symbol (e.g., XAUUSD)
        direction: Trade direction ('BUY' or 'SELL')
        entry_price: Entry price of the trade
        order_volume: Volume in lots
        market_type: Market type (FOREX, CRYPTO, OTHER)
        strategy: Strategy name
        timeframe: Timeframe (1M, 5M, 15M, 1H, 4H, 1D)
        sl: Stop loss price (optional)
        tp: Take profit price (optional)
        account: Account model instance (optional)
    
    Returns:
        Tuple of (Trade, TradeClosePricesMutation) or None on error
    """
    try:
        broker_id = str(order.get("order", ""))
        
        if not broker_id:
            logger.error("Order missing 'order' field (broker_id)")
            return None

        # Create Trade instance
        trade = Trade.objects.create(
            broker_id=broker_id,
            symbol=symbol,
            direction=direction.upper(),
            entry_price=entry_price,
            order_volume=order_volume,
            account=account,
            market_type=market_type,
            strategy=strategy,
            timeframe=timeframe,
            session=get_trading_session(),
            sl=sl,
            tp=tp,
            synched=False,
            environment=environment.upper(),
        )

        # Create initial TradeClosePricesMutation
        mutation = TradeClosePricesMutation.objects.create(
            trade=trade,
            mutation_price=entry_price,
            new_tp_price=tp,
            new_sl_price=sl,
        )

        logger.info(f"Created trade {trade.id} with broker_id {broker_id}")
        return trade, mutation

    except Exception as e:
        logger.exception(f"Error creating trade: {e}")
        return None
