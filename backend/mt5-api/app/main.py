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
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
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

    success: bool = Field(
        ..., description="Whether the operation succeeded")
    message: str = Field(
        ..., description="Human-readable status message")
    terminal_info: Optional[Dict[str, Any]] = Field(
        None, description="MT5 terminal information")


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
                "trade_mode": 0
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
        ..., description="Timeframe (M1, M5, M15, M30, H1, H4, D1, W1, MN1)")
    count: int = Field(
        100, ge=1, le=99999, description="Number of bars to retrieve")
    start_pos: int = Field(
        0, ge=0, description="Start position for data retrieval")

    @field_validator("timeframe")
    def validate_timeframe(cls, v):
        """Validate timeframe string and convert to MT5 constant."""
        valid_timeframes = {
            'M1': mt5.TIMEFRAME_M1,
            'M5': mt5.TIMEFRAME_M5,
            'M15': mt5.TIMEFRAME_M15,
            'M30': mt5.TIMEFRAME_M30,
            'H1': mt5.TIMEFRAME_H1,
            'H4': mt5.TIMEFRAME_H4,
            'D1': mt5.TIMEFRAME_D1,
            'W1': mt5.TIMEFRAME_W1,
            'MN1': mt5.TIMEFRAME_MN1
        }
        if v.upper() not in valid_timeframes:
            raise ValueError(
                f"Invalid timeframe. Must be one of: {', '.join(valid_timeframes.keys())}")     # noqa: E501
        return v.upper()

    class Config:
        json_schema_extra = {
            "example": {
                "symbol": "EURUSD",
                "timeframe": "H1",
                "count": 100,
                "start_pos": 0
            }
        }


class MarketRatesResponse(BaseModel):
    """Response model for rate data."""

    symbol: str = Field(..., description="Trading symbol")
    timeframe: str = Field(..., description="Timeframe")
    count: int = Field(..., description="Number of bars returned")
    rates: List[MarketRatesData] = Field(..., description="List of rate data")


class TradeRequest(BaseModel):
    """Request model for sending trade orders."""

    action: str = Field(..., description="Trade action: BUY or SELL")
    symbol: str = Field(..., description="Trading symbol (e.g., EURUSD)")
    volume: float = Field(..., gt=0, description="Trading volume in lots")
    order_type: str = Field(
        "MARKET", description="Order type: MARKET, LIMIT, STOP")
    price: Optional[float] = Field(
        None, description="Order price (required for LIMIT/STOP orders)")
    sl: Optional[float] = Field(None, description="Stop Loss price")
    tp: Optional[float] = Field(None, description="Take Profit price")
    deviation: int = Field(
        20, ge=0, description="Maximum price deviation in points")
    magic: int = Field(0, description="Expert Advisor ID")
    comment: str = Field("", max_length=31, description="Order comment")

    @field_validator("action")
    def validate_action(cls, v):
        """Validate trade action."""
        valid_actions = ['BUY', 'SELL']
        if v.upper() not in valid_actions:
            raise ValueError(
                f"Invalid action. Choices: {', '.join(valid_actions)}")
        return v.upper()

    @field_validator("order_type")
    def validate_order_type(cls, v):
        """Validate order type."""
        valid_types = ['MARKET', 'LIMIT', 'STOP']
        if v.upper() not in valid_types:
            raise ValueError(
                f"Invalid order type. Choices: {', '.join(valid_types)}")
        return v.upper()

    class Config:
        json_schema_extra = {
            "example": {
                "action": "BUY",
                "symbol": "EURUSD",
                "volume": 0.1,
                "order_type": "MARKET",
                "sl": 1.0850,
                "tp": 1.0950,
                "deviation": 20,
                "magic": 123456,
                "comment": "API Trade"
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
        ..., description="Human-readable return code description")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "order": 123456789,
                "volume": 0.1,
                "price": 1.0900,
                "bid": 1.0899,
                "ask": 1.0901,
                "comment": "Request executed",
                "request_id": 123456,
                "retcode": 10009,
                "retcode_description": "TRADE_RETCODE_DONE"
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
                detail="MT5 terminal not connected. To trigger a connection, use /api/v1/connect"   # noqa: E501
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
        initialized = mt5.initialize(**params) if params else \
            mt5.initialize()
        try:
            # Initialize MT5 connection at app start
            if not initialized:
                error_code, error_msg = mt5.last_error()
                LOGGER.error(
                    f"MT5 initialization failed.\n{error_code} - {error_msg}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Faled to initialize connection to MT5: {error_msg} (code: {error_code})"   # noqa: E501
                )

            self._initialized = True

            # Get terminal info
            terminal_info = mt5.terminal_info()
            terminal_data = terminal_info._asdict() if terminal_info else {}

            return ConnectionResponse(
                success=True,
                message="Successfully connected to MT5 terminal",
                terminal_info=terminal_data
            )
        except HTTPException:
            raise
        except Exception as e:
            LOGGER.exception(
                "Unexpected error when connecting to MT5 terminal.")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Unexpected error: {str(e)}"
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
                terminal_info=None
            )

        except Exception as e:
            LOGGER.exception(
                "Unexpected error when disconnecting with MT5 terminal.")
            # Even if shutdown fails, mark as not initialized
            self._initialized = False
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error during disconnection: {str(e)}"
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
                LOGGER.error(
                    f"Failed to get account info: {error_code} - {error_msg}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Failed to retrieve account info: {error_msg}"
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
                detail=f"Unexpected error: {str(e)}"
            )

    def get_market_prices(self, request: MarketRatesRequest) -> MarketRatesResponse:    # noqa: E501
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
                request.symbol,
                timeframe,
                request.start_pos,
                request.count
            )

            if rates is None or len(rates) == 0:
                error_code, error_msg = mt5.last_error()
                LOGGER.error(
                    f"Failed to get market rates: {error_code} - {error_msg}")
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"No market rates found for {request.symbol}: {error_msg}"   # noqa: E501
                )

            # Convert to DataFrame and then to list of dicts
            df = pd.DataFrame(rates)
            df["time"] = pd.to_datetime(df["time"], unit="s")

            rates_list = [
                MarketRatesData(
                    time=row['time'],
                    open=row['open'],
                    high=row['high'],
                    low=row['low'],
                    close=row['close'],
                    tick_volume=int(row['tick_volume']),
                    spread=int(row['spread']),
                    real_volume=int(row['real_volume'])
                )
                for _, row in df.iterrows()
            ]

            LOGGER.info(
                f"Retrived {len(rates_list)} rates for {request.symbol} {request.timeframe}")   # noqa: E501

            return MarketRatesResponse(
                symbol=request.symbol,
                timeframe=request.timeframe,
                count=len(rates_list),
                rates=rates_list
            )

        except HTTPException:
            raise
        except Exception as e:
            LOGGER.exception("Unexpected error retrieving market rates")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Unexpected error: {str(e)}"
            )

    def send_market_order(self, request: TradeRequest) -> TradeResponse:
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
                    detail=f"Symbol {request.symbol} not found"
                )

            # Check if available to trade,
            if not symbol_info.visible:
                if not mt5.symbol_select(request.symbol, True):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Failed to enable symbol {request.symbol}"
                    )

            # Determine order type
            if request.action == "BUY":
                order_type = mt5.ORDER_TYPE_BUY if \
                    request.order_type == "MARKET" else \
                    mt5.ORDER_TYPE_BUY_LIMIT
                price = mt5.symbol_info_tick(request.symbol).ask if \
                    request.price is None else request.price
            else:  # SELL
                order_type = mt5.ORDER_TYPE_SELL if \
                    request.order_type == "MARKET" else \
                    mt5.ORDER_TYPE_SELL_LIMIT
                price = mt5.symbol_info_tick(request.symbol).bid if \
                    request.price is None else request.price

            # Build trade request dictionary
            trade_request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": request.symbol,
                "volume": request.volume,
                "type": order_type,
                "price": price,
                "deviation": request.deviation,
                "magic": request.magic,
                "comment": request.comment,
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": symbol_info.filling_mode,
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
                    detail=f"Failed to send order: {error_msg}"
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

            retcode = result_dict.get('retcode', 0)
            retcode_description = retcode_map.get(
                retcode, f"UNKNOWN_CODE_{retcode}")

            success = retcode == 10009  # Success return code
            if success:
                LOGGER.info(
                    f"Order executed successfully: {result_dict.get('order')}")
            else:
                LOGGER.warning(
                    f"Order execution failed: {retcode_description} - {result_dict.get('comment')}")    # noqa: E501

            return TradeResponse(
                success=success,
                order=result_dict.get('order'),
                volume=result_dict.get('volume'),
                price=result_dict.get('price'),
                bid=result_dict.get('bid'),
                ask=result_dict.get('ask'),
                comment=result_dict.get('comment'),
                request_id=result_dict.get('request_id'),
                retcode=retcode,
                retcode_description=retcode_description
            )
        except HTTPException:
            raise
        except Exception as e:
            LOGGER.exception("Unexpected error sending order")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Unexpected error: {str(e)}"
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
    docs_url="/docs", redoc_url="/redoc"
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
    description="Return MT5 API service status, version and, MT5 terminal connection status"    # noqa: E501
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
            "mt5_connected": str(mt5_service.is_connected)
        }
    }


