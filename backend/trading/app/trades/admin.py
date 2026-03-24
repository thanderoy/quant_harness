from django.contrib import admin
from unfold.admin import ModelAdmin
from app.trades.models import Trade, TradeClosePricesMutation


@admin.register(Trade)
class TradeAdmin(ModelAdmin):
    list_display = [
        "symbol", "direction", "entry_price", "entry_time",
        "exit_price", "exit_time", "pnl", "strategy", "synched",
    ]
    list_filter = [
        "direction", "symbol", "strategy", "synched",
        "market_type", "exit_reason", "session",
    ]
    search_fields = [
        "broker_id", "symbol", "direction", "strategy", "broker", "session",
    ]

    ordering = ('-entry_time',)


@admin.register(TradeClosePricesMutation)
class TradeClosePricesMutationAdmin(ModelAdmin):
    list_display = [
        "trade", "mutation_time", "mutation_price",
        "new_tp_price", "new_sl_price",
    ]
    list_filter = ["mutation_time"]
    search_fields = ["trade__symbol", "trade__broker_id"]

    ordering = ('-mutation_time',)
