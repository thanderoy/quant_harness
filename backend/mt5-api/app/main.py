import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, HTTPException, status
import MetaTrader5 as mt5
import pandas as pd
from pydantic import BaseModel, Field, field_validator
import uvicorn


# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
LOGGER = logging.getLogger("MT5 API Service")

executor = ThreadPoolExecutor(max_workers=4)


class TimeframeEnum(str, Enum):
    """
    Supported timeframes.
    Mapped to MetaTrader5 constants used by mt5.copy_rates_from.
    """

    M1 = "M1"
    M5 = "M5"
    M15 = "M15"
    M30 = "M30"
    H1 = "H1"
    H4 = "H4"
    D1 = "D1"
    W1 = "W1"
    MN1 = "MN1"


# Map TimeframeEnum to mt5 constants
TIMEFRAME_MAP: Dict[TimeframeEnum, int] = {
    TimeframeEnum.M1: mt5.TIMEFRAME_M1,
    TimeframeEnum.M5: mt5.TIMEFRAME_M5,
    TimeframeEnum.M15: mt5.TIMEFRAME_M15,
    TimeframeEnum.M30: mt5.TIMEFRAME_M30,
    TimeframeEnum.H1: mt5.TIMEFRAME_H1,
    TimeframeEnum.H4: mt5.TIMEFRAME_H4,
    TimeframeEnum.D1: mt5.TIMEFRAME_D1,
    TimeframeEnum.W1: mt5.TIMEFRAME_W1,
    TimeframeEnum.MN1: mt5.TIMEFRAME_MN1,
}


class ConnectionResponse(BaseModel):
    """Response model for connection operations."""

    success: bool = Field(..., description="Whether the operation succeeded")
    message: str = Field(..., description="Human-readable status message")
    terminal_info: Optional[Dict[str, Any]] = Field(
        None, description="MT5 terminal information"
    )


class AccountInfo(BaseModel):
    """Response model for account information."""

    login: int = Field(..., description="Account login number")
    balance: float = Field(..., description="Account balance")
    equity: float = Field(..., description="Account equity")
    margin: float = Field(..., description="Used margin")
    margin_free: float = Field(..., description="Free margin")
    margin_level: float = Field(..., description="Margin level percentage")
    profit: float = Field(..., description="Current profit/loss")
    currency: str = Field(..., description="Account currency")
    leverage: int = Field(..., description="Account leverage")
    name: str = Field(..., description="Account holder name")
    server: str = Field(..., description="Connected server name")
    trade_mode: int = Field(..., description="Account trade mode")

    class Config:
        json_schema_extra = {
            "example": {
                "login": 12345678,
                "balance": 10000,
                "equity": 10000,
                "margin": 0,
                "margin_free": 10000,
                "margin_level": 0,
                "profit": 0,
                "currency": "EUR",
                "leverage": 100,
                "name": "John Doe",
                "server": "BrokerServer-Demo",
                "trade_mode": 0,
            }
        }


class MarketRatesData(BaseModel):
    """Model for individual rate/bar data."""

    time: datetime = Field(..., description="Bar opening time")
    open: float = Field(..., description="Open price")
    high: float = Field(..., description="High price")
    low: float = Field(..., description="Low price")
    close: float = Field(..., description="Close price")
    tick_volume: int = Field(..., description="Tick volume")
    spread: int = Field(..., description="Spread")
    real_volume: int = Field(..., description="Real volume")


class MarketRatesRequest(BaseModel):
    """Request model for historical market rates."""

    symbol: str = Field(..., description="Trading symbol (e.g., EURUSD)")
    timeframe: str = Field(
        ..., description="Timeframe (M1, M5, M15, M30, H1, H4, D1, W1, MN1)"
    )
    count: int = Field(100, ge=1, le=99999, description="Number of bars to retrieve")
    start_pos: int = Field(0, ge=0, description="Start position for data retrieval")

    @field_validator("timeframe")
    def validate_timeframe(cls, v):
        """Validate timeframe string and convert to MT5 constant."""
        valid_timeframes = {
            "M1": mt5.TIMEFRAME_M1,
            "M5": mt5.TIMEFRAME_M5,
            "M15": mt5.TIMEFRAME_M15,
            "M30": mt5.TIMEFRAME_M30,
            "H1": mt5.TIMEFRAME_H1,
            "H4": mt5.TIMEFRAME_H4,
            "D1": mt5.TIMEFRAME_D1,
            "W1": mt5.TIMEFRAME_W1,
            "MN1": mt5.TIMEFRAME_MN1,
        }
        if v.upper() not in valid_timeframes:
            raise ValueError(
                f"Invalid timeframe. Must be one of: {', '.join(valid_timeframes.keys())}"
            )  # noqa: E501
        return v.upper()

    class Config:
        json_schema_extra = {
            "example": {
                "symbol": "EURUSD",
                "timeframe": "H1",
                "count": 100,
                "start_pos": 0,
            }
        }


class MarketRatesResponse(BaseModel):
    """Response model for rate data."""

    symbol: str = Field(..., description="Trading symbol")
    timeframe: str = Field(..., description="Timeframe")
    count: int = Field(..., description="Number of bars returned")
    rates: List[MarketRatesData] = Field(..., description="List of rate data")


