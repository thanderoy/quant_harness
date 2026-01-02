import logging
import re
import asyncio
from typing import Dict, Optional

from app.quant.strategies.base import BaseStrategy
from app.adapters.telegram import TelegramAPIClient
from app.adapters.mt5_api import MT5APIClient
from app.adapters.db.create import create_trade as create_trade_record
from app.config import settings


LOGGER = logging.getLogger(__name__)


class ForexeroStrategy(BaseStrategy):
    """
    Streams Forexero Telegram signals and executes trades via MT5 API.
    For each signal, opens up to max_positions (TP1..TPn) positions and records
    them in the DB as Trade entries.
    """

    def __init__(self, *, mt5_base_url: Optional[str] = None):
        super().__init__()
        self.max_positions = 2  # Only work with TP1 and TP2 signals
        self.TELEGRAM_API_CLIENT = TelegramAPIClient()
        base_url = mt5_base_url or settings.MT5_API_URL
        self.MT5_API_CLIENT = MT5APIClient(base_url=base_url)

        # Try to connect MT5 once, ignore errors (we'll retry on send)
        try:
            self.MT5_API_CLIENT.connect()
        except Exception as e:
            LOGGER.warning(f"Could not connect MT5 at init: {e}")

        # Cache leverage for capital calculations
        self.account_leverage: float = 500.0
        try:
            info = self.MT5_API_CLIENT.get_account_info()
            self.account_leverage = float(info.get("leverage", self.account_leverage))
        except Exception as e:
            LOGGER.warning(f"Failed to get MT5 account info: {e}")

    def _normalize_symbol(self, symbol: str) -> str:
        # Remove emojis, slashes and spaces e.g. "🔔XAU/USD🔔" -> "XAUUSD"
        s = symbol.replace('🔔', '').replace('/', '').replace(' ', '')
        return s.upper()

    def _extract_signal_data(self, signal: dict) -> Optional[Dict[str, str]]:
        content = signal.get("content")
        if not content:
            return None

        data: Dict[str, str] = {}
        lines = [ln.strip() for ln in content.split('\n') if ln.strip()]
        if not lines:
            return None

        # First non-empty line is the symbol line
        data['Symbol'] = self._normalize_symbol(lines[0])

        # Remaining lines are key/value pairs like "Direction: BUY" or "TP1 1970.00"
        kv_pattern = re.compile(r"^(?P<key>[A-Za-z0-9]+)\s*:?[\s\t]*(?P<val>.+?)\s*$")
        for line in lines[1:]:
            m = kv_pattern.match(line)
            if not m:
                continue
            key = m['key'].upper()
            val = m['val'].replace('\xa0', ' ').strip()
            # Normalize common keys
            key = {
                'DIRECTION': 'Direction',
                'ENTRY': 'Entry Price',
                'ENTRYPRICE': 'Entry Price',
                'SL': 'SL',
                'TP': 'TP',
                'TP1': 'TP1',
                'TP2': 'TP2',
                'TP3': 'TP3',
            }.get(key, key.title())
            data[key] = val

        return data

    def _parse_float(self, v: Optional[str]) -> Optional[float]:
        try:
            return None if v is None else float(str(v).split()[0])
        except Exception:
            return None

    async def _send_order_async(self, **kwargs):
        """Execute MT5 order in a thread executor to avoid blocking the loop."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, lambda: self.MT5_API_CLIENT.send_order(**kwargs))

    async def enter_trade(self):
        volume_per_order = 0.1
        order_type = "LIMIT"
        deviation = 20

        # Ensure the queue exists
        queue = await self.TELEGRAM_API_CLIENT.get_queue()

        while True:
            try:
                signal = await queue.get()
                if not signal:
                    LOGGER.info("FXZ: Empty signal object, skipping")
                    queue.task_done()
                    continue

                data = self._extract_signal_data(signal)
                if not data:
                    LOGGER.info("FXZ: Could not parse signal content, skipping")
                    queue.task_done()
                    continue

                symbol = data.get("Symbol")
                action = (data.get("Direction") or "").strip().upper()
                entry_price = self._parse_float(data.get("Entry Price"))

                # Prefer TP1/TP2; fall back to a single TP if provided
                tps = [self._parse_float(data.get(f"TP{i}")) for i in range(1, self.max_positions + 1)]
                tps = [tp for tp in tps if tp is not None]
                if not tps and data.get("TP"):
                    tp_val = self._parse_float(data.get("TP"))
                    if tp_val is not None:
                        tps = [tp_val]
                sl = self._parse_float(data.get("SL"))

                if action not in {"BUY", "SELL"}:
                    LOGGER.error({
                        "error": "Invalid or missing Direction in signal",
                        "signal": signal,
                    })
                    queue.task_done()
                    continue

                if not symbol:
                    LOGGER.error({"error": "Missing symbol in signal", "signal": signal})
                    queue.task_done()
                    continue

                # If no TP given, still place a single order without TP
                if not tps:
                    tps = [None]

                # Place up to max_positions orders using TP1..TPn
                for idx, tp in enumerate(tps[: self.max_positions], start=1):
                    try:
                        # Use async wrapper for blocking call
                        order = await self._send_order_async(
                            action=action,
                            symbol=symbol,
                            volume=volume_per_order,
                            order_type=order_type,
                            price=entry_price,
                            sl=sl,
                            tp=tp,
                            deviation=deviation,
                            magic=2460000,
                            comment=f"FXZ TP{idx}" if tp is not None else "FXZ"
                        )

                        # Create Trade object in DB
                        if order and order.get("success", True) is not False:
                            executed_price = order.get("price")
                            executed_volume = order.get("volume", volume_per_order)
                            # Basic notional and capital approximation (fallback contract size)
                            contract_size = 100000
                            try:
                                order_size_usd = float(executed_volume) * contract_size * float(executed_price)
                                capital_used = order_size_usd / float(self.account_leverage)
                            except Exception:
                                order_size_usd = 0.0
                                capital_used = 0.0

                            try:
                                create_trade_record(
                                    order,
                                    symbol=symbol,
                                    capital=capital_used,
                                    position_size_usd=order_size_usd,
                                    leverage=float(self.account_leverage),
                                    commission=0.0,
                                    type=action,
                                    broker='MetaQuotes-Demo',
                                    market='GOLD',
                                    strategy=self.__class__.__name__,
                                    timeframe='1H',
                                    order_volume=float(executed_volume),
                                    sl=sl if sl is not None else 0.0,
                                    tp=tp,
                                )
                            except Exception as e:
                                LOGGER.error(
                                    {"error": f"Failed to create trade record: {e}", "order": order})
                        else:
                            LOGGER.error(
                                {"error": "Order failed", "order": order})

                    except Exception as e:
                        LOGGER.error(
                            {"error": f"Order placement error: {e}", "data": data})

                queue.task_done()

            except Exception as e:
                LOGGER.error(
                    f"Unexpected error occurred when entering trade: {str(e)}")
