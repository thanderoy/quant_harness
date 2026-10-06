from django.urls import path, include
from rest_framework.routers import DefaultRouter
from app.trades.views import TradeViewSet

router = DefaultRouter()
router.register(r"trades", TradeViewSet)

urlpatterns = [
    path("", include(router.urls)),
]
