from django.contrib import admin
from unfold.admin import ModelAdmin
from app.trades.models import Trade, TradeClosePricesMutation

@admin.register(Trade)
class TradeAdmin(ModelAdmin):
    list_display = [field.name for field in Trade._meta.fields]
    list_filter = [field.name for field in Trade._meta.fields]
    search_fields = [field.name for field in Trade._meta.fields]

    ordering = ('-entry_time',)

@admin.register(TradeClosePricesMutation)
class TradeClosePricesMutationAdmin(ModelAdmin):
    list_display = [field.name for field in TradeClosePricesMutation._meta.fields]
    list_filter = [field.name for field in TradeClosePricesMutation._meta.fields]
    search_fields = [field.name for field in TradeClosePricesMutation._meta.fields]

    ordering = ('-mutation_time',)
