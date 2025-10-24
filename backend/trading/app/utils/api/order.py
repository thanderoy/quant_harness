import requests
import traceback
from typing import List, Dict, Optional, Union
import logging
from django.conf import settings

logger = logging.getLogger(__name__)

BASE_URL = settings.MT5_API_URL
TIMEOUT = settings.REQUEST_TIMEOUT

def send_market_order(symbol: str, volume: float, order_type: Union[str, int], sl: float, tp: float = None,
                      deviation: int = 20, comment: str = 'From Django Server', magic: int = 234000, type_filling: Optional[int] = None, position_size_usd: float = None, commission: float = None, capital: float = None, leverage: int = 500
 ) -> Dict:
    try:
        # Map order_type ('BUY'/'SELL' or int) to MT5 numeric constants expected by Flask API
        if isinstance(order_type, int):
            order_type_value = order_type
        else:
            order_type_value = {
                'BUY': 0,  # mt5.ORDER_TYPE_BUY
                'SELL': 1, # mt5.ORDER_TYPE_SELL
            }.get(str(order_type).strip().upper())

        if order_type_value is None:
            logger.error(f"Invalid order type: {order_type}. Must be 'BUY' or 'SELL' or an int constant")
            return None

        request = {
            "symbol": symbol,
            "volume": volume,
            "type": order_type_value,
            "sl": sl,
            "deviation": deviation,
            "magic": magic,
            "comment": comment,
        }
        # Only include type_filling if a valid integer constant is provided
        if isinstance(type_filling, int):
            request["type_filling"] = type_filling

        if tp is not None:
            request["tp"] = tp

        logger.info(f"Sending market order: {request}")

        url = f"{BASE_URL}/order"
        response = requests.post(url, json=request, timeout=TIMEOUT)
        response.raise_for_status()

        response_data = response.json()
        order = response_data.get('result')
        if not order:
            error_msg = response_data.get('error', 'Unknown error')
            details = response_data.get('details', '')
            logger.error(f"Order failed: {error_msg} {details}")
            return None

        return order
        
    except requests.exceptions.HTTPError as e:
        error_msg = f"HTTP error sending market order for {symbol}: {e.response.text}"
        logger.error(error_msg)

    except requests.exceptions.Timeout:
        error_msg = f"Timeout sending market order for {symbol}"
        logger.error(error_msg)
    
    except Exception as e:
        error_msg = f"Exception sending market order for {symbol}: {str(e)}\n{traceback.format_exc()}"
        logger.error(error_msg)
    
def modify_sl_tp(ticket: int, sl: float, tp: float = None) -> Dict:
    try:
        request = {
            "position": ticket,
            "sl": sl,
        }

        if (tp_val := tp) is not None:
            request['tp'] = tp_val

        logger.info(f"Sending modify SL/TP request: {request}")

        url = f"{BASE_URL}/modify_sl_tp"
        response = requests.post(url, json=request, timeout=TIMEOUT)
        response.raise_for_status()

        response_data = response.json()

        if result := response_data.get('result'):
            logger.info(f"Modify SL/TP successful: {result}")
            return result
        error_msg = response_data.get('error', 'Unknown error')
        details = response_data.get('details', '')
        logger.error(f"Modify SL/TP failed: {error_msg} {details}")
        return None

    except requests.exceptions.HTTPError as e:
        error_msg = f"HTTP error sending modify SL/TP for {ticket}: {e.response.text}"
        logger.error(error_msg)
       
    except requests.exceptions.Timeout:
        error_msg = f"Timeout sending modify SL/TP for {ticket}"
        logger.error(error_msg)
        return None
    
    except Exception as e:
        error_msg = f"Exception sending modify SL/TP for {ticket}: {str(e)}\n{traceback.format_exc()}"
        logger.error(error_msg)
