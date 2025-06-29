import json
import base64
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from .models import Message, Conversation, MessageReaction, MessageThread, File, ConversationMember
from .serializers import MessageSerializer, MessageReactionSerializer
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
import logging
import time
from datetime import datetime, timedelta
import traceback
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync, sync_to_async
import urllib.parse
import asyncio
from rest_framework_simplejwt.tokens import AccessToken
import tempfile
import os
from django.db import models
import jwt
from django.conf import settings
from django.utils import timezone
import uuid
from stories.models import Story

# Add color codes for logging
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    MAGENTA = '\033[35m'
    YELLOW = '\033[33m'

# Custom formatter for colored logs
class ColoredFormatter(logging.Formatter):
    def format(self, record):
        if record.levelno >= logging.ERROR:
            color = Colors.FAIL
        elif record.levelno >= logging.WARNING:
            color = Colors.WARNING
        elif record.levelno >= logging.INFO:
            color = Colors.GREEN
        else:
            color = Colors.BLUE
        record.msg = f"{color}{record.msg}{Colors.ENDC}"
        return super().format(record)

# Configure logger
logger = logging.getLogger('chat_consumer')
logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler()
handler.setFormatter(ColoredFormatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logger.addHandler(handler)

User = get_user_model()

class ChatConsumer(AsyncWebsocketConsumer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.last_ping_time = None
        self.connection_start_time = None
        self.last_heartbeat_time = None
        self.missed_heartbeats = 0
        self.MAX_MISSED_HEARTBEATS = 3
        self.HEARTBEAT_INTERVAL = 30  # seconds
        self.token_validation_timeout = 5  # 5 seconds timeout for token validation

    @database_sync_to_async
    def get_user_and_check_membership(self, token, conversation_id=None):
        """Get user from token and check conversation membership if conversation_id is provided."""
        try:
            access_token = AccessToken(token)
            user_id = access_token['user_id']
            user = User.objects.get(id=user_id)
            is_member = True
            if conversation_id:
                is_member = ConversationMember.objects.filter(
                    conversation_id=conversation_id,
                    user=user
                ).exists()
            return user, is_member
        except Exception as e:
            logger.error(f"[Token/Membership Validation] Error: {str(e)}", exc_info=True)
            return None, False

    async def connect(self):
        self.connection_start_time = time.time()
        self.last_heartbeat_time = time.time()
        logger.info(f"{Colors.CYAN}=== WebSocket Connection Attempt ==={Colors.ENDC}")
        
        try:
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

            # Get conversation_id from URL route kwargs if available
            self.conversation_id = self.scope['url_route']['kwargs'].get('conversation_id')

            # Validate token and check membership in one DB call
            try:
                self.user, is_member = await asyncio.wait_for(
                    self.get_user_and_check_membership(token, self.conversation_id),
                    timeout=self.token_validation_timeout
                )
            except asyncio.TimeoutError:
                logger.error("[Connect] Token/membership validation timed out")
                await self.close(code=1008)
                return

            if not self.user:
                logger.error("[Connect] Token validation failed - no user found")
                await self.close(code=1008)
                return

            if self.conversation_id and not is_member:
                logger.error(f"[Connect] User {self.user.username} is not a member of conversation {self.conversation_id}")
                await self.close(code=1008)
                return

            # Update user's online status to 'online'
            await self.update_user_online_status('online')

            if self.conversation_id:
                self.room_group_name = f'chat_{self.conversation_id}'
                logger.info(f"{Colors.BLUE}Conversation ID: {self.conversation_id}{Colors.ENDC}")
                await self.channel_layer.group_add(
                    self.room_group_name,
                    self.channel_name
                )
                logger.info(f"{Colors.GREEN}Added to group: {self.room_group_name}{Colors.ENDC}")
            else:
                self.room_group_name = 'chat_general'
                logger.info(f"{Colors.BLUE}Joining general chat room{Colors.ENDC}")
                await self.channel_layer.group_add(
                    self.room_group_name,
                    self.channel_name
                )
                logger.info(f"{Colors.GREEN}Added to general chat group{Colors.ENDC}")

            # Accept the WebSocket connection
            await self.accept()
            logger.info(f"{Colors.GREEN}WebSocket connection accepted{Colors.ENDC}")

            # Send initial messages if in a specific conversation
            if self.conversation_id:
                logger.info(f"{Colors.CYAN}=== Sending Initial Messages ==={Colors.ENDC}")
                messages = await self.get_initial_messages()
                logger.info(f"{Colors.BLUE}Found {len(messages)} messages{Colors.ENDC}")
                
                if messages:
                    await self.send(text_data=json.dumps({
                        'type': 'initial_messages',
                        'messages': messages
                    }))
                logger.info(f"{Colors.GREEN}Initial messages sent{Colors.ENDC}")

            # Send initial heartbeat
            await self.send_heartbeat()
            
        except Exception as e:
            logger.error(f"[Connect] Unexpected error during WebSocket connection: {str(e)}", exc_info=True)
            await self.close(code=1011)  # Internal error
            return

    async def disconnect(self, close_code):
        connection_duration = time.time() - self.connection_start_time if self.connection_start_time else 0
        logger.info(f"{Colors.CYAN}=== WebSocket Disconnection ==={Colors.ENDC}")
        logger.info(f"{Colors.BLUE}Close code: {close_code}{Colors.ENDC}")
        logger.info(f"{Colors.BLUE}Channel name: {self.channel_name}{Colors.ENDC}")
        logger.info(f"{Colors.BLUE}Conversation ID: {getattr(self, 'conversation_id', 'Not set')}{Colors.ENDC}")
        logger.info(f"{Colors.BLUE}Connection duration: {connection_duration:.2f} seconds{Colors.ENDC}")
        logger.info(f"{Colors.BLUE}Missed heartbeats: {self.missed_heartbeats}{Colors.ENDC}")

        # Update user's online status to 'offline' if no other connections exist
        if hasattr(self, 'user'):
            await self.update_user_online_status('offline')

        # Leave room group if it exists
        if hasattr(self, 'room_group_name'):
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name
            )
            logger.info(f"{Colors.GREEN}Removed from group: {self.room_group_name}{Colors.ENDC}")

    @database_sync_to_async
    def get_initial_messages(self):
        """Get initial messages for the conversation"""
        try:
            logger.info(f"{Colors.CYAN}=== Fetching Initial Messages ==={Colors.ENDC}")
            logger.info(f"{Colors.BLUE}Conversation ID: {self.conversation_id}{Colors.ENDC}")
            
            conversation = Conversation.objects.get(id=self.conversation_id)
            messages = Message.objects.filter(conversation=conversation).order_by('-created_at')[:50]
            
            logger.info(f"{Colors.BLUE}Found {len(messages)} messages{Colors.ENDC}")
            
            # Serialize messages
            serializer = MessageSerializer(messages, many=True)
            serialized_messages = serializer.data
            
            logger.info(f"{Colors.GREEN}Messages serialized successfully{Colors.ENDC}")
            logger.info(f"{Colors.BLUE}First message data: {json.dumps(serialized_messages[0] if serialized_messages else {}, indent=2)}{Colors.ENDC}")
            
            return serialized_messages
        except Conversation.DoesNotExist:
            logger.error(f"{Colors.FAIL}Conversation not found: {self.conversation_id}{Colors.ENDC}")
            return []
        except Exception as e:
            logger.error(f"{Colors.FAIL}Error fetching initial messages: {str(e)}{Colors.ENDC}")
            logger.error(f"{Colors.FAIL}Stack trace: {traceback.format_exc()}{Colors.ENDC}")
            return []

    async def receive(self, text_data=None, bytes_data=None):
        try:
            if text_data:
                data = json.loads(text_data)
                message_type = data.get('type')
                
                if message_type == 'chat_message':
                    content = data.get('content', '')
                    conversation_id = data.get('conversation')
                    message_type = data.get('message_type', 'text')
                    story_id = data.get('story')  # New: get story id
                    story = None
                    if story_id:
                        try:
                            story = await database_sync_to_async(Story.objects.get)(id=story_id)
                        except Story.DoesNotExist:
                            story = None
                    
                    if not conversation_id:
                        await self.send(text_data=json.dumps({
                            'type': 'error',
                            'message': 'Conversation ID is required'
                        }))
                        return

                    # Get the conversation and sender
                    try:
                        conversation = await database_sync_to_async(Conversation.objects.get)(id=conversation_id)
                        sender = self.user  # Use the authenticated user from the WebSocket connection
                        
                        # Check if user is a member of the conversation
                        is_member = await database_sync_to_async(conversation.is_participant)(sender)
                        if not is_member:
                            await self.send(text_data=json.dumps({
                                'type': 'error',
                                'message': 'You are not a member of this conversation'
                            }))
                            return
                        
                        logger.info(f"{Colors.BLUE}Found conversation: {conversation.id}{Colors.ENDC}")
                        logger.info(f"{Colors.BLUE}Sender: {sender.username} (ID: {sender.id}){Colors.ENDC}")

                        # Get message data from the correct structure
                        message_data = data.get('message', {})
                        content = message_data.get('content', '')
                        files = message_data.get('files', [])
                        message_type = message_data.get('message_type', 'text')

                        # Validate message has content or files
                        if not content and not files:
                            await self.send(text_data=json.dumps({
                                'type': 'error',
                                'message': 'Message must have content or files'
                            }))
                            return

                        # Determine message type based on content and files
                        if files and len(files) > 0:
                            if content:
                                message_type = 'mixed'
                            else:
                                # Determine type from first file
                                first_file = files[0]
                                file_type = first_file.get('file_type', '')
                                if file_type.startswith('image/'):
                                    message_type = 'image'
                                elif file_type.startswith('video/'):
                                    message_type = 'video'
                                elif file_type.startswith('audio/'):
                                    message_type = 'voice'
                                else:
                                    message_type = 'file'
                        else:
                            message_type = 'text'

                        # Create message without files first, now with story
                        message = await database_sync_to_async(Message.objects.create)(
                            conversation=conversation,
                            sender=sender,
                            content=content,
                            message_type=message_type,
                            story=story  # Attach story if provided
                        )

                        # Track completed files
                        completed_files = []

                        # Handle file attachments if provided
                        if files and len(files) > 0:
                            for file_data in files:
                                try:
                                    # Get base64 data
                                    base64_data = file_data.get('file')
                                    if not base64_data:
                                        logger.error("No file data found in message")
                                        continue

                                    # Remove data URL prefix if present
                                    if base64_data.startswith('data:'):
                                        base64_data = base64_data.split(',')[1]

                                    # Decode base64 data
                                    file_content = base64.b64decode(base64_data)
                                    file_name = file_data.get('file_name', 'unnamed_file')
                                    file_type = file_data.get('file_type', 'application/octet-stream')

                                    # Create a temporary file
                                    with tempfile.NamedTemporaryFile(delete=False) as temp_file:
                                        temp_file.write(file_content)
                                        temp_file.flush()

                                        # Create Django file object
                                        django_file = ContentFile(file_content, name=file_name)

                                        # Create File model instance
                                        file_instance = await database_sync_to_async(File.objects.create)(
                                            file=django_file,
                                            file_name=file_name,
                                            file_type=file_type,
                                            file_size=len(file_content),
                                            category=file_data.get('category', 'document'),
                                            uploaded_by=sender
                                        )

                                        # Add file to message
                                        await database_sync_to_async(message.files.add)(file_instance)
                                        completed_files.append(file_instance)

                                        # Clean up temporary file
                                        os.unlink(temp_file.name)

                                except Exception as e:
                                    logger.error(f"Error processing file: {str(e)}")
                                    continue

                        # Update message type if needed after file processing
                        if completed_files and not content:
                            first_file = completed_files[0]
                            if first_file.category in ['image', 'video', 'audio']:
                                message.message_type = first_file.category
                            else:
                                message.message_type = 'file'
                        elif completed_files and content:
                            message.message_type = 'mixed'
                        elif not completed_files and content:
                            message.message_type = 'text'

                        # Save the message with updated type
                        await database_sync_to_async(message.save)()

                        # Broadcast the message to the conversation group
                        await self.channel_layer.group_send(
                            self.room_group_name,
                            {
                                'type': 'chat_message',
                                'message': {
                                    'id': str(message.id),
                                    'content': message.content,
                                    'message_type': message.message_type,
                                    'sender': {
                                        'id': str(sender.id),
                                        'username': sender.username
                                    },
                                    'conversation': str(conversation.id),
                                    'created_at': message.created_at.isoformat(),
                                    'files': [{
                                        'id': str(f.id),
                                        'file_name': f.file_name,
                                        'file_type': f.file_type,
                                        'file_size': f.file_size,
                                        'category': f.category,
                                        'url': f.get_url()
                                    } for f in completed_files]
                                }
                            }
                        )
                        logger.info(f"{Colors.GREEN}Message sent successfully{Colors.ENDC}")

                    except Conversation.DoesNotExist:
                        logger.error(f"Error finding conversation or user: Conversation matching query does not exist.")
                        await self.send(text_data=json.dumps({
                            'type': 'error',
                            'message': 'Conversation not found'
                        }))
                    except Exception as e:
                        logger.error(f"Error finding conversation or user: {str(e)}")
                        await self.send(text_data=json.dumps({
                            'type': 'error',
                            'message': str(e)
                        }))
                elif message_type == 'reaction':
                    await self.handle_reaction(data)
                elif message_type == 'typing':
                    await self.handle_typing(data)
                elif message_type == 'read':
                    await self.handle_read(data)
                elif message_type == 'ping':
                    await self.handle_ping(data)
                elif message_type == 'heartbeat':
                    await self.handle_heartbeat(data)
                elif message_type == 'message_received':
                    # Handle message received acknowledgment
                    message_id = data.get('message_id')
                    if message_id:
                        try:
                            message = await database_sync_to_async(Message.objects.get)(id=message_id)
                            if message.conversation.is_participant(self.user):
                                await database_sync_to_async(message.update_status)('delivered')
                                # Broadcast delivery status
                                await self.channel_layer.group_send(
                                    self.room_group_name,
                                    {
                                        'type': 'message_status',
                                        'message_id': message_id,
                                        'status': 'delivered',
                                        'user_id': str(self.user.id)
                                    }
                                )
                        except Message.DoesNotExist:
                            logger.error(f"Message {message_id} not found")
                        except Exception as e:
                            logger.error(f"Error updating message status: {str(e)}")
                else:
                    logger.warning(f"{Colors.WARNING}Invalid message type: {message_type}{Colors.ENDC}")
                    await self.send(text_data=json.dumps({
                        'type': 'error',
                        'error': 'Invalid message type'
                    }))
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            logger.error(f"Stack trace: {traceback.format_exc()}")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': str(e)
            }))

    async def handle_ping(self, data):
        """Handle ping messages from client"""
        try:
            timestamp = data.get('timestamp')
            self.last_ping_time = timestamp
            logger.info(f"{Colors.MAGENTA}=== Ping Received ==={Colors.ENDC}")
            logger.info(f"{Colors.BLUE}Timestamp: {timestamp}{Colors.ENDC}")
            
            # Send pong response
            await self.send(text_data=json.dumps({
                'type': 'pong',
                'timestamp': timestamp,
                'server_time': int(time.time() * 1000)
            }))
            logger.info(f"{Colors.GREEN}Pong sent{Colors.ENDC}")
        except Exception as e:
            logger.error(f"{Colors.FAIL}Error handling ping: {str(e)}{Colors.ENDC}")

    async def handle_heartbeat(self, data):
        """Handle heartbeat messages from client"""
        try:
            timestamp = data.get('timestamp')
            self.last_heartbeat_time = time.time()
            self.missed_heartbeats = 0
            logger.info(f"{Colors.MAGENTA}=== Heartbeat Received ==={Colors.ENDC}")
            logger.info(f"{Colors.BLUE}Timestamp: {timestamp}{Colors.ENDC}")
            
            # Send heartbeat response
            await self.send(text_data=json.dumps({
                'type': 'heartbeat_ack',
                'timestamp': timestamp,
                'server_time': int(time.time() * 1000)
            }))
            logger.info(f"{Colors.GREEN}Heartbeat acknowledged{Colors.ENDC}")
        except Exception as e:
            logger.error(f"{Colors.FAIL}Error handling heartbeat: {str(e)}{Colors.ENDC}")

    async def send_heartbeat(self):
        """Send heartbeat to client"""
        try:
            await self.send(text_data=json.dumps({
                'type': 'heartbeat',
                'timestamp': int(time.time() * 1000)
            }))
            logger.info(f"{Colors.MAGENTA}Heartbeat sent{Colors.ENDC}")
        except Exception as e:
            logger.error(f"{Colors.FAIL}Error sending heartbeat: {str(e)}{Colors.ENDC}")

    async def check_connection_health(self):
        """Check connection health and handle missed heartbeats"""
        current_time = time.time()
        if self.last_heartbeat_time and (current_time - self.last_heartbeat_time) > self.HEARTBEAT_INTERVAL:
            self.missed_heartbeats += 1
            logger.warning(f"{Colors.YELLOW}Missed heartbeat ({self.missed_heartbeats}/{self.MAX_MISSED_HEARTBEATS}){Colors.ENDC}")
            
            if self.missed_heartbeats >= self.MAX_MISSED_HEARTBEATS:
                logger.error(f"{Colors.FAIL}Connection unhealthy - too many missed heartbeats{Colors.ENDC}")
                await self.close()
            else:
                await self.send_heartbeat()
        else:
            self.missed_heartbeats = 0

    async def handle_reaction(self, data):
        try:
            message_id = data.get('message_id')
            emoji = data.get('emoji')
            action = data.get('action', 'add')  # 'add' or 'remove'

            # Get the message
            message = await database_sync_to_async(Message.objects.get)(id=message_id)
            
            if action == 'add':
                # Add reaction
                reaction = await database_sync_to_async(MessageReaction.objects.create)(
                    message=message,
                    user=self.user,
                    emoji=emoji
                )
                
                # Get reaction data in the correct format
                reaction_data = {
                    'emoji': emoji,
                    'count': await database_sync_to_async(MessageReaction.objects.filter)(
                        message=message,
                        emoji=emoji
                    ).count(),
                    'users': await database_sync_to_async(list)(
                        MessageReaction.objects.filter(
                            message=message,
                            emoji=emoji
                        ).values_list('user__username', flat=True)
                    ),
                    'isSelected': True
                }
            else:
                # Remove reaction
                await database_sync_to_async(MessageReaction.objects.filter)(
                    message=message,
                    user=self.user,
                    emoji=emoji
                ).delete()
                
                # Get updated reaction data
                reaction_data = {
                    'emoji': emoji,
                    'count': await database_sync_to_async(MessageReaction.objects.filter)(
                        message=message,
                        emoji=emoji
                    ).count(),
                    'users': await database_sync_to_async(list)(
                        MessageReaction.objects.filter(
                            message=message,
                            emoji=emoji
                        ).values_list('user__username', flat=True)
                    ),
                    'isSelected': False
                }

            # Broadcast the reaction update
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'reaction_update',
                    'message_id': message_id,
                    'reaction': reaction_data
                }
            )

        except Message.DoesNotExist:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Message not found'
            }))
        except Exception as e:
            logger.error(f"Error handling reaction: {e}")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': str(e)
            }))

    async def handle_typing(self, data):
        try:
            # Broadcast typing status
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'chat_typing',
                    'user_id': self.user.id,
                    'username': self.user.username,
                    'is_typing': data.get('is_typing', False)
                }
            )
        except Exception as e:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'error': f'Error processing typing status: {str(e)}'
            }))

    async def handle_read(self, data):
        try:
            # Update read status
            success = await self.update_read_status(data)
            if success:
                # Broadcast read status
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'chat_read',
                        'user_id': self.user.id,
                        'message_id': data.get('message_id')
                    }
                )
            else:
                await self.send(text_data=json.dumps({
                    'type': 'error',
                    'error': 'Failed to update read status'
                }))
        except Exception as e:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'error': f'Error processing read status: {str(e)}'
            }))

    @database_sync_to_async
    def update_read_status(self, data):
        try:
            message = Message.objects.get(id=data.get('message_id'))
            if not message.conversation.is_participant(self.user):
                return False

            message.update_status('read')
            return True
        except Exception as e:
            print(f"Error updating read status: {e}")
            return False

    async def chat_message(self, event):
        """Handle chat_message type events."""
        message = event['message']
        await self.send(text_data=json.dumps({
            'type': 'chat_message',
            'message': message
        }))

    async def reaction_update(self, event):
        """Handle reaction_update type events."""
        await self.send(text_data=json.dumps({
            'type': 'reaction_update',
            'message_id': event['message_id'],
            'reaction': event['reaction']
        }))

    async def chat_typing(self, event):
        logger.info(f"{Colors.CYAN}=== Sending Typing Status ==={Colors.ENDC}")
        logger.info(f"{Colors.BLUE}Event data: {json.dumps(event, indent=2)}{Colors.ENDC}")
        
        # Send typing status to WebSocket
        await self.send(text_data=json.dumps({
            'type': 'typing',
            'user_id': event['user_id'],
            'username': event['username'],
            'is_typing': event['is_typing']
        }))
        logger.info(f"{Colors.GREEN}Typing status sent to WebSocket{Colors.ENDC}")

    async def chat_read(self, event):
        logger.info(f"{Colors.CYAN}=== Sending Read Status ==={Colors.ENDC}")
        logger.info(f"{Colors.BLUE}Event data: {json.dumps(event, indent=2)}{Colors.ENDC}")
        
        # Send read status to WebSocket
        await self.send(text_data=json.dumps({
            'type': 'read',
            'user_id': event['user_id'],
            'message_id': event['message_id']
        }))
        logger.info(f"{Colors.GREEN}Read status sent to WebSocket{Colors.ENDC}")

    async def handle_token_refresh(self, data):
        """Handle token refresh requests from client"""
        try:
            refresh_token = data.get('refresh_token')
            if not refresh_token:
                await self.send(text_data=json.dumps({
                    'type': 'error',
                    'message': 'No refresh token provided'
                }))
                return

            # Validate refresh token and get new access token
            try:
                from rest_framework_simplejwt.tokens import RefreshToken
                refresh = RefreshToken(refresh_token)
                new_access_token = str(refresh.access_token)
                
                # Send new access token to client
                await self.send(text_data=json.dumps({
                    'type': 'token_refresh',
                    'access_token': new_access_token
                }))
                logger.info(f"{Colors.GREEN}Token refresh successful for user {self.user.id}{Colors.ENDC}")
            except Exception as e:
                logger.error(f"{Colors.FAIL}Token refresh failed: {str(e)}{Colors.ENDC}")
                await self.send(text_data=json.dumps({
                    'type': 'error',
                    'message': 'Invalid refresh token'
                }))
                await self.close(code=1008)  # Policy violation
        except Exception as e:
            logger.error(f"{Colors.FAIL}Error handling token refresh: {str(e)}{Colors.ENDC}")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Error processing token refresh'
            }))

    async def message_status(self, event):
        """Handle message status updates."""
        await self.send(text_data=json.dumps({
            'type': 'message_status',
            'message_id': event['message_id'],
            'status': event['status'],
            'user_id': event['user_id']
        }))

    async def unread_count_update(self, event):
        """Handle unread count update events."""
        try:
            logger.info(f"ChatConsumer received unread_count_update event: {event}")
            
            # Extract and validate the unread count
            unread_count = event.get('unread_count')
            if isinstance(unread_count, models.F):
                logger.error("Received F() expression instead of numeric unread count")
                return
                
            try:
                unread_count = int(unread_count)
            except (TypeError, ValueError):
                logger.error(f"Invalid unread count value: {unread_count}")
                return
                
            # Only send the update to the specific user
            if str(self.user.id) == event['user_id']:
                message = {
                    'type': 'unread_count_update',
                    'conversation_id': event['conversation_id'],
                    'unread_count': unread_count
                }
                logger.info(f"Sending unread count update to user {self.user.username}: {message}")
                await self.send(text_data=json.dumps(message))
                logger.info(f"Successfully sent unread count update to user {self.user.username}")
            else:
                logger.info(f"Skipping unread count update for user {self.user.username} (not the target user)")
        except Exception as e:
            logger.error(f"Error handling unread count update: {str(e)}", exc_info=True)

    @database_sync_to_async
    def update_user_online_status(self, status):
        """Update user's online status in the database and broadcast to connected users."""
        try:
            if hasattr(self, 'user') and self.user:
                old_status = self.user.online_status
                self.user.online_status = status
                self.user.last_active = timezone.now()
                self.user.save(update_fields=['online_status', 'last_active'])
                logger.info(f"Updated {self.user.username} online status to: {status}")
                
                # Broadcast status change to connected users
                if old_status != status:
                    asyncio.create_task(self.broadcast_online_status_change(status))
        except Exception as e:
            logger.error(f"Error updating user online status: {str(e)}")

    async def broadcast_online_status_change(self, new_status):
        """Broadcast online status change to connected users."""
        try:
            # Get all conversations where this user is a participant
            conversations = await self.get_user_conversations()
            
            for conversation in conversations:
                # Send to all participants in this conversation
                await self.channel_layer.group_send(
                    f'chat_{conversation.id}',
                    {
                        'type': 'online_status_change',
                        'user_id': str(self.user.id),
                        'username': self.user.username,
                        'online_status': new_status,
                        'is_online': new_status == 'online',
                        'last_active': timezone.now().isoformat()
                    }
                )
                
            # Also send to user's personal group for general status updates
            await self.channel_layer.group_send(
                f'user_{self.user.id}',
                {
                    'type': 'online_status_change',
                    'user_id': str(self.user.id),
                    'username': self.user.username,
                    'online_status': new_status,
                    'is_online': new_status == 'online',
                    'last_active': timezone.now().isoformat()
                }
            )
            
        except Exception as e:
            logger.error(f"Error broadcasting online status change: {str(e)}")

    @database_sync_to_async
    def get_user_conversations(self):
        """Get all conversations where the user is a participant."""
        try:
            from chat.models import Conversation
            return list(Conversation.objects.filter(
                participants=self.user
            ).distinct())
        except Exception as e:
            logger.error(f"Error getting user conversations: {str(e)}")
            return []

    async def online_status_change(self, event):
        """Handle online status change events."""
        await self.send(text_data=json.dumps({
            'type': 'online_status_change',
            'user_id': event['user_id'],
            'username': event['username'],
            'online_status': event['online_status'],
            'is_online': event['is_online'],
            'last_active': event['last_active']
        }))

