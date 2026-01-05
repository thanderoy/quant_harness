import logging
from datetime import datetime

from app.trades.models import Trade, TradeClosePricesMutation  # Import models
from app.adapters.arithmetics import get_price_at_pnl, get_pnl_at_price

logger = logging.getLogger(__name__)

def create_trade(order, symbol: str, capital: float, position_size_usd: float,
                 leverage: float, commission: float, type: str, broker: str,
                 market: str, strategy: str, timeframe: str, order_volume: float,
                 sl: float, tp: float = None):
    try:
        entry_price = order.get('price')

        # Create Trade instance
        trade = Trade.objects.create(
            transaction_broker_id=order.get('order'),
            symbol=symbol,
            entry_time=datetime.now(),  # Modify as needed based on actual data
            entry_price=entry_price,
            type=type.upper(),  # Ensure matching choices
            position_size_usd=position_size_usd,  # Example calculation
            capital=capital,  # Set appropriately
            leverage=leverage,  # Adjust based on your data
            order_volume=order_volume,
            order_commission=commission,
            break_even_price=0,
            liquidity_price=0,
            broker=broker,
            market_type=market,
            strategy=strategy,
            timeframe=timeframe,
        )

        # Create TradeClosePricesMutation instance
        mutation = TradeClosePricesMutation.objects.create(
            trade=trade,
            mutation_price=entry_price,  # Example: using SL price
            new_tp_price=tp if tp else None,
            new_sl_price=sl,
            pnl_at_new_tp_price=None,
            pnl_at_new_sl_price=None,
        )

        logger.info({'trade': trade, 'mutation': mutation})

        return trade, mutation
    except Exception as e:
        logger.error(f"Error creating trade: {e}")

