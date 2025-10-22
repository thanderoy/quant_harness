# backend/django/app/quant/algorithms/simple_sma/entry.py

import pandas as pd
import requests
import logging
import traceback

from app.utils.arithmetics import (
    calculate_order_size_usd,
    calculate_commission,
    get_price_at_pnl,
    get_pnl_at_price,
    convert_usd_to_lots,
)
from app.utils.api.data import fetch_data_pos, symbol_info_tick
from app.utils.account import have_open_positions_in_symbol
from app.utils.market import is_market_open
from app.utils.db.create import create_trade
from app.quant.algorithms.simple_sma.config import (
    PAIRS,
    MAIN_TIMEFRAME,
    TP_PNL_MULTIPLIER,
    SL_PNL_MULTIPLIER,
    LEVERAGE,
    DEVIATION,
    CAPITAL_PER_TRADE,
    SMA_WINDOW,
)

logger = logging.getLogger(__name__)


def entry_algorithm():
    try:
        for pair in PAIRS:
            logger.info(f"[SMA] Checking {pair} for open positions.")
            if have_open_positions_in_symbol(pair):
                logger.info(f"[SMA] Skipping {pair}: has open positions.")
                continue

            if not is_market_open(pair):
                logger.info(f"[SMA] Skipping {pair}: market is not open.")
                continue

            bars_needed = max(SMA_WINDOW + 2, 30)
            df = fetch_data_pos(pair, MAIN_TIMEFRAME, bars_needed)
            if df is None or df.empty or 'close' not in df.columns:
                logger.info(f"[SMA] Skipping {pair}: no data or missing close column.")
                continue

            # Compute SMA and use the previous bar to avoid lookahead
            df['sma'] = pd.Series(df['close']).rolling(window=SMA_WINDOW, min_periods=SMA_WINDOW).mean()
            last_row = df.iloc[-2]
            if pd.isna(last_row.get('sma')):
                logger.info(f"[SMA] Skipping {pair}: insufficient data for SMA window.")
                continue

            order_type = 'BUY' if last_row['close'] > last_row['sma'] else 'SELL' if last_row['close'] < last_row['sma'] else None
            if order_type is None:
                logger.info(f"[SMA] No signal for {pair}: price equals SMA.")
                continue

            tick_info = symbol_info_tick(pair)
            if tick_info is None or tick_info.empty:
                logger.info(f"[SMA] Skipping {pair}: no tick info.")
                continue

            order_capital = CAPITAL_PER_TRADE
            last_tick_price = tick_info['ask'].iloc[0] if order_type == 'BUY' else tick_info['bid'].iloc[0]
            price_decimals = len(str(last_tick_price).split('.')[-1])
            order_size_usd = calculate_order_size_usd(order_capital, LEVERAGE)
            order_volume_lots = convert_usd_to_lots(pair, order_size_usd, order_type)

            # Normalize potential Series
            if isinstance(order_volume_lots, (pd.Series, pd.DataFrame)):
                order_volume_lots = order_volume_lots.iloc[0] if not getattr(order_volume_lots, 'empty', True) else 0.0

            if order_volume_lots < 0.01:
                logger.error({'error_msg': f"[SMA] Order volume too low for {pair}", 'order_volume_lots': order_volume_lots})
                continue

            desired_sl_pnl = order_capital * SL_PNL_MULTIPLIER
            commission = calculate_commission(order_size_usd, pair)

            sl_including_commission, sl_excluding_commission = get_price_at_pnl(
                desired_pnl=desired_sl_pnl,
                commission=commission,
                order_size_usd=order_size_usd,
                leverage=LEVERAGE,
                entry_price=last_tick_price,
                type=order_type,
            )

            # Basic sanity on SL vs current quotes
            if order_type == 'BUY':
                if sl_including_commission >= tick_info['bid'].iloc[0]:
                    logger.error({'error_msg': f"[SMA] SL too high for {pair}", 'sl': sl_including_commission})
                    continue
            else:  # SELL
                if sl_including_commission <= tick_info['ask'].iloc[0]:
                    logger.error({'error_msg': f"[SMA] SL too low for {pair}", 'sl': sl_including_commission})
                    continue

            from app.utils.api.order import send_market_order  # late import to keep logs concise
            order = send_market_order(
                symbol=pair,
                volume=order_volume_lots,
                order_type=order_type,
                sl=round(sl_including_commission, price_decimals),
                deviation=DEVIATION,
                type_filling="ORDER_FILLING_FOK",
                position_size_usd=order_size_usd,
                commission=commission,
                capital=order_capital,
                leverage=LEVERAGE,
            )

            if order is not None:
                try:
                    create_trade(
                        order,
                        pair,
                        order_capital,
                        order_size_usd,
                        LEVERAGE,
                        commission,
                        order_type,
                        'Alpari',
                        'FOREX',
                        'SIMPLE SMA',
                        MAIN_TIMEFRAME,
                        order_volume_lots,
                        sl_including_commission,
                        None,
                    )
                except Exception as e:
                    logger.error(f"[SMA] Error creating trade record in DB: {e}\n{traceback.format_exc()}")

                logger.info({
                    'event': 'trade_opened',
                    'symbol': pair,
                    'entry_condition': '[SMA] price vs SMA',
                    'order_capital': f"${order_capital:.5f}",
                    'order_size_usd': f"${order_size_usd:.5f}",
                    'sl_pnl_multiplier': f"{SL_PNL_MULTIPLIER * 100}%",
                    'commission': f"${commission:.5f}",
                    'order_info': {'order': order, 'type': order_type, 'sl': sl_including_commission},
                    'tick_info': tick_info,
                    'sl_detail': {
                        'sl_including_commission': f"${sl_including_commission:.5f}",
                        'pnl_at_sl_including_commission': f"${get_pnl_at_price(sl_including_commission, last_tick_price, order_size_usd, LEVERAGE, order_type, commission)[1]:.5f}",
                    },
                })
            else:
                logger.error({'event': 'trade_failed_to_open', 'symbol': pair, 'type': order_type})

    except requests.RequestException as e:
        logger.error(f"[SMA] Error fetching MT5 data: {str(e)}")
    except Exception as e:
        logger.error(f"[SMA] Exception in entry_algorithm: {e}\n{traceback.format_exc()}")
