import os
import logging
import asyncio
from typing import Set
import urllib.parse
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'superlink.settings')

import django
django.setup()

from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from channels.security.websocket import AllowedHostsOriginValidator
from connections.routing import websocket_urlpatterns as connection_urlpatterns
from chat.routing import websocket_urlpatterns as chat_urlpatterns
from notifications.routing import websocket_urlpatterns as notification_urlpatterns
from community.routing import websocket_urlpatterns as community_urlpatterns
from assistant.routing import websocket_urlpatterns as assistant_urlpatterns
from channels.middleware import BaseMiddleware
from channels.exceptions import DenyConnection
from urllib.parse import parse_qs
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.tokens import AccessToken
from django.contrib.auth import get_user_model
from channels.db import database_sync_to_async
import signal
import sys
import threading
from django.core.signals import request_started, request_finished
from django.dispatch import receiver
from django.contrib.staticfiles.handlers import ASGIStaticFilesHandler
from asgiref.sync import sync_to_async
from functools import partial
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)
User = get_user_model()

# Track active connections and shutdown state
active_connections = set()
is_shutting_down = False
shutdown_event = threading.Event()
executor = ThreadPoolExecutor(max_workers=4)

def handle_shutdown(signum, frame):
    """Handle graceful shutdown of the application"""
    global is_shutting_down
    if is_shutting_down:
        return
    
    logger.info("Received shutdown signal. Starting graceful shutdown...")
    is_shutting_down = True
    shutdown_event.set()
    
    # Close all active WebSocket connections
    for task in active_connections:
        if not task.done():
            task.cancel()
    
    # Wait for connections to close (with increased timeout)
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Create a future to wait for shutdown
            shutdown_future = asyncio.Future()
            
            async def wait_for_shutdown():
                try:
                    await asyncio.wait_for(
                        asyncio.gather(*active_connections, return_exceptions=True),
                        timeout=15.0  # Increased timeout
                    )
                except asyncio.TimeoutError:
                    logger.warning("Timeout waiting for connections to close")
                finally:
                    shutdown_future.set_result(None)
            
            # Run the shutdown in the background
            asyncio.create_task(wait_for_shutdown())
            
            # Wait for shutdown to complete
            loop.run_until_complete(shutdown_future)
        else:
            loop.run_until_complete(
                asyncio.wait_for(
                    asyncio.gather(*active_connections, return_exceptions=True),
                    timeout=15.0  # Increased timeout
                )
            )
    except asyncio.TimeoutError:
        logger.warning("Timeout waiting for connections to close")
    except Exception as e:
        logger.error(f"Error during shutdown: {e}")
    
    # Shutdown the thread pool executor
    executor.shutdown(wait=True)
    
    logger.info("Graceful shutdown complete")
    sys.exit(0)

def init_signals():
    """Initialize signal handlers in the main thread"""
    if threading.current_thread() is threading.main_thread():
        try:
            signal.signal(signal.SIGTERM, handle_shutdown)
            signal.signal(signal.SIGINT, handle_shutdown)
            logger.info("Signal handlers initialized in main thread")
        except ValueError as e:
            logger.warning(f"Could not initialize signal handlers: {e}")
    else:
        logger.info("Signal handlers will be initialized in main thread")

# Initialize signals when the module is imported
init_signals()

class ShutdownMiddleware(BaseMiddleware):
    def __init__(self, application):
        super().__init__(application)
        self.application = application

    async def __call__(self, scope, receive, send):
        if is_shutting_down:
            logger.warning("Rejecting new connection during shutdown")
            if scope["type"] == "websocket":
                await send({
                    "type": "websocket.close",
                    "code": 1012,  # Service Restart
                    "reason": "Server is shutting down"
                })
            return None
        return await self.application(scope, receive, send)

class TokenAuthMiddleware(BaseMiddleware):
    def __init__(self, application):
        super().__init__(application)
        self.application = application
        self._loop = None
        self._task = None

    async def __call__(self, scope, receive, send):
        if is_shutting_down:
            logger.warning("Rejecting new connection during shutdown")
            if scope["type"] == "websocket":
                await send({
                    "type": "websocket.close",
                    "code": 1012,  # Service Restart
                    "reason": "Server is shutting down"
                })
            return None

        try:
            if scope["type"] == "websocket":
                # Create a task for this connection
                self._task = asyncio.current_task()
                active_connections.add(self._task)
                
                try:
                    # Get token from query string
                    query_string = scope["query_string"].decode()
                    token = None
                    for param in query_string.split('&'):
                        if param.startswith('token='):
                            token = param.split('=')[1]
                            token = urllib.parse.unquote(token)
                            break

                    if not token:
                        logger.error("No token found in query string")
                        await send({
                            "type": "websocket.close",
                            "code": 1008,  # Policy violation
                            "reason": "No token provided"
                        })
                        return None

                    logger.info(f"Attempting to validate token: {token[:20]}...")
                    
                    # Validate token and get user
                    try:
                        if self._loop is None:
                            self._loop = asyncio.get_running_loop()
                        
                        # Use the thread pool executor for token validation
                        user = await self._loop.run_in_executor(
                            executor,
                            self.get_user_from_token,
                            token
                        )
                        
                        if not user:
                            logger.error("Token validation failed - no user found")
                            await send({
                                "type": "websocket.close",
                                "code": 1008,  # Policy violation
                                "reason": "Invalid token"
                            })
                            return None
                        
                        logger.info(f"Token validated successfully for user: {user.username}")
                        scope["user"] = user
                        
                    except asyncio.CancelledError:
                        logger.warning("Token validation cancelled during shutdown")
                        return None
                    except Exception as e:
                        logger.error(f"Token validation error: {str(e)}", exc_info=True)
                        await send({
                            "type": "websocket.close",
                            "code": 1008,  # Policy violation
                            "reason": "Token validation failed"
                        })
                        return None

                    return await self.application(scope, receive, send)
                finally:
                    # Remove task from active connections when done
                    if self._task in active_connections:
                        active_connections.remove(self._task)
            
            return await self.application(scope, receive, send)
        except Exception as e:
            logger.error(f"Error in TokenAuthMiddleware: {str(e)}", exc_info=True)
            if scope["type"] == "websocket":
                await send({
                    "type": "websocket.close",
                    "code": 1011,  # Internal error
                    "reason": "Internal server error"
                })
            return None

    def get_user_from_token(self, token):
        try:
            access_token = AccessToken(token)
            user_id = access_token['user_id']
            return User.objects.get(id=user_id)
        except Exception as e:
            logger.error(f"Error getting user from token: {str(e)}")
            return None

# Combine all websocket URL patterns
websocket_urlpatterns = (
    connection_urlpatterns + 
    assistant_urlpatterns + 
    community_urlpatterns + 
    chat_urlpatterns +
    notification_urlpatterns
)

# Create the ASGI application
application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": AllowedHostsOriginValidator(
        ShutdownMiddleware(
            TokenAuthMiddleware(
                URLRouter(
                    websocket_urlpatterns
                )
            )
        )
    ),
})

# Wrap the application with ASGIStaticFilesHandler and add error handling
application = ASGIStaticFilesHandler(application)
