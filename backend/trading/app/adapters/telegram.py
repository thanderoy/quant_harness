"""Telegram API Interactions."""
import asyncio
import logging
from typing import AsyncIterator
from app.config import settings
from telethon import TelegramClient, events


class TelegramAPIClient:

    def __init__(self):
        """Initialize Client"""

        self.logger: logging.Logger = self._create_logger()
        self.API_ID: int = settings.TELEGRAM_API_ID
        self.API_HASH: str = settings.TELEGRAM_API_HASH     # noqa: E501
        self.API_SESSION_NAME: str = '/tmp/telegram_client_logs'
        self.TARGET_CHANNEL: str = settings.TELEGRAM_API_TARGET_CHANNEL  # noqa: E501

        self.client = TelegramClient(
            self.API_SESSION_NAME, self.API_ID, self.API_HASH)

        self.message_queue: asyncio.Queue = asyncio.Queue()

    def _create_logger(self) -> logging.Logger:
        """Create a logger object to capture output."""
        logging.basicConfig(
            level=logging.INFO, format='%(asctime)s [%(levelname)s] > %(message)s')     # noqa: E501

        return logging.getLogger(self.__class__.__name__)

    def _serialize_message(self, message: object) -> dict:
        """Serialize message object"""
        if not message.text:
            return {}

        return {
            "message_id": message.id,
            "chat_id": str(message.chat_id),
            "content": message.raw_text,
            "sender_id": str(message.sender_id),
            "timestamp": message.date.isoformat(),
        }

    async def _queue_new_signal(self, event: object):
        """Add new messages to the asyncio.Queue object for consumer."""
        message = event.message

        serialized_message = self._serialize_message(message)

        if not serialized_message:
            self.logger.warning("Skipping non-text message.")
            return

        await self.message_queue.put(serialized_message)
        self.logger.info("New signal received. Added to queue.")
        self.logger.debug(f"Current queue size: {self.message_queue.qsize()}")

    async def fetch_signals(self, limit: int = 3) -> AsyncIterator:
        """
        Fetch historical messages ordered in descending order.

        :param limit (int): How far back to fetch messages.
        :returns (AsyncIterator): Signals data.
        """
        self.logger.debug(
            f"Fetching last {limit} messages from {self.TARGET_CHANNEL}...")

        async with self.client:
            async for message in self.client.iter_messages(
                    self.TARGET_CHANNEL, limit=limit):

                # Check if message is empty
                if not message.text:
                    continue

                yield self._serialize_message(message)

        self.logger.debug(
            f"Fetched {limit} messages from {self.TARGET_CHANNEL}.")

    def stream_signals(self):
        """
        Stream realtime messages from TARGET CHANNEL.

        :returns (dict): Signals data.
        """
        # Set up a new event loop for this thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        self.client.add_event_handler(
            self._queue_new_signal, events.NewMessage(chats=self.TARGET_CHANNEL))  # noqa: E501

        with self.client:
            self.logger.info(
                f"Streaming messages from {self.TARGET_CHANNEL}...")
            self.client.run_until_disconnected()    # Runs forever
            self.logger.info("Streaming paused. Client Disconnected.")
