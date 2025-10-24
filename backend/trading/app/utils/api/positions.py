import traceback
from typing import List, Dict
from datetime import datetime
import logging
import time

import requests
import pandas as pd
from django.conf import settings

from app.utils.constants import MT5Timeframe

logger = logging.getLogger(__name__)

BASE_URL = settings.MT5_API_URL
TIMEOUT = settings.REQUEST_TIMEOUT

empty_df = pd.DataFrame(columns=[
    'ticket', 'time', 'time_msc', 'time_update', 'time_update_msc', 'type',
    'magic', 'identifier', 'reason', 'volume', 'price_open', 'sl', 'tp',
    'price_current', 'swap', 'profit', 'symbol', 'comment', 'external_id'
])

def get_positions() -> pd.DataFrame:
    try:
        url = f"{BASE_URL}/get_positions"
        start_time = time.time()  # Start timing
        response = requests.get(url, timeout=TIMEOUT)
        end_time = time.time()    # End timing
        duration = end_time - start_time
        logger.info(f"Fetched positions in {duration:.2f} seconds")

        response.raise_for_status()
        
        data = response.json()

        df = pd.DataFrame(data if isinstance(data, list) else [])

        if df.empty:
            return empty_df

        df['time'] = pd.to_datetime(df['time'], unit='s', utc=True)
        df['time_update'] = pd.to_datetime(df['time_update'], unit='s', utc=True)

        return df
    
    except requests.exceptions.Timeout:
        error_msg = f"Timeout fetching positions from {url}"
        logger.error(error_msg)
        return empty_df
    
    except Exception as e:
        error_msg = f"Exception fetching positions: {e}\n{traceback.format_exc()}"
        logger.error(error_msg)
        return empty_df
