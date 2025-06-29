from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from channels.security.websocket import AllowedHostsOriginValidator
from django.core.asgi import get_asgi_application
from connections.routing import websocket_urlpatterns as connection_urlpatterns
from assistant.routing import websocket_urlpatterns as assistant_urlpatterns
from community.routing import websocket_urlpatterns as community_urlpatterns
from chat.routing import websocket_urlpatterns as chat_urlpatterns
from notifications.routing import websocket_urlpatterns as notification_urlpatterns

# Combine all websocket URL patterns
websocket_urlpatterns = (
    connection_urlpatterns + 
    assistant_urlpatterns + 
    community_urlpatterns + 
    chat_urlpatterns +
    notification_urlpatterns
)

application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": AllowedHostsOriginValidator(
        AuthMiddlewareStack(
            URLRouter(
                websocket_urlpatterns
            )
        )
    ),
}) 