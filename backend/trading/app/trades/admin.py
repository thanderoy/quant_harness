from django.contrib import admin
from app.trades.models import Trade, TradeClosePricesMutation


@admin.register(Trade)
class TradeAdmin(admin.ModelAdmin):
    list_display = [
        "symbol", "direction", "entry_price", "entry_time",
        "exit_price", "exit_time", "pnl", "strategy", "status", "synched",
    ]
    list_filter = [
        "direction", "symbol", "strategy", "status", "synched",
        "market_type", "exit_reason", "session",
    ]
    search_fields = [
        "broker_id", "symbol", "direction", "strategy", "session",
    ]

    ordering = ('-entry_time',)


@admin.register(TradeClosePricesMutation)
class TradeClosePricesMutationAdmin(admin.ModelAdmin):
    list_display = [
        "trade", "mutation_time", "mutation_price",
        "new_tp_price", "new_sl_price",
    ]
    list_filter = ["mutation_time"]
    search_fields = ["trade__symbol", "trade__broker_id"]

    ordering = ('-mutation_time',)
