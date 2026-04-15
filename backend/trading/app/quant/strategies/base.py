import logging


class BaseStrategy:

    def __init__(self, environment: str = "prod"):
        """Initialize with required args and inputs."""

        self.environment: str = environment.lower()
        self.logger: object = self._create_logger()
        self.max_positions: int = 1
        self.open_positions: int = 0

    def _create_logger(self):
        """Create a logger object to capture output."""
        self.logger = logging.getLogger(self.__class__.__name__)

        return True

    def enter_trade(self, *args, **kwargs):
        """
        Analyse the entry condition(s).
        Returns True or False.
        """

        # Check number of open positions
        if self.open_positions >= self.max_positions:
            self.logger.warning(
                f"Cannot Enter Trade: Maximum Open Positions {self.open_positions}/{self.max_positions} ")      # noqa: E501
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
