from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/chat/global/$', consumers.GlobalChatConsumer.as_asgi()),  # Global chat updates path
    re_path(r'ws/chat/$', consumers.ChatConsumer.as_asgi()),  # Base chat path
    re_path(r'ws/chat/(?P<conversation_id>\w+)/$', consumers.ChatConsumer.as_asgi()),  # Conversation-specific path
] 