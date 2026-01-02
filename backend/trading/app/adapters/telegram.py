import asyncio
import logging
from app.config import settings
from telethon import TelegramClient, events

class TelegramAPIClient:
    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
        # Use a persistent path for the session file. Avoid re-login prompts on container restarts.
        # Ensure this path matches the volume mounted or directory created in Dockerfile
        self.API_SESSION_NAME = '/app/session/telegram_session'

        # Initialize client but DON'T start it yet
        self.client = TelegramClient(
            self.API_SESSION_NAME,
            settings.TELEGRAM_API_ID,
            settings.TELEGRAM_API_HASH
        )

        # We initialize the queue as None and create it inside the loop
        self.message_queue: asyncio.Queue = None
        self.TARGET_CHANNEL = settings.TELEGRAM_API_TARGET_CHANNEL

    async def get_queue(self) -> asyncio.Queue:
        """Ensure the queue is created on the correct running loop."""
        if self.message_queue is None:
            self.message_queue = asyncio.Queue()
        return self.message_queue

    def _serialize_message(self, message: object) -> dict:
        if not message:
            return {}
        return {
            "message_id": message.id,
            "chat_id": str(message.chat_id),
            "content": message.raw_text,
            "sender_id": str(message.sender_id),
            "timestamp": message.date.isoformat(),
        }

    async def _queue_new_signal(self, event: events.NewMessage.Event):
        """Event handler for new messages."""
        self.logger.info(f"Received message: \n{event.message}")
        serialized = self._serialize_message(event.message)
        if serialized:
            queue = await self.get_queue()
            await queue.put(serialized)
            self.logger.info("New message queued.")

    async def start_client(self):
        """Standardized way to ensure client is connected."""
        if not self.client.is_connected():
            await self.client.start()

    async def send_message(self, message: str, channel: str = None):
        """
        Send a message to a telegram channel.
        Falls back to TELEGRAM_API_RESULTS_CHANNEL if channel is not provided.
        """
        await self.start_client()
        target_channel = channel or settings.TELEGRAM_API_RESULTS_CHANNEL

        try:
            await self.client.send_message(target_channel, message)
            self.logger.info(f"Message sent to {target_channel}")
        except Exception as e:
            self.logger.error(f"Failed to send message to {target_channel}: {e}")

    async def stream_signals(self, channel=None):
        """
        The proper async way to stream.
        Run this with: asyncio.run(client.stream_signals())
        """
        await self.start_client()
        channel = channel or self.TARGET_CHANNEL

        # Register the handler
        self.client.add_event_handler(
            self._queue_new_signal,
            events.NewMessage(chats=channel)
        )

        self.logger.info(f"Streaming from {channel}...")
        try:
            await self.client.run_until_disconnected()
        finally:
            await self.client.disconnect()