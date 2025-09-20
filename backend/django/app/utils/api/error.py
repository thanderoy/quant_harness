import os
import requests
import traceback
from typing import Dict
from dotenv import load_dotenv
import logging

load_dotenv()
logger = logging.getLogger(__name__)

BASE_URL = os.getenv('MT5_API_URL')
TIMEOUT = float(os.getenv('REQUEST_TIMEOUT', '10'))

def last_error() -> Dict:
    try:
        url = f"{BASE_URL}/last_error"
        response = requests.get(url, timeout=TIMEOUT)
        response.raise_for_status()
        
        data = response.json()
        return data
    except Exception as e:
        error_msg = f"Exception fetching last error: {e}\n{traceback.format_exc()}"
        logger.error(error_msg)

def last_error_str() -> Dict:
    try:
        url = f"{BASE_URL}/last_error_str"
        response = requests.get(url, timeout=TIMEOUT)
        response.raise_for_status()
        
        data = response.json()
        return data
    except Exception as e:
        error_msg = f"Exception fetching last error str: {e}\n{traceback.format_exc()}"
        logger.error(error_msg)
