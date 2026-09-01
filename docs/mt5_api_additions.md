# mt5-api additions required by the D1 and D3b collectors

**Status:** specified, not implemented. WMPS is frozen bug-fix-only during Phases 0–2, and
`backend/mt5-api/app/main.py` is on the do-not-touch list, so this records exactly what the two
blocked collectors need rather than changing it.

As of WMPS `63d93f6` the service exposes `/`, `/api/v1/connect`, `/disconnect`, `/account`,
`/rates`, `/tick`, `/order/*`, `/position/*`, `/positions`, `/deals`. Neither endpoint below
exists, so `d1_contract_specs.py` and `d3b_spread_history.py` raise `EndpointMissing` and write a
`BLOCKED` artifact naming this file.

`d3a_spread_forward.py` needs **no** change — it runs on the existing `/api/v1/tick`.

---

## 1. `GET /api/v1/symbol_info` — required by D1

Wraps `MetaTrader5.symbol_info(symbol)`.

| Query param | Type | Default |
|---|---|---|
| `symbol` | str | `XAUUSD` |

Response must carry, at minimum, the fields D1 pins — the collector records any that are absent
rather than tolerating them silently:

```
contract_size  tick_size  tick_value
volume_min     volume_max volume_step
currency_profit currency_margin digits
trade_stops_level trade_freeze_level
filling_mode   swap_long  swap_short  swap_mode
```

Return the MT5 struct's fields as-is. Do **not** normalise, round, or substitute defaults for
missing values: a defaulted `tick_value` is indistinguishable downstream from a measured one, and
it is the term the entire position-size calculation rests on.

`filling_mode` is an integer bitmask; the collector tests bit 2 (`SYMBOL_FILLING_IOC`) to check
whether the codebase-wide IOC assumption generalises past XAUUSD.

## 2. `GET /api/v1/ticks` — required by D3b

Wraps `MetaTrader5.copy_ticks_range(symbol, date_from, date_to, COPY_TICKS_ALL)`.

| Query param | Type | Notes |
|---|---|---|
| `symbol` | str | |
| `date_from` | ISO-8601 UTC | |
| `date_to` | ISO-8601 UTC | |

Returns a list of `{time, bid, ask, last, volume, flags}`.

**Return what exists; never pad, and never silently narrow the window.** Broker tick retention
varies by symbol and twelve months may not be available. The collector computes obtained depth
from the returned timestamps and sets `depth_shortfall` — but it can only do that if the response
reflects the true extent. An endpoint that quietly clamps the request to what it can serve
converts a data limitation into a false cost estimate.

Tick ranges are large. A hard row cap with an explicit `truncated: true` flag in the response is
acceptable; silent truncation is not.

---

## Why these are specified rather than implemented

Writing the collectors before the terminal is up is deliberate. The session MT5 becomes available
is the session you want pulling data, not authoring the puller — and D3a in particular is the
highest-value MT5-dependent action available, since forward spread data only accumulates from the
day it is switched on.
