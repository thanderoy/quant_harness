from django.db.models import Sum
from app.trades.models import Trade
import os


def environment_callback(request):
    """Return the environment name for the Unfold admin header badge."""
    if os.getenv('DJANGO_DEBUG', 'False').lower() == 'true':
        return ["Development", "warning"]
    return ["Production", "danger"]

def dashboard_callback(request, context):
    trades = Trade.objects.all()

    # KPIs
    total_pnl = trades.aggregate(Sum('pnl'))['pnl__sum'] or 0.0
    active_trades_count = trades.filter(exit_time__isnull=True).count()
    total_capital = trades.aggregate(Sum('capital'))['capital__sum'] or 0.0

    # Win Rate
    closed_trades = trades.filter(exit_time__isnull=False)
    closed_count = closed_trades.count()
    winning_trades = closed_trades.filter(pnl__gt=0).count()
    win_rate = (winning_trades / closed_count * 100) if closed_count > 0 else 0.0

    # PnL by Symbol
    pnl_by_symbol = list(closed_trades.values('symbol').annotate(total=Sum('pnl')).order_by('-total'))

    context.update({
        "total_pnl": total_pnl,
        "active_trades_count": active_trades_count,
        "total_capital": total_capital,
        "win_rate": round(win_rate, 2),
        "pnl_by_symbol": pnl_by_symbol,
        "closed_trades_count": closed_count
    })
    return context
