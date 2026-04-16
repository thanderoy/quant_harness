from django_filters import rest_framework as filters
from app.trades.models import Trade

class TradeFilter(filters.FilterSet):
    # Time range filters
    entry_time_after = filters.DateTimeFilter(field_name='entry_time', lookup_expr='gte')
    entry_time_before = filters.DateTimeFilter(field_name='entry_time', lookup_expr='lte')
    exit_time_after = filters.DateTimeFilter(field_name='exit_time', lookup_expr='gte')
    exit_time_before = filters.DateTimeFilter(field_name='exit_time', lookup_expr='lte')
    
    # Numeric range filters
    pnl_min = filters.NumberFilter(field_name='pnl', lookup_expr='gte')
    pnl_max = filters.NumberFilter(field_name='pnl', lookup_expr='lte')
    
    # Symbol filters
    symbol = filters.CharFilter(lookup_expr='iexact')
    symbols = filters.BaseInFilter(field_name='symbol', lookup_expr='in')
    
    # Trade direction filter
    direction = filters.CharFilter(lookup_expr='iexact')
    
    # Status filters
    is_open = filters.BooleanFilter(field_name='exit_time', lookup_expr='isnull')

    # Environment filter
    environment = filters.CharFilter(lookup_expr='iexact')

    class Meta:
        model = Trade
        fields = {
            'synched': ['exact'],
            'status': ['exact', 'in'],
            'market_type': ['exact'],
            'exit_reason': ['exact', 'icontains'],
            'environment': ['exact'],
        }