class GlobalChatConsumer(AsyncWebsocketConsumer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.last_ping_time = None
        self.connection_start_time = None
        self.last_heartbeat_time = None
        self.missed_heartbeats = 0
        self.MAX_MISSED_HEARTBEATS = 3
        self.HEARTBEAT_INTERVAL = 30  # seconds
        self.token_validation_timeout = 5  # seconds
        self.user = None
        self.room_group_name = 'chat_global'  # Fixed group name for global chat

    async def connect(self):
        try:
            logger.info("=== Global Chat WebSocket Connection Attempt ===")
            
            # Get token from query string
            query_string = self.scope['query_string'].decode()
            logger.info(f"Query string: {query_string}")
            
            token = None
            for param in query_string.split('&'):
                if param.startswith('token='):
                    token = param.split('=')[1]
                    token = urllib.parse.unquote(token)
                    break

            if not token:
                logger.error("No token found in query string")
                await self.close(code=1008)  # Policy violation
                return

            # Validate token and get user using database_sync_to_async
            try:
                self.user = await self.get_user_from_token(token)
                if not self.user:
                    logger.error("Failed to validate token or get user")
                    await self.close(code=1008)  # Policy violation
                    return
            except Exception as e:
                logger.error(f"Token validation error: {str(e)}", exc_info=True)
                await self.close(code=1008)  # Policy violation
                return

            # Accept the connection
            await self.accept()
            logger.info(f"WebSocket connection accepted for user {self.user.username}")

            # Add to global chat group
            await self.channel_layer.group_add(
                "chat_global",
                self.channel_name
            )
            logger.info("Added to global chat group: chat_global")

            # Start heartbeat
            self.heartbeat_task = asyncio.create_task(self.start_heartbeat())

        except Exception as e:
            logger.error(f"Error in connect: {str(e)}", exc_info=True)
            await self.close(code=1011)  # Internal error

    async def disconnect(self, close_code):
        try:
            logger.info(f"=== WebSocket Disconnection ===")
            logger.info(f"Close code: {close_code}")
            logger.info(f"Channel name: {self.channel_name}")
            
            # Cancel heartbeat task if it exists
            if hasattr(self, 'heartbeat_task'):
                self.heartbeat_task.cancel()
                try:
                    await self.heartbeat_task
                except asyncio.CancelledError:
                    pass
                logger.info("Heartbeat task cancelled")
            
            # Remove from global chat group
            await self.channel_layer.group_discard(
                "chat_global",
                self.channel_name
            )
            logger.info("Removed from global chat group")
            
        except Exception as e:
            logger.error(f"Error in disconnect: {str(e)}", exc_info=True)

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            message_type = data.get('type')
            
            if message_type == 'chat_message':
                await self.handle_chat_message(data)
            elif message_type == 'heartbeat':
                await self.handle_heartbeat()
            else:
                logger.warning(f"Unknown message type: {message_type}")
                
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {str(e)}")
        except Exception as e:
            logger.error(f"Error in receive: {str(e)}", exc_info=True)

    async def handle_chat_message(self, data):
        try:
            message = data.get('message', '').strip()
            if not message:
                return

            # Broadcast to global chat group
            await self.channel_layer.group_send(
                "chat_global",
                {
                    'type': 'chat_message',
                    'message': message,
                    'username': self.user.username,
                    'timestamp': timezone.now().isoformat()
                }
            )
            
        except Exception as e:
            logger.error(f"Error in handle_chat_message: {str(e)}", exc_info=True)

    async def chat_message(self, event):
        try:
            await self.send(text_data=json.dumps({
                'type': 'chat_message',
                'message': event['message'],
                'username': event['username'],
                'timestamp': event['timestamp']
            }))
        except Exception as e:
            logger.error(f"Error in chat_message: {str(e)}", exc_info=True)

    async def start_heartbeat(self):
        try:
            while True:
                await asyncio.sleep(30)  # Send heartbeat every 30 seconds
                await self.send(text_data=json.dumps({
                    'type': 'heartbeat',
                    'timestamp': timezone.now().isoformat()
                }))
        except asyncio.CancelledError:
            logger.info("Heartbeat task cancelled")
        except Exception as e:
            logger.error(f"Error in heartbeat: {str(e)}", exc_info=True)

    async def handle_heartbeat(self):
        try:
            await self.send(text_data=json.dumps({
                'type': 'heartbeat_ack',
                'timestamp': timezone.now().isoformat()
            }))
        except Exception as e:
            logger.error(f"Error in handle_heartbeat: {str(e)}", exc_info=True)

    @database_sync_to_async
    def get_user_from_token(self, token):
        try:
            access_token = AccessToken(token)
            user_id = access_token['user_id']
            return User.objects.get(id=user_id)
        except Exception as e:
            logger.error(f"Error getting user from token: {str(e)}", exc_info=True)
            return None

    @database_sync_to_async
    def get_user_context(self):
        """Get user context in a sync context."""
        if not self.user:
            return {}
        try:
            # Get user's recent messages
            recent_messages = ChatMessage.objects.filter(
                user=self.user
            ).order_by('-created_at')[:10]
            
            # Get user's active conversations
            active_conversations = ChatMessage.objects.filter(
                user=self.user
            ).values('conversation_id').distinct()[:5]
            
            return {
                'recent_messages': [
                    {
                        'id': msg.id,
                        'message': msg.message,
                        'is_user_message': msg.is_user_message,
                        'created_at': msg.created_at.isoformat(),
                        'conversation_id': msg.conversation_id
                    }
                    for msg in recent_messages
                ],
                'active_conversations': list(active_conversations)
            }
        except Exception as e:
            logger.error(f"Error getting user context: {str(e)}", exc_info=True)
            return {}

    async def unread_count_update(self, event):
        """Handle unread count update events."""
        try:
            logger.info(f"GlobalChatConsumer received unread_count_update event: {event}")
            
            # Extract and validate the unread count
            unread_count = event.get('unread_count')
            if isinstance(unread_count, models.F):
                logger.error("Received F() expression instead of numeric unread count")
                return
                
            try:
                unread_count = int(unread_count)
            except (TypeError, ValueError):
                logger.error(f"Invalid unread count value: {unread_count}")
                return
                
            # Send the update to the client
            message = {
                'type': 'unread_count_update',
                'unread_count': unread_count
            }
            logger.info(f"Sending unread count update to user {self.user.username}: {message}")
            await self.send(text_data=json.dumps(message))
            logger.info(f"Successfully sent unread count update to user {self.user.username}")
        except Exception as e:
            logger.error(f"Error handling unread count update: {str(e)}", exc_info=True)

    async def start_heartbeat(self):
        try:
            while True:
                await asyncio.sleep(30)  # Send heartbeat every 30 seconds
                await self.send(text_data=json.dumps({
                    'type': 'heartbeat',
                    'timestamp': timezone.now().isoformat()
                }))
        except asyncio.CancelledError:
            logger.info("Heartbeat task cancelled")
        except Exception as e:
            logger.error(f"Error in heartbeat: {str(e)}", exc_info=True) 