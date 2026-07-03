import logging

from app.quant.strategies.logging_utils import get_strategy_logger


class BaseStrategy:
    # Short bracketed code prepended to every log record (e.g. "ASQ" -> [ASQ]).
    # Subclasses should override this; falls back to the class name otherwise.
    SHORT_NAME: str = ""

    def __init__(self, environment: str = "test"):
        """Initialize with required args and inputs."""

        self.environment: str = environment.lower()
        self.logger: logging.LoggerAdapter = self._create_logger()
        self.max_positions: int = 1
        self.open_positions: int = 0

    def _create_logger(self) -> logging.LoggerAdapter:
        """Create a short-name-prefixed logger to capture output."""
        short_name = self.SHORT_NAME or self.__class__.__name__
        return get_strategy_logger(self.__class__.__name__, short_name)

    def enter_trade(self, *args, **kwargs):
        """
        Analyse the entry condition(s).
        Returns True or False.
        """

        # Check number of open positions
        if self.open_positions >= self.max_positions:
            self.logger.warning(
                f"Cannot Enter Trade: Maximum Open Positions {self.open_positions}/{self.max_positions} "
            )  # noqa: E501
            return False

        # IMPLEMENT YOUR TRADE ENTRY LOGIC HERE .....

    def exit_trade(self, *args, **kwargs):
        """
        Analyse the exit condition(s).
        Returns True or False.
        """

        # Check for any open positions
        if self.open_positions == 0:
            self.logger.info("Cannot Exit Trade: No Open Positions")
            return False

        # IMPLEMENT YOUR TRADE EXIT LOGIC HERE .....