class TickInfo(BaseModel):
    """Response model for tick information."""

    symbol: str = Field(..., description="Trading symbol")
    bid: float = Field(..., description="Current bid price")
    ask: float = Field(..., description="Current ask price")
    last: float = Field(..., description="Last trade price")
    volume: float = Field(..., description="Volume of last trade")
    time: datetime = Field(..., description="Time of the tick")

    class Config:
        json_schema_extra = {
            "example": {
                "symbol": "XAUUSD",
                "bid": 2650.50,
                "ask": 2650.75,
                "last": 2650.60,
                "volume": 100,
                "time": "2026-01-13T12:00:00",
            }
        }


class TradeRequest(BaseModel):
    """Request model for sending trade orders."""

    action: str = Field(..., description="Trade action: BUY or SELL")
    symbol: str = Field(..., description="Trading symbol (e.g., EURUSD)")
    volume: float = Field(..., gt=0, description="Trading volume in lots")
    order_type: str = Field("MARKET", description="Order type: MARKET, LIMIT, STOP")
    price: Optional[float] = Field(
        None, description="Order price (required for LIMIT/STOP orders)"
    )
    sl: Optional[float] = Field(None, description="Stop Loss price")
    tp: Optional[float] = Field(None, description="Take Profit price")
    deviation: int = Field(20, ge=0, description="Maximum price deviation in points")
    magic: int = Field(0, description="Expert Advisor ID")
    comment: str = Field("", max_length=31, description="Order comment")

    @field_validator("action")
    def validate_action(cls, v):
        """Validate trade action."""
        valid_actions = ["BUY", "SELL"]
        if v.upper() not in valid_actions:
            raise ValueError(f"Invalid action. Choices: {', '.join(valid_actions)}")
        return v.upper()

    @field_validator("order_type")
    def validate_order_type(cls, v):
        """Validate order type."""
        valid_types = ["MARKET", "LIMIT", "STOP"]
        if v.upper() not in valid_types:
            raise ValueError(f"Invalid order type. Choices: {', '.join(valid_types)}")
        return v.upper()

    class Config:
        json_schema_extra = {
            "example": {
                "action": "BUY",
                "symbol": "XAUUSD",
                "volume": 0.1,
                "order_type": "LIMIT",
                "price": 4315.0,
                "sl": 4350.0,
                "tp": 4310.0,
                "deviation": 20,
                "magic": 123456,
                "comment": "API Trade",
            }
        }


class TradeResponse(BaseModel):
    """Response model for trade execution results."""

    success: bool = Field(..., description="Whether the trade was successful")
    order: Optional[int] = Field(None, description="Order ticket number")
    volume: Optional[float] = Field(None, description="Executed volume")
    price: Optional[float] = Field(None, description="Execution price")
    bid: Optional[float] = Field(None, description="Current bid price")
    ask: Optional[float] = Field(None, description="Current ask price")
    comment: Optional[str] = Field(None, description="Broker comment")
    request_id: Optional[int] = Field(None, description="Request ID")
    retcode: int = Field(..., description="Return code")
    retcode_description: str = Field(
        ..., description="Human-readable return code description"
    )


class OrderInfo(BaseModel):
    """Response model for historical order information."""

    ticket: int = Field(..., description="Order ticket number")
    symbol: str = Field(..., description="Trading symbol")
    type: int = Field(..., description="Order type")
    type_description: str = Field(..., description="Human-readable order type")
    state: int = Field(..., description="Order state")
    state_description: str = Field(..., description="Human-readable order state")
    volume_initial: float = Field(..., description="Initial volume requested")
    volume_current: float = Field(..., description="Unfilled volume")
    price_open: float = Field(..., description="Order price")
    price_current: float = Field(..., description="Current price")
    price_stoplimit: float = Field(..., description="StopLimit limit price")
    sl: float = Field(..., description="Stop Loss level")
    tp: float = Field(..., description="Take Profit level")
    time_setup: Optional[datetime] = Field(None, description="Order setup time")
    time_done: Optional[datetime] = Field(None, description="Order execution/cancel time")
    magic: int = Field(..., description="Expert Advisor ID")
    comment: str = Field(..., description="Order comment")
    position_id: int = Field(..., description="Position ID")
    reason: int = Field(..., description="Order placement reason")

    class Config:
        json_schema_extra = {
            "example": {
                "ticket": 123456788,
                "symbol": "XAUUSD",
                "type": 0,
                "type_description": "ORDER_TYPE_BUY",
                "state": 4,
                "state_description": "ORDER_STATE_FILLED",
                "volume_initial": 0.1,
                "volume_current": 0.0,
                "price_open": 2650.50,
                "price_current": 2650.50,
                "price_stoplimit": 0.0,
                "sl": 0.0,
                "tp": 0.0,
                "time_setup": "2026-01-17T11:59:00",
                "time_done": "2026-01-17T12:00:00",
                "magic": 2460000,
                "comment": "FXZ TP1",
                "position_id": 123456787,
                "reason": 3,
            }
        }


