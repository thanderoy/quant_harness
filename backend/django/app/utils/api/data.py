import os
import requests
import traceback
import pandas as pd
from datetime import datetime, timezone
from dotenv import load_dotenv
import logging

from app.utils.constants import MT5Timeframe

load_dotenv()
logger = logging.getLogger(__name__)

BASE_URL = os.getenv('MT5_API_URL')
TIMEOUT = float(os.getenv('REQUEST_TIMEOUT', '10'))

def symbol_info_tick(symbol: str) -> pd.DataFrame:
    try:
        url = f"{BASE_URL}/symbol_info_tick/{symbol}"
        response = requests.get(url, timeout=TIMEOUT)
        response.raise_for_status()
        
        data = response.json()
        # Wrap the data in a list to create a single-row DataFrame
        df = pd.DataFrame([data])
        return df
    except Exception as e:
        error_msg = f"Exception fetching symbol info tick for {symbol}: {e}\n{traceback.format_exc()}"
        logger.error(error_msg)

def symbol_info(symbol) -> pd.DataFrame:
    try:
        url = f"{BASE_URL}/symbol_info/{symbol}"
        response = requests.get(url, timeout=TIMEOUT)
        response.raise_for_status()
        
        data = response.json()
        df = pd.DataFrame([data])
        return df
    except Exception as e:
        error_msg = f"Exception fetching symbol info for {symbol}: {e}\n{traceback.format_exc()}"
        logger.error(error_msg)

def fetch_data_pos(symbol: str, timeframe: MT5Timeframe, bars: int) -> pd.DataFrame:
    try:
        url = f"{BASE_URL}/fetch_data_pos?symbol={symbol}&timeframe={timeframe.value}&num_bars={bars}"
        response = requests.get(url, timeout=TIMEOUT)
        response.raise_for_status()
        
        data = response.json()
        df = pd.DataFrame(data)
        return df
    except Exception as e:
        error_msg = f"Exception fetching data for {symbol} on {timeframe}: {e}\n{traceback.format_exc()}"
        logger.error(error_msg)

def _to_iso_z(dt: datetime) -> str:
    """Return an ISO-8601 string in UTC with trailing 'Z' to match Flask parser expectations."""
    if dt.tzinfo is None:
        # Assume naive is UTC and append Z
        return dt.isoformat() + 'Z'
    # Convert to UTC and strip tzinfo to add 'Z'
    return dt.astimezone(timezone.utc).replace(tzinfo=None).isoformat() + 'Z'


def fetch_data_range(symbol: str, timeframe: MT5Timeframe, from_date: datetime, to_date: datetime) -> pd.DataFrame:
    try:
        url = f"{BASE_URL}/fetch_data_range"
        params = {
            'symbol': symbol,
            'timeframe': timeframe.value,
            'start': _to_iso_z(from_date),
            'end': _to_iso_z(to_date)
        }
        response = requests.get(url, params=params, timeout=TIMEOUT)
        response.raise_for_status()
        
        data = response.json()
        df = pd.DataFrame(data)
        return df
    except Exception as e:
        error_msg = f"Exception fetching data for {symbol} on {timeframe}: {e}\n{traceback.format_exc()}"
        logger.error(error_msg)
