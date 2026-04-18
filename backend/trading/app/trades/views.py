from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status as drf_status

from app.adapters.mt5_api import MT5APIClient, APIError
from app.config import settings
from app.trades.models import Trade, TradeClosePricesMutation
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

    @action(detail=True, methods=['post'])
    def modify(self, request, pk=None):
        """Modify the SL and/or TP of an open position on MT5 and record the mutation."""
        trade = self.get_object()
        sl = request.data.get('sl')
        tp = request.data.get('tp')

        if sl is None and tp is None:
            return Response(
                {'detail': 'At least one of sl or tp must be provided.'},
                status=drf_status.HTTP_400_BAD_REQUEST,
            )

        sl_value = float(sl) if sl is not None else None
        tp_value = float(tp) if tp is not None else None

        mt5_url = settings.get_mt5_url(trade.environment)
        mt5_client = MT5APIClient(base_url=mt5_url)
        try:
            result = mt5_client.modify_position(
                int(trade.broker_id),
                sl=sl_value,
                tp=tp_value,
            )
        except APIError as e:
            return Response({'detail': str(e)}, status=drf_status.HTTP_502_BAD_GATEWAY)
        finally:
            mt5_client.close()

        if not result.get('success'):
            return Response(
                {'detail': result.get('comment', 'Modification failed'), 'mt5_response': result},
                status=drf_status.HTTP_400_BAD_REQUEST,
            )

        update_fields = []
        if sl_value is not None:
            trade.sl = sl_value
            update_fields.append('sl')
        if tp_value is not None:
            trade.tp = tp_value
            update_fields.append('tp')
        trade.save(update_fields=update_fields)

        TradeClosePricesMutation.objects.create(
            trade=trade,
            new_sl_price=sl_value,
            new_tp_price=tp_value,
        )

        serializer = self.get_serializer(trade)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def close(self, request, pk=None):
        """Close an open position on MT5 and record the exit on the Trade."""
        trade = self.get_object()

        if trade.exit_time is not None:
            return Response(
                {'detail': 'Trade is already closed.'},
                status=drf_status.HTTP_400_BAD_REQUEST,
            )

        exit_reason = request.data.get('exit_reason', 'MANUAL')
        volume = request.data.get('volume')

        valid_reasons = [c[0] for c in Trade.CLOSING_REASON_CHOICES]
        if exit_reason not in valid_reasons:
            return Response(
                {'detail': f'Invalid exit_reason. Choices: {valid_reasons}'},
                status=drf_status.HTTP_400_BAD_REQUEST,
            )

        mt5_url = settings.get_mt5_url(trade.environment)
        mt5_client = MT5APIClient(base_url=mt5_url)
        try:
            result = mt5_client.close_position(
                int(trade.broker_id),
                volume=float(volume) if volume is not None else None,
            )
        except APIError as e:
            return Response({'detail': str(e)}, status=drf_status.HTTP_502_BAD_GATEWAY)
        finally:
            mt5_client.close()

        if not result.get('success'):
            return Response(
                {'detail': result.get('comment', 'Close failed'), 'mt5_response': result},
                status=drf_status.HTTP_400_BAD_REQUEST,
            )

        trade.exit_time = timezone.now()
        trade.exit_price = result.get('price')
        trade.exit_reason = exit_reason
        trade.save(update_fields=['exit_time', 'exit_price', 'exit_reason'])

        serializer = self.get_serializer(trade)
        return Response(serializer.data)
