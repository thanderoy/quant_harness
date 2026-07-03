"""Shared logging helpers for strategy modules.

Every strategy tags its log records with a short bracketed code (e.g. ``[ASQ]``)
so the different strategies are trivially greppable in the shared Loki/Grafana
stream. The tag is applied once, at logger construction, via a
:class:`logging.LoggerAdapter` — individual call sites never repeat it.
"""

import logging


class StrategyLogPrefixAdapter(logging.LoggerAdapter):
    """LoggerAdapter that prepends ``[SHORT] `` to every log message."""

    def process(self, msg: str, kwargs: dict) -> tuple[str, dict]:
        return f"[{self.extra['short_name']}] {msg}", kwargs


def get_strategy_logger(name: str, short_name: str) -> logging.LoggerAdapter:
    """Return a logger for ``name`` whose records are prefixed ``[short_name]``.

    Use one per strategy module (``strategy.py`` and ``tasks.py``) in place of
    ``logging.getLogger(__name__)``.
    """
    return StrategyLogPrefixAdapter(
        logging.getLogger(name), {"short_name": short_name}
    )
