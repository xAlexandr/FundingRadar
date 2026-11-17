"""
ASGI config for funding_web project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/asgi/
"""

import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "funding_web.settings")
django.setup()  # 👈 Добавьте это перед `get_asgi_application()`

from django.core.asgi import get_asgi_application
from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from trading.routing import websocket_urlpatterns

application = ProtocolTypeRouter({
    "http": get_asgi_application(),  # Обычные HTTP-запросы через Django
    "websocket": AuthMiddlewareStack(  # Аутентификация для WebSocket
        URLRouter(websocket_urlpatterns)
    ),
})