class DealInfo(BaseModel):
    """Response model for deal/trade history information."""

    ticket: int = Field(..., description="Deal ticket number")
    order: int = Field(..., description="Associated order ticket")
    symbol: str = Field(..., description="Trading symbol")
    type: int = Field(..., description="Deal type (0=BUY, 1=SELL)")
    type_description: str = Field(..., description="Human-readable deal type")
    entry: int = Field(..., description="Deal entry (0=IN, 1=OUT, 2=INOUT, 3=OUT_BY)")
    entry_description: str = Field(..., description="Human-readable deal entry")
    volume: float = Field(..., description="Deal volume")
    price: float = Field(..., description="Deal execution price")
    profit: float = Field(..., description="Deal profit/loss")
    commission: float = Field(..., description="Commission charged")
    swap: float = Field(..., description="Swap charged")
    fee: float = Field(0.0, description="Deal fee")
    time: datetime = Field(..., description="Deal execution time")
    time_msc: int = Field(..., description="Deal execution time in milliseconds")
    magic: int = Field(..., description="Expert Advisor ID")
    comment: str = Field(..., description="Deal comment")
    external_id: str = Field("", description="Deal external ID")
    reason: int = Field(..., description="Deal execution reason")
    position_id: int = Field(..., description="Position ID")

    class Config:
        json_schema_extra = {
            "example": {
                "ticket": 123456789,
                "order": 123456788,
                "symbol": "XAUUSD",
                "type": 1,
                "type_description": "DEAL_TYPE_SELL",
                "entry": 1,
                "entry_description": "DEAL_ENTRY_OUT",
                "volume": 0.1,
                "price": 2650.50,
                "profit": 150.25,
                "commission": -0.50,
                "swap": -0.10,
                "fee": 0.0,
                "time": "2026-01-17T12:00:00",
                "time_msc": 1705492800000,
                "magic": 2460000,
                "comment": "FXZ TP1",
                "external_id": "",
                "reason": 3,
                "position_id": 123456787,
            }
        }


class PositionInfo(BaseModel):
    """Response model for open position information."""

    ticket: int = Field(..., description="Position ticket number")
    symbol: str = Field(..., description="Trading symbol")
    type: int = Field(..., description="Position type (0=BUY, 1=SELL)")
    type_description: str = Field(..., description="Human-readable position type")
    volume: float = Field(..., description="Position volume")
    price_open: float = Field(..., description="Position open price")
    price_current: float = Field(..., description="Current price")
    profit: float = Field(..., description="Current unrealized profit/loss")
    sl: float = Field(..., description="Stop Loss level")
    tp: float = Field(..., description="Take Profit level")
    time: datetime = Field(..., description="Position open time")
    magic: int = Field(..., description="Expert Advisor ID")
    comment: str = Field(..., description="Position comment")
    swap: float = Field(..., description="Accumulated swap")
    commission: float = Field(0.0, description="Commission (if available)")

    class Config:
        json_schema_extra = {
            "example": {
                "ticket": 123456789,
                "symbol": "XAUUSD",
                "type": 0,
                "type_description": "POSITION_TYPE_BUY",
                "volume": 0.1,
                "price_open": 2640.00,
                "price_current": 2650.50,
                "profit": 105.00,
                "sl": 2630.00,
                "tp": 2670.00,
                "time": "2026-01-17T10:00:00",
                "magic": 2460000,
                "comment": "FXZ TP1",
                "swap": -0.50,
                "commission": -0.25,
            }
        }


