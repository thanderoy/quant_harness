import logging
import re
from typing import Dict, Optional, List

from app.quant.strategies.base import BaseStrategy
from app.adapters.mt5_api import MT5APIClient
from app.adapters.utils.create import create_trade as create_trade_record
from app.config import settings


LOGGER = logging.getLogger(__name__)


class ForexeroStrategy(BaseStrategy):
    """
    Streams Forexero Telegram signals and executes trades via MT5 API.
    For each signal, opens up to max_positions (TP1..TPn) positions and records
    them in the DB as Trade entries.
    """

    def __init__(
        self,
        *,
        mt5_base_url: Optional[str] = None,
        volume_per_order: float = 0.02,
        deviation: int = 20,
        magic_number: int = 2460000,
        trades_per_tp: int = 1,
        use_tps: Optional[List[int]] = None,
        ignore_high_risk_trades: bool = False,
    ):
        super().__init__()
        self.volume_per_order = volume_per_order
        self.deviation = deviation
        self.magic_number = magic_number
        self.trades_per_tp = trades_per_tp
        self.use_tps = use_tps if use_tps is not None else [1]
        self.ignore_high_risk_trades = ignore_high_risk_trades

        base_url = mt5_base_url or settings.MT5_API_URL
        self.MT5_API_CLIENT = MT5APIClient(base_url=base_url)

        # Try to connect MT5 once, ignore errors (we'll retry on send)
        try:
            self.MT5_API_CLIENT.connect()
        except Exception as e:
            LOGGER.warning(f"Could not connect MT5 at init: {e}")

        # Cache leverage for capital calculations
        self.account_leverage: float = 400.0
        try:
            info = self.MT5_API_CLIENT.get_account_info()
            self.account_leverage = float(info.get("leverage", self.account_leverage))
        except Exception as e:
            LOGGER.warning(f"Failed to get MT5 account info: {e}")

    def _normalize_symbol(self, symbol: str) -> str:
        # Remove emojis, slashes and spaces e.g. "🔔XAU/USD🔔" -> "XAUUSD"
        s = symbol.replace("🔔", "").replace("/", "").replace(" ", "")
        return s.upper()

    def _extract_signal_data(self, signal: dict) -> Optional[Dict[str, str]]:
        content = signal.get("content")
        if not content:
            return None

        data: Dict[str, str] = {}
        lines = [ln.strip() for ln in content.split("\n") if ln.strip()]
        if not lines:
            return None

        # First non-empty line is the symbol line
        symbol = self._normalize_symbol(lines[0])
        if symbol not in ["XAUUSD", "EURUSD", "GBPUSD", "NZDUSD", "AUDUSD"]:
            LOGGER.warning(f"FXZ: Invalid symbol {symbol}, skipping signal")
            return None

        data["Symbol"] = symbol

        # Remaining lines are key/value pairs like "Direction: BUY" or "TP1 1970.00"
        # Allow spaces in keys (e.g. "Entry Price")
        kv_pattern = re.compile(
            r"^(?P<key>[A-Za-z0-9 ]+?)\s*[:]\s*(?P<val>.+?)\s*$|^(?P<key_nc>[A-Za-z0-9]+)\s+(?P<val_nc>.+?)\s*$"
        )

        for line in lines[1:]:
            # Try matching with colon first
            m = kv_pattern.match(line)
            if not m:
                continue

            if m.group("key"):
                key_raw = m.group("key")
                val_raw = m.group("val")
            else:
                key_raw = m.group("key_nc")
                val_raw = m.group("val_nc")

            key = key_raw.strip().upper()
            val = val_raw.replace("\xa0", " ").strip()
            # Normalize common keys
            key = {
                "DIRECTION": "Direction",
                "ENTRYPRICE": "Entry Price",
                "SL": "SL",
                "TP": "TP",
                "TP1": "TP1",
                "TP2": "TP2",
                "TP3": "TP3",
            }.get(key, key.title())
            data[key] = val

        return data

    def _parse_float(self, v: Optional[str]) -> Optional[float]:
        try:
            return None if v is None else float(str(v).split()[0])
        except Exception:
            return None

    def process_signal(self, signal: dict):
        """
        Synchronously process a signal: parse, validate, and execute trades.
        """
        if not signal:
            LOGGER.info("FXZ: Empty signal object, skipping")
            return

        # Check whether to ignore 'HIGH RISK' trades
        if self.ignore_high_risk_trades:
            content = signal.get("content", "").upper()
            if content and "HIGH RISK" in content:
                LOGGER.info("FXZ: Skipping HIGH RISK signal")
                return

        data = self._extract_signal_data(signal)
        if not data:
            LOGGER.info("FXZ: Could not parse signal content, skipping")
            return

        symbol = data.get("Symbol")
        action = (data.get("Direction") or "").strip().upper()
        entry_price = self._parse_float(data.get("Entry Price"))
        sl = self._parse_float(data.get("SL"))

        # Validate required fields before proceeding
        if not symbol:
            LOGGER.warning("FXZ: Missing or invalid symbol, skipping signal")
            return

        if action not in ("BUY", "SELL"):
            LOGGER.warning(
                f"FXZ: Invalid action '{action}', must be BUY or SELL, skipping signal"
            )
            return

        # Prepare list of (tp_index, tp_value) to execute
        valid_tps: List[tuple[int, Optional[float]]] = []

        # 1. Try to extract specific values for requested TPs
        for i in self.use_tps:
            val = self._parse_float(data.get(f"TP{i}"))
            if val is not None:
                valid_tps.append((i, val))

        # 2. If no specific keys found, try generic "TP"
        if not valid_tps:
            val = self._parse_float(data.get("TP"))
            if val is not None:
                # Assign generic TP to the first requested TP index
                if self.use_tps:
                    valid_tps.append((self.use_tps[0], val))

        # 3. If still nothing, place one order without TP if use_tps is configured
        if not valid_tps and self.use_tps:
            valid_tps.append((self.use_tps[0], None))

        # Fetch tick data once before placing orders (for order type determination)
        tick_data = None
        if entry_price:
            try:
                tick_data = self.MT5_API_CLIENT.get_tick(symbol)
                LOGGER.info(
                    f"Fetched tick for {symbol}: bid={tick_data.get('bid')}, ask={tick_data.get('ask')}"
                )
            except Exception as e:
                LOGGER.warning(f"Failed to get tick for {symbol}: {e}")

        # Place orders
        for tp_idx, tp in valid_tps:
            for _ in range(self.trades_per_tp):
                # Determine order type dynamically based on current tick price
                order_type = "MARKET"  # Default to market if no entry price

                if entry_price:
                    if tick_data:
                        bid = tick_data.get("bid")
                        ask = tick_data.get("ask")

                        if action == "BUY":
                            # BUY_LIMIT: entry below current ask (waiting for price to come down)
                            # BUY_STOP: entry at or above current ask (waiting for price to break up)
                            if entry_price < ask:
                                order_type = "LIMIT"
                            else:
                                order_type = "STOP"
                            LOGGER.info(
                                f"BUY: entry={entry_price}, ask={ask}, order_type={order_type}"
                            )
                        else:  # SELL
                            # SELL_LIMIT: entry above current bid (waiting for price to rise)
                            # SELL_STOP: entry at or below current bid (waiting for price to break down)
                            if entry_price > bid:
                                order_type = "LIMIT"
                            else:
                                order_type = "STOP"
                            LOGGER.info(
                                f"SELL: entry={entry_price}, bid={bid}, order_type={order_type}"
                            )
                    else:
                        # Fallback to LIMIT if tick fetch failed
                        order_type = "LIMIT"
                        LOGGER.warning("Using LIMIT order type (tick data unavailable)")

                try:
                    order_data = {
                        "entry_price": entry_price,
                        "tp": tp,
                        "sl": sl,
                        "order_type": order_type,
                    }
                    LOGGER.info(f"Data: {order_data}")
                    # Synchronous call
                    order = self.MT5_API_CLIENT.send_order(
                        action=action,
                        symbol=symbol,
                        volume=self.volume_per_order,
                        order_type=order_type,
                        price=entry_price,
                        sl=sl,
                        tp=tp,
                        deviation=self.deviation,
                        magic=self.magic_number,
                        comment=f"FXZ TP{tp_idx}" if tp is not None else "FXZ",
                    )

                    # Create Trade object in DB if order succeeded
                    if order and order.get("success") is True:
                        executed_price = order.get("price", entry_price)
                        executed_volume = order.get("volume", self.volume_per_order)
                        # Basic capital approximation (contract size for gold = 100)
                        contract_size = 100
                        try:
                            order_size_usd = (
                                float(executed_volume)
                                * contract_size
                                * float(executed_price)
                            )
                            capital_used = order_size_usd / float(self.account_leverage)
                        except Exception:
                            capital_used = 0.0

                        try:
                            create_trade_record(
                                order,
                                symbol=symbol,
                                direction=action,
                                entry_price=float(executed_price),
                                order_volume=float(executed_volume),
                                capital=capital_used,
                                leverage=float(self.account_leverage),
                                broker="MetaQuotes-Demo",
                                market_type="FOREX",
                                strategy=self.__class__.__name__,
                                timeframe="1H",
                                sl=sl,
                                tp=tp,
                            )
                        except Exception as e:
                            LOGGER.error(
                                {
                                    "error": f"Failed to create trade record: {e}",
                                    "order": order,
                                }
                            )
                    else:
                        retcode = (
                            order.get("retcode", "unknown") if order else "no response"
                        )
                        retcode_desc = (
                            order.get("retcode_description", "") if order else ""
                        )
                        LOGGER.error(
                            {
                                "error": f"Order failed: {retcode} - {retcode_desc}",
                                "order": order,
                            }
                        )

                except Exception as e:
                    LOGGER.error({"error": f"Order placement error: {e}", "data": data})
