import json
import logging
import urllib.parse
import time
import asyncio
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from rest_framework_simplejwt.tokens import AccessToken
from django.contrib.auth import get_user_model
from .models import Notification
from .serializers import NotificationSerializer
from asgiref.sync import sync_to_async

# Configure logging
logger = logging.getLogger(__name__)
# Create a file handler for notifications
notification_handler = logging.FileHandler('notification_debug.log')
notification_handler.setLevel(logging.DEBUG)
# Create a formatter
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
notification_handler.setFormatter(formatter)
# Add the handler to the logger
logger.addHandler(notification_handler)

User = get_user_model()

class NotificationConsumer(AsyncWebsocketConsumer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = None
        self.room_group_name = None
        self.token_validation_timeout = 5  # 5 seconds timeout for token validation
        logger.debug("[Init] NotificationConsumer initialized")

    @database_sync_to_async
    def get_user_from_token(self, token):
        try:
            logger.debug(f"[Token Validation] Starting token validation process")
            logger.debug(f"[Token Validation] Token length: {len(token) if token else 0}")
            
            # Decode the token
            access_token = AccessToken(token)
            user_id = access_token['user_id']
            logger.debug(f"[Token Validation] Token decoded successfully, user_id: {user_id}")
            
            # Get the user
            user = User.objects.get(id=user_id)
            logger.debug(f"[Token Validation] User found: {user.username} (ID: {user.id})")
            return user
        except Exception as e:
            logger.error(f"[Token Validation] Error validating token: {str(e)}", exc_info=True)
            return None

    @database_sync_to_async
    def get_missed_notifications(self):
        """Get unread notifications from the last 24 hours"""
        try:
            from django.utils import timezone
            from datetime import timedelta
            
            # Get unread notifications from the last 24 hours
            notifications = Notification.objects.filter(
                recipient=self.user,
                is_read=False,
                created_at__gte=timezone.now() - timedelta(hours=24)
            ).order_by('-created_at')
            
            logger.debug(f"[Missed Notifications] Found {notifications.count()} unread notifications")
            
            # Serialize notifications
            serializer = NotificationSerializer(notifications, many=True)
            serialized_data = serializer.data
            logger.debug(f"[Missed Notifications] Serialized data: {serialized_data}")
            return serialized_data
        except Exception as e:
            logger.error(f"[Missed Notifications] Error getting missed notifications: {str(e)}", exc_info=True)
            return []

    async def connect(self):
        try:
            logger.debug("[Connect] WebSocket connection attempt started")
            logger.debug(f"[Connect] Scope: {self.scope}")
            
            # Get token from query string
            query_string = self.scope['query_string'].decode()
            logger.debug(f"[Connect] Query string: {query_string}")
            
            token = None
            for param in query_string.split('&'):
                if param.startswith('token='):
                    token = param.split('=')[1]
                    token = urllib.parse.unquote(token)
                    break

            if not token:
                logger.error("[Connect] No token found in query string")
                await self.close(code=1008)  # Policy violation
                return

            logger.debug("[Connect] Token found, starting validation")

            # Validate token with timeout
            try:
                self.user = await asyncio.wait_for(
                    self.get_user_from_token(token),
                    timeout=self.token_validation_timeout
                )
            except asyncio.TimeoutError:
                logger.error("[Connect] Token validation timed out")
                await self.close(code=1008)
                return

            if not self.user:
                logger.error("[Connect] Token validation failed - no user found")
                await self.close(code=1008)
                return

            logger.debug(f"[Connect] Token validated for user {self.user.id}")

            # Accept the connection first to prevent timeout
            await self.accept()
            logger.debug("[Connect] WebSocket connection accepted")
            
            # Set up room group
            self.room_group_name = f"notifications_{self.user.id}"
            await self.channel_layer.group_add(
                self.room_group_name,
                self.channel_name
            )
            logger.debug(f"[Connect] Added to room group: {self.room_group_name}")
            
            # Send success message
            await self.send(text_data=json.dumps({
                'type': 'connection_established',
                'message': 'Successfully connected to notifications'
            }))
            logger.debug("[Connect] Sent connection established message")
            
            # Get missed notifications
            missed_notifications = await self.get_missed_notifications()
            if missed_notifications:
                logger.debug(f"[Connect] Sending {len(missed_notifications)} missed notifications")
                for notification in missed_notifications:
                    await self.notification_message({
                        'data': notification
                    })
            
            logger.debug(f"[Connect] Connection process completed successfully for user {self.user.id}")
            
        except Exception as e:
            logger.error(f"[Connect] Unexpected error during WebSocket connection: {str(e)}", exc_info=True)
            await self.close(code=1011)  # Internal error
            return

    async def disconnect(self, close_code):
        try:
            logger.debug(f"[Disconnect] WebSocket disconnection started. Close code: {close_code}")
            if self.room_group_name:
                logger.debug(f"[Disconnect] User {self.user.id if self.user else 'unknown'} disconnecting from room {self.room_group_name}")
                # Leave room group
                await self.channel_layer.group_discard(
                    self.room_group_name,
                    self.channel_name
                )
                logger.debug(f"[Disconnect] Successfully left room group: {self.room_group_name}")
            else:
                logger.warning("[Disconnect] No room group name found during disconnect")
        except Exception as e:
            logger.error(f"[Disconnect] Error during disconnect: {str(e)}", exc_info=True)

    async def receive(self, text_data):
        try:
            logger.debug(f"[Receive] Received WebSocket message: {text_data}")
            data = json.loads(text_data)
            logger.debug(f"[Receive] Parsed message data: {data}")
            
            if data.get('type') == 'ping':
                logger.debug("[Receive] Received ping message, sending pong response")
                # Send pong response
                await self.send(text_data=json.dumps({
                    'type': 'pong',
                    'timestamp': time.time()
                }))
                logger.debug("[Receive] Pong response sent")
                return
                
            if data.get('type') == 'request_missed_notifications':
                logger.debug("[Receive] Received request for missed notifications")
                # Get unread notifications from the last 24 hours
                notifications = await self.get_missed_notifications()
                if notifications:
                    logger.debug(f"[Receive] Sending {len(notifications)} missed notifications")
                    for notification in notifications:
                        logger.debug(f"[Receive] Sending missed notification: {notification}")
                        await self.notification_message({
                            'data': notification
                        })
                return
                
            logger.debug("[Receive] Message processing completed")
        except json.JSONDecodeError as e:
            logger.error(f"[Receive] Error decoding message: {str(e)}", exc_info=True)
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Invalid message format'
            }))
        except Exception as e:
            logger.error(f"[Receive] Unexpected error processing message: {str(e)}", exc_info=True)

    async def notification_message(self, event):
        try:
            logger.debug(f"[Notification] Starting to process notification for user {self.user.id}")
            logger.debug(f"[Notification] Event data: {event}")
            
            # Send notification to WebSocket
            logger.debug(f"[Notification] Preparing to send notification to user {self.user.id}")
            # Ensure the message format is consistent
            message = {
                'type': 'notification_message',
                'data': event['data']
            }
            logger.debug(f"[Notification] Formatted message: {message}")
            
            await self.send(text_data=json.dumps(message))
            logger.debug(f"[Notification] Successfully sent notification to user {self.user.id}")
        except Exception as e:
            logger.error(f"[Notification] Error sending notification: {str(e)}", exc_info=True)
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Error sending notification'
            })) 