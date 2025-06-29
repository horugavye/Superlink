from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/socket.io/$', consumers.ConnectionConsumer.as_asgi()),
] 