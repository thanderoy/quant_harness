import asyncio
import logging
from celery import shared_task
from app.quant.strategies.forexero.strategy import ForexeroStrategy
from app.adapters.telegram import TelegramAPIClient

LOGGER = logging.getLogger(__name__)


@shared_task(bind=True, name="app.quant.strategies.forexero.tasks.execute_forexero_trade")
def execute_forexero_trade(self, signal_data: dict, environment: str = "prod"):
    """
    Celery task to process a single Forexero signal.
    """
    try:
        LOGGER.info(f"Processing signal: {signal_data}")
        strategy = ForexeroStrategy(environment=environment)
        strategy.process_signal(signal_data)
    except Exception as e:
        LOGGER.exception(f"Error processing signal in task: {e}")
        raise self.retry(exc=e)


@shared_task(bind=True, name="app.quant.strategies.forexero.tasks.run_forexero_listener")
def run_forexero_listener(self, channel=None, environment: str = "prod"):
    """
    Long-running Celery task that listens to Telegram signals
    and dispatches execution tasks.
    """
    LOGGER.info("Starting Forexero listener task...")
    
    async def main():
        client = TelegramAPIClient()

        async def _celery_event_handler(event):
            """
            Custom handler that serializes the message and triggers
            the execution task.
            """
            try:
                # Re-use the existing serialization logic
                serialized = client.serialize_message(event.message)
                if serialized:
                    LOGGER.info(f"Dispatching task for message {serialized.get('message_id')}")
                    execute_forexero_trade.delay(serialized, environment=environment)
            except Exception as e:
                LOGGER.error(f"Error in listener event handler: {e}")

        await client.stream_signals(channel=channel, event_handler=_celery_event_handler)

    try:
        # Run the async stream with our custom handler
        asyncio.run(main())
    except Exception as e:
        LOGGER.exception(f"Forexero listener task failed: {e}")
        # We might want to restart this task if it crashes
        raise e
