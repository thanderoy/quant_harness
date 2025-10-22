import requests
from typing import Dict
import logging
import traceback
from django.conf import settings

logger = logging.getLogger(__name__)

BASE_URL = settings.MT5_API_URL
TIMEOUT = settings.REQUEST_TIMEOUT


def get_deal_from_ticket(ticket: int) -> Dict:
    try:
        url = f"{BASE_URL}/get_deal_from_ticket"
        response = requests.get(url, params={"ticket": ticket}, timeout=TIMEOUT)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        error_msg = f"Exception fetching deal for ticket {ticket}: {e}\n{traceback.format_exc()}"
        logger.error(error_msg)
        return None


def get_order_from_ticket(ticket: int) -> Dict:
    try:
        url = f"{BASE_URL}/get_order_from_ticket"
        response = requests.get(url, params={"ticket": ticket}, timeout=TIMEOUT)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        error_msg = f"Exception fetching order for ticket {ticket}: {e}\n{traceback.format_exc()}"
        logger.error(error_msg)
        return None