class MT5Service:
    """
    Manages MetaTrader5 terminal connections and operations.

    This service handles all interactions with the MT5 terminal, maintaining
        a single connection state and providing thread-safe operations.
    """

    def __init__(self):
        "Initialize the MT5 service."
        self._initialized = False

    @property
    def is_connected(self) -> bool:
        """Check if MT5 terminal is connected and inititlized."""
        return self._initialized and mt5.terminal_info() is not None

    def _ensure_connection(self) -> None:
        """
        Ensure MT5 is connected before operations.

        Raises:
            HTTPException: If MT5 is not connected (503 Service Unavailable)
        """
        if not self.is_connected:
            LOGGER.error("MT5 Terminal is not connected.")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="MT5 terminal not connected. To trigger a connection, use /api/v1/connect",  # noqa: E501
            )

    def connect(self, params: dict) -> ConnectionResponse:
        """
        Initialize and connect to MT5 terminal.

        Args:
            params: Connection parameters

        Returns:
            Response with connection status and terminal info

        Raises:
            HTTPException: If connection fails (500 Internal Server Error)
        """
        initialized = mt5.initialize(**params) if params else mt5.initialize()
        try:
            # Initialize MT5 connection at app start
            if not initialized:
                error_code, error_msg = mt5.last_error()
                LOGGER.error(f"MT5 initialization failed.\n{error_code} - {error_msg}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Faled to initialize connection to MT5: {error_msg} (code: {error_code})",  # noqa: E501
                )

            self._initialized = True

            # Get terminal info
            terminal_info = mt5.terminal_info()
            terminal_data = terminal_info._asdict() if terminal_info else {}

            return ConnectionResponse(
                success=True,
                message="Successfully connected to MT5 terminal",
                terminal_info=terminal_data,
            )
        except HTTPException:
            raise
        except Exception as e:
            LOGGER.exception("Unexpected error when connecting to MT5 terminal.")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Unexpected error: {str(e)}",
            )

    def disconnect(self) -> ConnectionResponse:
        """
        Disconnect from MT5 terminal.

        Returns:
            ConnectionResponse with disconnection status
        """
        try:
            mt5.shutdown()
            self._initialized = False
            LOGGER.debug("Successfully disconnected from MT5 terminal")

            return ConnectionResponse(
                success=True,
                message="Successfully disconnected from MT5 terminal",
                terminal_info=None,
            )

        except Exception as e:
            LOGGER.exception("Unexpected error when disconnecting with MT5 terminal.")
            # Even if shutdown fails, mark as not initialized
            self._initialized = False
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error during disconnection: {str(e)}",
            )

    def get_account_info(self) -> AccountInfo:
        """
        Retrieve current account information.

        Returns:
            AccountInfo with current account data

        Raises:
            HTTPException: If account info cannot be retrieved
        """
        self._ensure_connection()

        try:
            account_info = mt5.account_info()

            if account_info is None:
                error_code, error_msg = mt5.last_error()
                LOGGER.error(f"Failed to get account info: {error_code} - {error_msg}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Failed to retrieve account info: {error_msg}",
                )

            # Convert namedtuple to dict and create AccountInfo model
            account_dict = account_info._asdict()

            return AccountInfo(**account_dict)

        except HTTPException:
            raise
        except Exception as e:
            LOGGER.exception("Unexpected error retrieving account info")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Unexpected error: {str(e)}",
            )

    def get_market_prices(
        self, request: MarketRatesRequest
    ) -> MarketRatesResponse:  # noqa: E501
        """
        Retrieve historical market rates.

        Args:
            request: Rate request parameters

        Returns:
            RateResponse with historical rate data

        Raises:
            HTTPException: If rates cannot be retrieved
        """
        self._ensure_connection()

        try:
            timeframe = TIMEFRAME_MAP[request.timeframe]

            # Get market rates from MT5
            rates = mt5.copy_rates_from_pos(
                request.symbol, timeframe, request.start_pos, request.count
            )

            if rates is None or len(rates) == 0:
                error_code, error_msg = mt5.last_error()
                LOGGER.error(f"Failed to get market rates: {error_code} - {error_msg}")
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"No market rates found for {request.symbol}: {error_msg}",  # noqa: E501
                )

            # Convert to DataFrame and then to list of dicts
            df = pd.DataFrame(rates)
            df["time"] = pd.to_datetime(df["time"], unit="s")

            rates_list = [
                MarketRatesData(
                    time=row["time"],
                    open=row["open"],
                    high=row["high"],
                    low=row["low"],
                    close=row["close"],
                    tick_volume=int(row["tick_volume"]),
                    spread=int(row["spread"]),
                    real_volume=int(row["real_volume"]),
                )
                for _, row in df.iterrows()
            ]

            LOGGER.info(
                f"Retrived {len(rates_list)} rates for {request.symbol} {request.timeframe}"
            )  # noqa: E501

            return MarketRatesResponse(
                symbol=request.symbol,
                timeframe=request.timeframe,
                count=len(rates_list),
                rates=rates_list,
            )

        except HTTPException:
            raise
        except Exception as e:
            LOGGER.exception("Unexpected error retrieving market rates")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Unexpected error: {str(e)}",
            )

    def get_tick(self, symbol: str) -> TickInfo:
        """
        Retrieve current tick information for a symbol.

        Args:
            symbol: Trading symbol (e.g., XAUUSD)

        Returns:
            TickInfo with current bid/ask/last prices

        Raises:
            HTTPException: If tick cannot be retrieved
        """
        self._ensure_connection()

        try:
            symbol_info = mt5.symbol_info(symbol)
            if symbol_info is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Symbol {symbol} not found",
                )

            # Ensure symbol is visible in Market Watch
            if not symbol_info.visible:
                if not mt5.symbol_select(symbol, True):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Failed to enable symbol {symbol}",
                    )

            tick = mt5.symbol_info_tick(symbol)
            if tick is None:
                error_code, error_msg = mt5.last_error()
                LOGGER.error(f"Failed to get tick: {error_code} - {error_msg}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Failed to retrieve tick for {symbol}: {error_msg}",
                )

            return TickInfo(
                symbol=symbol,
                bid=tick.bid,
                ask=tick.ask,
                last=tick.last,
                volume=tick.volume,
                time=datetime.fromtimestamp(tick.time),
            )

        except HTTPException:
            raise
        except Exception as e:
            LOGGER.exception("Unexpected error retrieving tick")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Unexpected error: {str(e)}",
            )

    def send_order(self, request: TradeRequest) -> TradeResponse:
        """
        Send a trade order to MT5.

        Args:
            request: Trade request parameters

        Returns:
            TradeResponse with execution results

        Raises:
            HTTPException: If order cannot be sent or executed
        """
        self._ensure_connection()

        try:
            symbol_info = mt5.symbol_info(request.symbol)

            if symbol_info is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Symbol {request.symbol} not found",
                )

            # Check if available to trade,
            if not symbol_info.visible:
                if not mt5.symbol_select(request.symbol, True):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Failed to enable symbol {request.symbol}",
                    )

            # Get current tick for price reference
            tick = mt5.symbol_info_tick(request.symbol)
            if tick is None:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Failed to get tick for {request.symbol}",
                )

            # Determine order type and price based on action and order_type
            if request.action == "BUY":
                if request.order_type == "MARKET":
                    order_type = mt5.ORDER_TYPE_BUY
                    price = tick.ask
                    trade_action = mt5.TRADE_ACTION_DEAL
                elif request.order_type == "LIMIT":
                    order_type = mt5.ORDER_TYPE_BUY_LIMIT
                    price = request.price if request.price else tick.ask
                    trade_action = mt5.TRADE_ACTION_PENDING
                else:  # STOP
                    order_type = mt5.ORDER_TYPE_BUY_STOP
                    price = request.price if request.price else tick.ask
                    trade_action = mt5.TRADE_ACTION_PENDING
            else:  # SELL
                if request.order_type == "MARKET":
                    order_type = mt5.ORDER_TYPE_SELL
                    price = tick.bid
                    trade_action = mt5.TRADE_ACTION_DEAL
                elif request.order_type == "LIMIT":
                    order_type = mt5.ORDER_TYPE_SELL_LIMIT
                    price = request.price if request.price else tick.bid
                    trade_action = mt5.TRADE_ACTION_PENDING
                else:  # STOP
                    order_type = mt5.ORDER_TYPE_SELL_STOP
                    price = request.price if request.price else tick.bid
                    trade_action = mt5.TRADE_ACTION_PENDING

            # Build trade request dictionary
            trade_request = {
                "action": trade_action,
                "symbol": request.symbol,
                "volume": request.volume,
                "type": order_type,
                "price": price,
                "deviation": request.deviation,
                "magic": request.magic,
                "comment": request.comment,
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_RETURN,
            }

            # Add SL/TP if provided
            if request.sl is not None:
                trade_request["sl"] = request.sl
            if request.tp is not None:
                trade_request["tp"] = request.tp

            result = mt5.order_send(trade_request)

            if result is None:
                error_code, error_msg = mt5.last_error()
                LOGGER.error(f"Order send failed: {error_code} - {error_msg}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Failed to send order: {error_msg}",
                )
            result_dict = result._asdict()

            # Map return codes to descriptions
            retcode_map = {
                10009: "TRADE_RETCODE_DONE",
                10008: "TRADE_RETCODE_PLACED",
                10004: "TRADE_RETCODE_REQUOTE",
                10006: "TRADE_RETCODE_REJECT",
                10007: "TRADE_RETCODE_CANCEL",
                10010: "TRADE_RETCODE_PARTIAL",
                10011: "TRADE_RETCODE_ERROR",
                10012: "TRADE_RETCODE_TIMEOUT",
                10013: "TRADE_RETCODE_INVALID",
                10014: "TRADE_RETCODE_INVALID_VOLUME",
                10015: "TRADE_RETCODE_INVALID_PRICE",
                10016: "TRADE_RETCODE_INVALID_STOPS",
                10017: "TRADE_RETCODE_TRADE_DISABLED",
                10018: "TRADE_RETCODE_MARKET_CLOSED",
                10019: "TRADE_RETCODE_NO_MONEY",
                10020: "TRADE_RETCODE_PRICE_CHANGED",
                10021: "TRADE_RETCODE_PRICE_OFF",
                10022: "TRADE_RETCODE_INVALID_EXPIRATION",
                10023: "TRADE_RETCODE_ORDER_CHANGED",
                10024: "TRADE_RETCODE_TOO_MANY_REQUESTS",
            }

            retcode = result_dict.get("retcode", 0)
            retcode_description = retcode_map.get(retcode, f"UNKNOWN_CODE_{retcode}")

            success = retcode == 10009  # Success return code
            if success:
                LOGGER.info(f"Order executed successfully: {result_dict.get('order')}")
            else:
                LOGGER.warning(
                    f"Order execution failed: {retcode_description} - {result_dict.get('comment')}"
                )  # noqa: E501

            return TradeResponse(
                success=success,
                order=result_dict.get("order"),
                volume=result_dict.get("volume"),
                price=result_dict.get("price"),
                bid=result_dict.get("bid"),
                ask=result_dict.get("ask"),
                comment=result_dict.get("comment"),
                request_id=result_dict.get("request_id"),
                retcode=retcode,
                retcode_description=retcode_description,
            )
        except HTTPException:
            raise
        except Exception as e:
            LOGGER.exception("Unexpected error sending order")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Unexpected error: {str(e)}",
            )

    def get_position_info(self, ticket: int) -> Optional[PositionInfo]:
        """
        Get an open position by its ticket number.

        Args:
            ticket: Position ticket number

        Returns:
            PositionInfo if position is open, None if not found

        Raises:
            HTTPException: If MT5 is not connected
        """
        self._ensure_connection()

        try:
            positions = mt5.positions_get(ticket=ticket)

            if positions is None or len(positions) == 0:
                # Position not found - might be closed
                return None

            pos = positions[0]
            pos_dict = pos._asdict()

            type_map = {0: "POSITION_TYPE_BUY", 1: "POSITION_TYPE_SELL"}

            return PositionInfo(
                ticket=pos_dict["ticket"],
                symbol=pos_dict["symbol"],
                type=pos_dict["type"],
                type_description=type_map.get(pos_dict["type"], f"UNKNOWN_{pos_dict['type']}"),
                volume=pos_dict["volume"],
                price_open=pos_dict["price_open"],
                price_current=pos_dict["price_current"],
                profit=pos_dict["profit"],
                sl=pos_dict.get("sl", 0.0),
                tp=pos_dict.get("tp", 0.0),
                time=datetime.fromtimestamp(pos_dict["time"]),
                magic=pos_dict.get("magic", 0),
                comment=pos_dict.get("comment", ""),
                swap=pos_dict.get("swap", 0.0),
                commission=pos_dict.get("commission", 0.0),
            )

        except HTTPException:
            raise
        except Exception as e:
            LOGGER.exception("Unexpected error getting position")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Unexpected error: {str(e)}",
            )

    def get_order_info(self, ticket: int) -> Optional[OrderInfo]:
        """
        Get a historical order by its ticket number.

        Args:
            ticket: Order ticket number

        Returns:
            OrderInfo with order details, or None if not found

        Raises:
            HTTPException: If MT5 is not connected
        """
        self._ensure_connection()

        try:
            orders = mt5.history_orders_get(ticket=ticket)

            if orders is None or len(orders) == 0:
                return None

            order = orders[0]
            order_dict = order._asdict()

            order_type_map = {
                0: "ORDER_TYPE_BUY",
                1: "ORDER_TYPE_SELL",
                2: "ORDER_TYPE_BUY_LIMIT",
                3: "ORDER_TYPE_SELL_LIMIT",
                4: "ORDER_TYPE_BUY_STOP",
                5: "ORDER_TYPE_SELL_STOP",
                6: "ORDER_TYPE_BUY_STOP_LIMIT",
                7: "ORDER_TYPE_SELL_STOP_LIMIT",
                8: "ORDER_TYPE_CLOSE_BY",
            }

            order_state_map = {
                0: "ORDER_STATE_STARTED",
                1: "ORDER_STATE_PLACED",
                2: "ORDER_STATE_CANCELED",
                3: "ORDER_STATE_PARTIAL",
                4: "ORDER_STATE_FILLED",
                5: "ORDER_STATE_REJECTED",
                6: "ORDER_STATE_EXPIRED",
                7: "ORDER_STATE_REQUEST_ADD",
                8: "ORDER_STATE_REQUEST_MODIFY",
                9: "ORDER_STATE_REQUEST_CANCEL",
            }

            return OrderInfo(
                ticket=order_dict["ticket"],
                symbol=order_dict["symbol"],
                type=order_dict["type"],
                type_description=order_type_map.get(order_dict["type"], f"UNKNOWN_{order_dict['type']}"),
                state=order_dict.get("state", 0),
                state_description=order_state_map.get(order_dict.get("state", 0), "UNKNOWN"),
                volume_initial=order_dict.get("volume_initial", 0.0),
                volume_current=order_dict.get("volume_current", 0.0),
                price_open=order_dict.get("price_open", 0.0),
                price_current=order_dict.get("price_current", 0.0),
                price_stoplimit=order_dict.get("price_stoplimit", 0.0),
                sl=order_dict.get("sl", 0.0),
                tp=order_dict.get("tp", 0.0),
                time_setup=datetime.fromtimestamp(order_dict["time_setup"]) if order_dict.get("time_setup") else None,
                time_done=datetime.fromtimestamp(order_dict["time_done"]) if order_dict.get("time_done") else None,
                magic=order_dict.get("magic", 0),
                comment=order_dict.get("comment", ""),
                position_id=order_dict.get("position_id", 0),
                reason=order_dict.get("reason", 0),
            )

        except HTTPException:
            raise
        except Exception as e:
            LOGGER.exception("Unexpected error getting order")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Unexpected error: {str(e)}",
            )

    DEAL_TYPE_MAP = {
        0: "DEAL_TYPE_BUY",
        1: "DEAL_TYPE_SELL",
        2: "DEAL_TYPE_BALANCE",
        3: "DEAL_TYPE_CREDIT",
        4: "DEAL_TYPE_CHARGE",
        5: "DEAL_TYPE_CORRECTION",
        6: "DEAL_TYPE_BONUS",
        7: "DEAL_TYPE_COMMISSION",
        8: "DEAL_TYPE_COMMISSION_DAILY",
        9: "DEAL_TYPE_COMMISSION_MONTHLY",
        10: "DEAL_TYPE_COMMISSION_AGENT_DAILY",
        11: "DEAL_TYPE_COMMISSION_AGENT_MONTHLY",
        12: "DEAL_TYPE_INTEREST",
        13: "DEAL_TYPE_BUY_CANCELED",
        14: "DEAL_TYPE_SELL_CANCELED",
    }

    DEAL_ENTRY_MAP = {
        0: "DEAL_ENTRY_IN",
        1: "DEAL_ENTRY_OUT",
        2: "DEAL_ENTRY_INOUT",
        3: "DEAL_ENTRY_OUT_BY",
    }

    def _map_deals(self, deals) -> List[DealInfo]:
        """Convert raw MT5 deal tuples to DealInfo models."""
        result = []
        for deal in deals:
            d = deal._asdict()
            result.append(
                DealInfo(
                    ticket=d["ticket"],
                    order=d["order"],
                    symbol=d["symbol"],
                    type=d["type"],
                    type_description=self.DEAL_TYPE_MAP.get(d["type"], f"UNKNOWN_{d['type']}"),
                    entry=d.get("entry", 0),
                    entry_description=self.DEAL_ENTRY_MAP.get(d.get("entry", 0), f"UNKNOWN_{d.get('entry')}"),
                    volume=d["volume"],
                    price=d["price"],
                    profit=d["profit"],
                    commission=d.get("commission", 0.0),
                    swap=d.get("swap", 0.0),
                    fee=d.get("fee", 0.0),
                    time=datetime.fromtimestamp(d["time"]),
                    time_msc=d.get("time_msc", 0),
                    magic=d.get("magic", 0),
                    comment=d.get("comment", ""),
                    external_id=d.get("external_id", ""),
                    reason=d.get("reason", 0),
                    position_id=d.get("position_id", 0),
                )
            )
        return result

    def get_deals(
        self,
        position: Optional[int] = None,
        *,
        ticket: Optional[int] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
    ) -> List[DealInfo]:
        """
        Get historical deals filtered by position/ticket or date range.

        Args:
            position: Position ticket number
            ticket: Order ticket number
            date_from: Start of date range (inclusive)
            date_to: End of date range (inclusive)

        Returns:
            List of DealInfo. Empty list if none found.
        """
        self._ensure_connection()

        has_id_filter = ticket is not None or position is not None
        has_date_filter = date_from is not None and date_to is not None

        if not has_id_filter and not has_date_filter:
            raise ValueError("Must provide either ticket/position or date_from+date_to")

        try:
            if has_date_filter:
                deals = mt5.history_deals_get(date_from, date_to)
            elif ticket is not None:
                deals = mt5.history_deals_get(ticket=ticket)
            else:
                deals = mt5.history_deals_get(position=position)

            if deals is None or len(deals) == 0:
                return []

            return self._map_deals(deals)

        except HTTPException:
            raise
        except Exception as e:
            LOGGER.exception("Unexpected error getting deals")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Unexpected error: {str(e)}",
            )


