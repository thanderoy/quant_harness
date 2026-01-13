#!/usr/bin/env python3
import json
import logging
from typing import Any, Dict, Optional
from urllib.parse import urljoin

import requests

LOG = logging.getLogger("MT5 API Client")


class APIError(Exception):
    """Raised when the MT5 API returns an error or cannot be reached."""


class MT5APIClient:
    """
    Minimal client wrapper for the MT5 API.

    Endpoints:
      - GET    /                           -> health/info
      - POST   /api/v1/connect             -> connect to MT5 terminal (JSON body: MetaTrader5.initialize kwargs)
      - POST   /api/v1/disconnect          -> disconnect from MT5 terminal
      - GET    /api/v1/account             -> account info
      - GET    /api/v1/rates?symbol=...&timeframe=... -> historical rates (count/start_pos fixed by server defaults)
      - POST   /api/v1/order/send          -> send trade order
    """

    def __init__(self, base_url: str, timeout: float = 30.0, verify: bool = True):
        if not base_url.startswith("http"):
            raise ValueError("base_url must start with http:// or https://")
        self.base_url = base_url if base_url.endswith("/") else f"{base_url}/"
        self.timeout = timeout
        self.verify = verify
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})

    def close(self):
        self.session.close()

    def _url(self, path: str) -> str:
        return urljoin(self.base_url, path.lstrip("/"))

    def _handle(self, resp: requests.Response) -> Any:
        if resp.status_code >= 400:
            try:
                payload = resp.json()
            except Exception:
                payload = {"detail": resp.text}
            raise APIError(
                f"HTTP {resp.status_code}: {json.dumps(payload, ensure_ascii=False)}"
            )
        if resp.headers.get("content-type", "").startswith("application/json"):
            return resp.json()
        return resp.text

    # --- Public API methods ---

    def health(self) -> Dict[str, Any]:
        resp = self.session.get(
            self._url("/"), timeout=self.timeout, verify=self.verify
        )
        return self._handle(resp)

    def connect(
        self,
        path: Optional[str] = None,
        login: Optional[int] = None,
        password: Optional[str] = None,
        server: Optional[str] = None,
        timeout: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Parameters map directly to MetaTrader5.initialize(...).
        Include only what you need; missing values are omitted.
        """
        payload: Dict[str, Any] = {}
        if path is not None:
            payload["path"] = path
        if login is not None:
            payload["login"] = login
        if password is not None:
            payload["password"] = password
        if server is not None:
            payload["server"] = server
        if timeout is not None:
            payload["timeout"] = timeout
        resp = self.session.post(
            self._url("/api/v1/connect"),
            json=payload,
            timeout=self.timeout,
            verify=self.verify,
        )
        return self._handle(resp)

    def disconnect(self) -> Dict[str, Any]:
        resp = self.session.post(
            self._url("/api/v1/disconnect"), timeout=self.timeout, verify=self.verify
        )
        return self._handle(resp)

    def get_account_info(self) -> Dict[str, Any]:
        resp = self.session.get(
            self._url("/api/v1/account"), timeout=self.timeout, verify=self.verify
        )
        return self._handle(resp)

    def get_market_rates(self, symbol: str, timeframe: str) -> Dict[str, Any]:
        """
        timeframe must be one of: M1, M5, M15, M30, H1, H4, D1, W1, MN1.
        Note: server currently uses defaults count=100, start_pos=0.
        """
        tf = self._normalize_timeframe(timeframe)
        params = {"symbol": symbol, "timeframe": tf}
        resp = self.session.get(
            self._url("/api/v1/rates"),
            params=params,
            timeout=self.timeout,
            verify=self.verify,
        )
        return self._handle(resp)

    def send_order(
        self,
        *,
        action: str,
        symbol: str,
        volume: float,
        order_type: str = "MARKET",
        price: Optional[float] = None,
        sl: Optional[float] = None,
        tp: Optional[float] = None,
        deviation: int = 20,
        magic: int = 0,
        comment: str = "",
    ) -> Dict[str, Any]:
        payload = {
            "action": self._normalize_action(action),
            "symbol": symbol,
            "volume": float(volume),
            "order_type": self._normalize_order_type(order_type),
            "deviation": int(deviation),
            "magic": int(magic),
            "comment": str(comment)[:31],
        }
        if price is not None:
            payload["price"] = float(price)
        if sl is not None:
            payload["sl"] = float(sl)
        if tp is not None:
            payload["tp"] = float(tp)
        resp = self.session.post(
            self._url("/api/v1/order/send"),
            json=payload,
            timeout=self.timeout,
            verify=self.verify,
        )
        return self._handle(resp)

    def get_tick(self, symbol: str) -> Dict[str, Any]:
        """
        Retrieve current tick information for a symbol.

        Args:
            symbol: Trading symbol (e.g., XAUUSD)

        Returns:
            Dict with bid, ask, last, volume, time
        """
        params = {"symbol": symbol}
        resp = self.session.get(
            self._url("/api/v1/tick"),
            params=params,
            timeout=self.timeout,
            verify=self.verify,
        )
        return self._handle(resp)

    # --- helpers ---

    @staticmethod
    def _normalize_timeframe(tf: str) -> str:
        allowed = {"M1", "M5", "M15", "M30", "H1", "H4", "D1", "W1", "MN1"}
        t = tf.upper()
        if t not in allowed:
            raise ValueError(
                f"Invalid timeframe '{tf}'. Allowed: {', '.join(sorted(allowed))}"
            )
        return t

    @staticmethod
    def _normalize_action(action: str) -> str:
        a = action.upper()
        if a not in {"BUY", "SELL"}:
            raise ValueError("action must be BUY or SELL")
        return a

    @staticmethod
    def _normalize_order_type(ot: str) -> str:
        o = ot.upper()
        if o not in {"MARKET", "LIMIT", "STOP"}:
            raise ValueError("order_type must be MARKET, LIMIT, or STOP")
        return o