@app.post(
    "/api/v1/connect",
    response_model=ConnectionResponse,
    status_code=status.HTTP_200_OK,
    tags=["Health & Connection"],
    summary="Connect to MT5 Terminal",
    description="Initialize and establish connection to the MetaTrader5 terminal"   # noqa: E501
)
async def connect_mt5(
    params: dict,
    service: MT5Service = Depends(get_mt5_service)
):
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
    description="Shut down the connection to the MetaTrader5 terminal"
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
    description="Retrieve current account information including balance, equity, and margin"    # noqa: E501
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
    account_info = await loop.run_in_executor(
        executor, service.get_account_info)
    return account_info


# Data Endpoints
@app.get(
    "/api/v1/rates",
    response_model=MarketRatesResponse,
    status_code=status.HTTP_200_OK,
    tags=["Market Rates/Data"],
    summary="Get Historical Market Rates",
    description="Retrieve historical OHLCV data for a specified symbol and timeframe"   # noqa: E501
)
async def get_market_rates(
        symbol: str = "XAUUSD", timeframe: str = "M30",
        service: MT5Service = Depends(get_mt5_service)):
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
    rate_request = MarketRatesRequest(
        symbol=symbol, timeframe=timeframe)

    loop = asyncio.get_event_loop()
    rates = await loop.run_in_executor(
        executor,  service.get_market_prices, rate_request
    )
    return rates


# Orders Endpoint
@app.post(
    "/api/v1/order/send",
    response_model=TradeResponse,
    status_code=status.HTTP_200_OK,
    tags=["Trades Execution"],
    summary="Send Trade Order",
    description="Execute a trade order (buy/sell) on the MT5 terminal"
)
async def send_order(
    request: TradeRequest,
    service: MT5Service = Depends(get_mt5_service)
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
    result = await loop.run_in_executor(executor, service.send_market_order, request)
    return result


# --- Running the API ---

if __name__ == "__main__":
    # Note: Use 'python -m uvicorn main:app --reload' for development
    uvicorn.run(app, host="0.0.0.0", port=5001)
