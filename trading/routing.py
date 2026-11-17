from django.urls import re_path
from trading.consumers import MonitorConsumer

websocket_urlpatterns = [
    re_path(r'ws/monitor/$', MonitorConsumer.as_asgi()),  # WebSocket путь
]