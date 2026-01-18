from rest_framework import viewsets
from rest_framework.response import Response
from app.trades.models import Trade
from app.trades.serializers import TradeSerializer
from app.trades.filters import TradeFilter


class TradeViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Trade.objects.all()
    serializer_class = TradeSerializer
    filterset_class = TradeFilter
    ordering_fields = ['entry_time', 'exit_time', 'pnl', 'symbol']
    ordering = ['-entry_time']  # default ordering

    def get_queryset(self):
        # Ensure we prefetch the related mutations to avoid N+1 queries
        return Trade.objects.prefetch_related('close_prices_mutations').all()
