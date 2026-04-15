import uuid
from django.utils import timezone
from django.db import models


ENVIRONMENT_CHOICES = [
    ('PROD', 'Production'),
    ('TEST', 'Test'),
]


class Account(models.Model):
    id = models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True)
    login = models.BigIntegerField(db_index=True)
    name = models.CharField(max_length=255)
    server = models.CharField(max_length=255)
    currency = models.CharField(max_length=10)
    trade_mode = models.IntegerField()
    environment = models.CharField(
        max_length=4, choices=ENVIRONMENT_CHOICES, default='PROD',
    )

    class Meta:
        unique_together = ('login', 'environment')

    @property
    def latest_snapshot(self):
        return self.snapshots.order_by('-date').first()

    def __str__(self):
        return f"{self.login} - {self.name}"


class AccountSnapshot(models.Model):
    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name='snapshots')
    date = models.DateField()
    balance = models.FloatField()
    equity = models.FloatField()
    margin = models.FloatField()
    margin_free = models.FloatField()
    margin_level = models.FloatField()
    leverage = models.IntegerField()
    profit = models.FloatField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('account', 'date')
        ordering = ['-date']

    def __str__(self):
        return f"Snapshot {self.account.login} on {self.date}"


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
        ('REJECTED', 'Rejected'),
        ('CANCELED', 'Canceled'),
        ('EXPIRED', 'Expired'),
        ('OTHER', 'Other'),
    ]

    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('FILLED', 'Filled'),
        ('REJECTED', 'Rejected'),
        ('CANCELED', 'Canceled'),
        ('EXPIRED', 'Expired'),
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
    session = models.CharField(max_length=50, null=True, blank=True)
    pnl = models.FloatField(null=True, blank=True)

    # Additional Info
    account = models.ForeignKey(Account, on_delete=models.SET_NULL, null=True, blank=True, related_name='trades')
    strategy = models.CharField(max_length=50)
    market_type = models.CharField(max_length=50, choices=MARKET_TYPE_CHOICES)
    timeframe = models.CharField(max_length=50, choices=TIMEFRAME_CHOICES)
    status = models.CharField(
        max_length=10, choices=STATUS_CHOICES, default='PENDING',
    )
    environment = models.CharField(
        max_length=4, choices=ENVIRONMENT_CHOICES, default='PROD',
        db_index=True,
    )
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