# FastAPI Lifespan - Connection management
mt5_service = MT5Service()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager for startup and shutdown events.

    Ensures proper cleanup of MT5 connection on application shutdown.
    """
    LOGGER.info("MT5 API Service is starting...")
    yield
    # Cleanup on shutdown
    LOGGER.info("FastAPI application shutting down")
    if mt5_service.is_connected:
        mt5_service.disconnect()


app = FastAPI(
    title="MT5 Terminal API Service.",
    description="MetaTrader5 terminal API service with async HTTP endpoints.",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)


def get_mt5_service() -> MT5Service:
    """
    Dependency injection for MT5Service.

    Returns:
        The global MT5Service instance
    """
    return mt5_service


# Health + Connection Checks Endpoint
@app.get(
    "/",
    status_code=status.HTTP_200_OK,
    tags=["Health & Connection"],
    summary="Checks that the MT5 API Service is Running",
    description="Return MT5 API service status, version and, MT5 terminal connection status",  # noqa: E501
)
async def root():
    """
    Root endpoint for API health check.
    """
    return {
        "success": "true",
        "message": "MT5 API Service is running...",
        "description": {
            "message": "MT5 Terminal API Service.",
            "version": "1.0.0",
            "status": "running",
            "mt5_connected": str(mt5_service.is_connected),
        },
    }


@app.post(
    "/api/v1/connect",
    response_model=ConnectionResponse,
    status_code=status.HTTP_200_OK,
    tags=["Health & Connection"],
    summary="Connect to MT5 Terminal",
    description="Initialize and establish connection to the MetaTrader5 terminal",  # noqa: E501
)
async def connect_mt5(params: dict, service: MT5Service = Depends(get_mt5_service)):
    """
    Connect to MT5 terminal with optional credentials.

    This endpoint initializes the MT5 terminal connection. If credentials are
        provided, it will attempt to login to the specified account. Otherwise,
        it will connect to the default configured account in the MT5 terminal.

    Args:
        params: Connection parameters including login, password, server, etc.
        service: Injected MT5Service instance

    Returns:
        ConnectionResponse with connection status and terminal information
    """
    # Run blocking MT5 operation in thread pool
    loop = asyncio.get_event_loop()
    response = await loop.run_in_executor(executor, service.connect, params)
    return response


@app.post(
    "/api/v1/disconnect",
    response_model=ConnectionResponse,
    status_code=status.HTTP_200_OK,
    tags=["Health & Connection"],
    summary="Disconnect from MT5 Terminal",
    description="Shut down the connection to the MetaTrader5 terminal",
)
async def disconnect_mt5(service: MT5Service = Depends(get_mt5_service)):
    """
    Disconnect from MT5 terminal.

    This endpoint cleanly shuts down the connection to the MT5 terminal.
    It should be called before application shutdown to ensure proper cleanup.

    Args:
        service: Injected MT5Service instance

    Returns:
        ConnectionResponse with disconnection status
    """
    loop = asyncio.get_event_loop()
    response = await loop.run_in_executor(executor, service.disconnect)
    return response


# Account Info Endpoint
@app.get(
    "/api/v1/account",
    response_model=AccountInfo,
    status_code=status.HTTP_200_OK,
    tags=["Account"],
    summary="Get Account Information",
    description="Retrieve current account information including balance, equity, and margin",  # noqa: E501
)
async def get_account_info(service: MT5Service = Depends(get_mt5_service)):
    """
    Get current MT5 account information.

    This endpoint retrieves comprehensive account information including:
    - Balance and equity
    - Margin usage and free margin
    - Current profit/loss
    - Account leverage and currency
    - Server information

    Args:
        service: Injected MT5Service instance

    Returns:
        AccountInfo with current account data
    """
    loop = asyncio.get_event_loop()
    account_info = await loop.run_in_executor(executor, service.get_account_info)
    return account_info


# Data Endpoints
@app.get(
    "/api/v1/rates",
    response_model=MarketRatesResponse,
    status_code=status.HTTP_200_OK,
    tags=["Market Rates/Data"],
    summary="Get Historical Market Rates",
    description="Retrieve historical OHLCV data for a specified symbol and timeframe",  # noqa: E501
)
async def get_market_rates(
    symbol: str = "XAUUSD",
    timeframe: str = "M30",
    service: MT5Service = Depends(get_mt5_service),
):
    """
    Get historical market rates (OHLCV data).

    This endpoint retrieves historical candlestick data for technical analysis.
    The data is returned as a JSON array of rate objects, each containing:
    - Open, High, Low, Close prices
    - Tick volume and real volume
    - Spread information
    - Timestamp

    Args:
        symbol: Trading symbol (e.g., EURUSD, GBPUSD)
        timeframe: Chart timeframe (M1, M5, M15, M30, H1, H4, D1, W1, MN1)
        service: Injected MT5Service instance

    Returns:
        RateResponse with historical rate data
    """
    rate_request = MarketRatesRequest(symbol=symbol, timeframe=timeframe)

    loop = asyncio.get_event_loop()
    rates = await loop.run_in_executor(
        executor, service.get_market_prices, rate_request
    )
    return rates


# Tick Data Endpoint
@app.get(
    "/api/v1/tick",
    response_model=TickInfo,
    status_code=status.HTTP_200_OK,
    tags=["Market Rates/Data"],
    summary="Get Current Tick Data",
    description="Retrieve current bid/ask/last prices for a symbol",
)
async def get_tick(
    symbol: str = "XAUUSD",
    service: MT5Service = Depends(get_mt5_service),
):
    """
    Get current tick information for a symbol.

    This endpoint retrieves the latest tick data including:
    - Current bid and ask prices
    - Last trade price
    - Volume and timestamp

    Args:
        symbol: Trading symbol (e.g., XAUUSD, EURUSD)
        service: Injected MT5Service instance

    Returns:
        TickInfo with current tick data
    """
    loop = asyncio.get_event_loop()
    tick = await loop.run_in_executor(executor, service.get_tick, symbol)
    return tick


# Orders Endpoint
@app.post(
    "/api/v1/order/send",
    response_model=TradeResponse,
    status_code=status.HTTP_200_OK,
    tags=["Orders & Positions"],
    summary="Send Trade Order",
    description="Execute a trade order (buy/sell) on the MT5 terminal",
)
async def send_order(
    request: TradeRequest, service: MT5Service = Depends(get_mt5_service)
):
    """
    Send a trade order to the MT5 terminal.

    This endpoint executes trading operations including:
    - Market orders (immediate execution)
    - Pending orders (limit/stop orders)
    - Stop Loss and Take Profit levels
    - Custom magic numbers and comments

    The response includes the execution result, order ticket, and actual execution price.   # noqa: E501

    Args:
        request: Trade request parameters (action, symbol, volume, etc.)
        service: Injected MT5Service instance

    Returns:
        TradeResponse with execution results
    """
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(executor, service.send_order, request)
    return result


# Position Endpoint
@app.get(
    "/api/v1/position/{ticket}",
    response_model=PositionInfo,
    status_code=status.HTTP_200_OK,
    tags=["Orders & Positions"],
    summary="Get Open Position Info",
    description="Retrieve an open position by its ticket number",
)
async def get_position(
    ticket: int,
    service: MT5Service = Depends(get_mt5_service),
):
    """
    Get an open position by ticket number.

    Returns position details including current profit/loss, entry price,
    and SL/TP levels. Returns 404 if position is not found (may be closed).

    Args:
        ticket: Position ticket number
        service: Injected MT5Service instance

    Returns:
        PositionInfo with position details
    """
    loop = asyncio.get_event_loop()
    position = await loop.run_in_executor(
        executor, service.get_position_info, ticket
    )
    if position is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Position {ticket} not found (may be closed)",
        )
    return position


# Order History Endpoint
@app.get(
    "/api/v1/order/{ticket}",
    response_model=OrderInfo,
    status_code=status.HTTP_200_OK,
    tags=["Orders & Positions"],
    summary="Get Historical Order Info",
    description="Retrieve a historical order by its ticket number",
)
async def get_order(
    ticket: int,
    service: MT5Service = Depends(get_mt5_service),
):
    """
    Get a historical order by ticket number.

    Returns order details including state, execution time, and position info.
    Returns 404 if order is not found in history.

    Args:
        ticket: Order ticket number
        service: Injected MT5Service instance

    Returns:
        OrderInfo with order details
    """
    loop = asyncio.get_event_loop()
    order = await loop.run_in_executor(
        executor, service.get_order_info, ticket
    )
    if order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order {ticket} not found in history",
        )
    return order


# Deal History Endpoint
@app.get(
    "/api/v1/deals",
    response_model=List[DealInfo],
    status_code=status.HTTP_200_OK,
    tags=["Orders & Positions"],
    summary="Get Historical Deals Info",
    description="Retrieve historical deals by position/ticket or date range",
)
async def get_deals(
    position: Optional[int] = None,
    ticket: Optional[int] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    service: MT5Service = Depends(get_mt5_service),
):
    """
    Get historical deals filtered by position/ticket or date range.

    Provide either position/ticket for a specific trade's deals,
    or date_from+date_to for all deals in a period.

    Returns deal details including profit, commission, and swap.
    Returns 404 if no deals are found matching the criteria.
    """
    has_id_filter = position is not None or ticket is not None
    has_date_filter = date_from is not None and date_to is not None

    if not has_id_filter and not has_date_filter:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Must provide either 'position'/'ticket' or 'date_from'+'date_to' parameters",
        )

    dt_from = None
    dt_to = None
    if has_date_filter:
        try:
            dt_from = datetime.fromisoformat(date_from)
            dt_to = datetime.fromisoformat(date_to)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid date format. Use ISO format (e.g. 2024-01-01)",
            )

    loop = asyncio.get_event_loop()
    deals = await loop.run_in_executor(
        executor,
        lambda: service.get_deals(
            position=position,
            ticket=ticket,
            date_from=dt_from,
            date_to=dt_to,
        ),
    )
    if not deals and has_id_filter:
        criteria = f"ticket {ticket}" if ticket else f"position {position}"
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Deals for {criteria} not found in history",
        )
    return deals


# --- Running the API ---

if __name__ == "__main__":
    # Note: Use 'python -m uvicorn main:app --reload' for development
    uvicorn.run(app, host="0.0.0.0", port=5001)

