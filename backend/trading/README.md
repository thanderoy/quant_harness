# Trading Django App

## Overview

The `trading` Django app provides a modular framework for managing trading algorithms, tracking trades and orders, and interacting with external trading platforms (such as MetaTrader 5) via adapters. It is designed for plug-and-play extensibility, allowing you to add new strategies with minimal changes to the core system.

---

## Features

- **Plug-and-play strategy architecture** (adapter pattern)
- **Order and trade tracking** with Django ORM
- **API endpoints** for managing strategies, orders, and trades
- **Celery integration** for asynchronous execution
- **Adapter layer** for platform-agnostic trading (e.g., MT5, mock, etc.)
- **Audit logging** and risk checks

---

## Setup

1. **Install dependencies**
   Make sure your Django project includes `trading` in `INSTALLED_APPS` and all requirements are installed.

   ```bash
   pip install -r requirements.txt
   ```

2. **Apply migrations**

   ```bash
   python manage.py makemigrations trading
   python manage.py migrate
   ```

3. **Configure environment variables**
   Ensure your `.env` or Django settings include:

   ```
   MT5_API_URL=http://mt5:5001
   ```

4. **Run Celery worker (for async tasks)**

   ```bash
   celery -A <your_project_name> worker -l info
   ```

---

## API Endpoints

All endpoints are prefixed with `/api/v1/trading/`.

### **Strategies**

- **List available strategies**
  ```
  GET /api/v1/trading/strategies/
  ```
  **Response:**
  ```json
  [
    {"name": "MeanReversion", "description": "Mean reversion strategy"},
    {"name": "Momentum", "description": "Momentum strategy"}
  ]
  ```

- **Run a strategy (backtest or live)**
  ```
  POST /api/v1/trading/strategies/run/
  ```
  **Body:**
  ```json
  {
    "strategy": "MeanReversion",
    "symbol": "EURUSD",
    "mode": "live",  // or "backtest"
    "params": {"window": 20, "num_std_dev": 2}
  }
  ```
  **Response:**
  ```json
  {"task_id": "abc123", "status": "started"}
  ```

### **Orders**

- **List orders**
  ```
  GET /api/v1/trading/orders/
  ```
- **Place an order**
  ```
  POST /api/v1/trading/orders/
  ```
  **Body:**
  ```json
  {
    "symbol": "EURUSD",
    "side": "buy",
    "qty": 1.0,
    "order_type": "market"
  }
  ```

### **Trades**

- **List trades**
  ```
  GET /api/v1/trading/trades/
  ```

---

## Usage Examples

### **Placing an Order via API**

```python
import requests

order = {
    "symbol": "EURUSD",
    "side": "buy",
    "qty": 1.0,
    "order_type": "market"
}
resp = requests.post("http://localhost:8000/api/v1/trading/orders/", json=order)
print(resp.json())
```

### **Running a Strategy**

```python
import requests

payload = {
    "strategy": "MeanReversion",
    "symbol": "EURUSD",
    "mode": "live",
    "params": {"window": 20, "num_std_dev": 2}
}
resp = requests.post("http://localhost:8000/api/v1/trading/strategies/run/", json=payload)
print(resp.json())
```

---

## Plugging in a New Strategy

1. **Create a new folder in `trading/strategies/` (e.g., `my_strategy/`).**
2. **Implement a `entry.py` with a `strategy_class` exposing the required interface:**

   ```python
   # trading/strategies/my_strategy/entry.py
   from trading.engine.strategy_base import Strategy

   class MyStrategy(Strategy):
       name = "MyStrategy"
       def on_init(self, context): ...
       def on_bar(self, bar, context): ...
       def on_tick(self, tick, context): ...

   strategy_class = MyStrategy
   ```

3. **Register or auto-discover the strategy in the engine.**

---

## Models

- **Order**: Tracks all submitted orders, their status, and payloads.
- **Trade**: Tracks all executed trades, linked to orders.
- **StrategyInstance**: (Optional) Tracks running/backtested strategy sessions.

---

## Celery Tasks

- **run_strategy_tick**: Executes a strategy tick (bar or tick event).
- **place_order_task**: Places an order asynchronously via the adapter.

---

## Adapter Pattern

Adapters are in `trading/adapters/` and implement a common interface for placing/canceling orders and querying positions. Example: `mt5_adapter.py` for MetaTrader 5.

---

## Testing

- Use Django's test framework for unit and integration tests.
- Backtest strategies using historical data and the same API.

---

## Contributing

1. Fork the repo and create a feature branch.
2. Add your strategy or adapter.
3. Write tests and documentation.
4. Submit a pull request.

---

## License

MIT License

---

For further details, see the code and docstrings in each module.