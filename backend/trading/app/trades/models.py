from django.utils import timezone
from django.db import models


class Trade(models.Model):
    TRADE_DIRECTION_CHOICES = [
        ('BUY', 'Buy'),
        ('SELL', 'Sell'),
    ]

    CLOSING_REASON_CHOICES = [
        ('TP', 'Take Profit'),
        ('SL', 'Stop Loss'),
        ('MANUAL', 'Manual'),
        ('LIQUIDATION', 'Liquidation'),
        ('OTHER', 'Other'),
    ]

    MARKET_TYPE_CHOICES = [
        ('FOREX', 'Forex'),
        ('CRYPTO', 'Crypto'),
        ('OTHER', 'Other'),
    ]

    TIMEFRAME_CHOICES = [
        ('1M', '1 Minute'),
        ('5M', '5 Minutes'),
        ('15M', '15 Minutes'),
        ('1H', '1 Hour'),
        ('4H', '4 Hours'),
        ('1D', '1 Day'),
    ]

    # Core trade fields
    id = models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True)
    broker_id = models.CharField(max_length=100)  # Identifier on Broker System
    direction = models.CharField(max_length=4, choices=TRADE_DIRECTION_CHOICES)
    symbol = models.CharField(max_length=10)
    entry_time = models.DateTimeField(db_index=True, default=timezone.now, editable=False)
    entry_price = models.FloatField()
    exit_time = models.DateTimeField(null=True, blank=True)
    exit_price = models.FloatField(null=True, blank=True)
    exit_reason = models.CharField(
        max_length=50, null=True, blank=True, choices=CLOSING_REASON_CHOICES)
    order_volume = models.FloatField(null=True, blank=True)
    sl = models.FloatField(null=True, blank=True)
    tp = models.FloatField(null=True, blank=True)
    session = models.CharField(max_length=50)
    pnl = models.FloatField(null=True, blank=True)

    # Additional Info
    capital = models.FloatField()
    leverage = models.FloatField(default=500)
    strategy = models.CharField(max_length=50)
    broker = models.CharField(max_length=50)
    market_type = models.CharField(max_length=50, choices=MARKET_TYPE_CHOICES)
    timeframe = models.CharField(max_length=50, choices=TIMEFRAME_CHOICES)
    synched = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.direction} {self.symbol} at {self.entry_price}"


class TradeClosePricesMutation(models.Model):
    trade = models.ForeignKey(
        Trade, on_delete=models.CASCADE, related_name='close_prices_mutations')
    mutation_time = models.DateTimeField(auto_now_add=True)
    mutation_price = models.FloatField(null=True, blank=True)
    new_tp_price = models.FloatField(null=True, blank=True)
    new_sl_price = models.FloatField(null=True, blank=True)
    pnl_at_new_tp_price = models.FloatField(null=True, blank=True)
    pnl_at_new_sl_price = models.FloatField(null=True, blank=True)

    class Meta:
        ordering = ['mutation_time']
        verbose_name = "Trade Close Prices Mutation"
        verbose_name_plural = "Trade Close Prices Mutations"

    def __str__(self):
        return f"Mutation for {self.trade} at {self.mutation_time}"
