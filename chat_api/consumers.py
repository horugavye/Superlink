import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from chat.models import (
    Conversation,
    ConversationMember,
    Message,
    MessageReaction,
    MessageThread,
    MessageEffect,
    LinkPreview
)
from .serializers import (
    MessageSerializer,
    MessageReactionSerializer,
    MessageThreadSerializer,
    MessageEffectSerializer,
    LinkPreviewSerializer
)
from rest_framework.request import Request
from django.http import HttpRequest
from channels.middleware import BaseMiddleware
from channels.auth import AuthMiddlewareStack
from django.contrib.auth.models import AnonymousUser
from urllib.parse import parse_qs
import jwt
from django.conf import settings
import asyncio
import urllib.parse
from rest_framework_simplejwt.tokens import AccessToken
from django.core.exceptions import ObjectDoesNotExist
import traceback
from django.core.files.base import ContentFile
from channels.exceptions import DenyConnection
from django.utils import timezone
import base64
import tempfile
import os
from PIL import Image
from io import BytesIO
from django.core.files import File
from django.db.models.functions import Now
from django.db.models import F
import time

# Optional imports for media processing
try:
    from moviepy.editor import VideoFileClip
    VIDEO_PROCESSING_AVAILABLE = True
except ImportError:
    VIDEO_PROCESSING_AVAILABLE = False

try:
    from pydub import AudioSegment
    AUDIO_PROCESSING_AVAILABLE = True
except ImportError:
    AUDIO_PROCESSING_AVAILABLE = False

logger = logging.getLogger(__name__)
User = get_user_model()

class TokenAuthMiddleware(BaseMiddleware):
    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        try:
            # Get the token from the query string
            query_string = scope.get('query_string', b'').decode()
            query_params = parse_qs(query_string)
            token = query_params.get('token', [None])[0]

            if token:
                try:
                    # Decode the JWT token
                    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=['HS256'])
                    user_id = payload.get('user_id')
                    if user_id:
                        user = await database_sync_to_async(User.objects.get)(id=user_id)
                        scope['user'] = user
                        return await self.inner(scope, receive, send)
                except (jwt.InvalidTokenError, User.DoesNotExist):
                    pass

            # If no token or invalid token, set anonymous user
            scope['user'] = AnonymousUser()
            return await self.inner(scope, receive, send)
        except Exception as e:
            logger.error(f"Error in TokenAuthMiddleware: {str(e)}")
            scope['user'] = AnonymousUser()
            return await self.inner(scope, receive, send)

def TokenAuthMiddlewareStack(inner):
    return TokenAuthMiddleware(AuthMiddlewareStack(inner))

class ChatConsumer(AsyncWebsocketConsumer):
    # Add connection tracking
    _active_connections = {}
    _connection_locks = {}

    async def connect(self):
        try:
            print("\n=== WebSocket Connection Attempt ===")
            print(f"User: {self.scope['user']}")
            print(f"Path: {self.scope['path']}")
            print(f"Query String: {self.scope['query_string']}")

            # Get conversation ID from path
            self.conversation_id = self.scope['url_route']['kwargs']['conversation_id']
            print(f"Conversation ID: {self.conversation_id}")

            # Check if user is authenticated
            if self.scope['user'].is_anonymous:
                print("Anonymous user, rejecting connection")
                await self.close()
                return

            # Check if user is a member of the conversation
            is_member = await self.is_conversation_member(self.conversation_id)
            if not is_member:
                print("User is not a member of the conversation")
                await self.close()
                return

            # Join conversation group
            await self.channel_layer.group_add(
                f"chat_{self.conversation_id}",
                self.channel_name
            )
            print(f"Added to group: chat_{self.conversation_id}")

            # Accept the connection
            await self.accept()
            print("WebSocket connection accepted")

            # Send initial messages
            await self.send_initial_messages()

        except Exception as e:
            print(f"Error in connect: {str(e)}")
            await self.close()

    @database_sync_to_async
    def is_conversation_member(self, conversation_id):
        try:
            return ConversationMember.objects.filter(
                conversation_id=conversation_id,
                user=self.scope['user']
            ).exists()
        except Exception as e:
            print(f"Error checking conversation membership: {str(e)}")
            return False

    @database_sync_to_async
    def get_conversation_messages(self, conversation_id, limit=50):
        try:
            messages = Message.objects.filter(
                conversation_id=conversation_id
            ).order_by('-created_at')[:limit]
            
            # Create a request object for the serializer
            request = HttpRequest()
            request.user = self.scope['user']
            request.META['HTTP_HOST'] = 'localhost:8000'  # Set the host for URL generation
            request.META['wsgi.url_scheme'] = 'http'  # Set the scheme for URL generation
            
            return MessageSerializer(messages, many=True, context={'request': request}).data
        except Exception as e:
            print(f"Error getting messages: {str(e)}")
            return []

    async def send_initial_messages(self):
        try:
            print("\n=== Sending Initial Messages ===")
            messages = await self.get_conversation_messages(self.conversation_id)
            print(f"Found {len(messages)} messages")
            
            await self.send(text_data=json.dumps({
                'type': 'initial_messages',
                'messages': messages
            }))
            print("Initial messages sent")
            
        except Exception as e:
            print(f"Error sending initial messages: {str(e)}")

    async def disconnect(self, close_code):
        try:
            print(f"\n=== WebSocket Disconnection ===")
            print(f"Close code: {close_code}")
            print(f"Channel name: {self.channel_name}")
            print(f"Conversation ID: {self.conversation_id}")

            # Leave conversation group
            await self.channel_layer.group_discard(
                f"chat_{self.conversation_id}",
                self.channel_name
            )
            print(f"Removed from group: chat_{self.conversation_id}")

        except Exception as e:
            print(f"Error in disconnect: {str(e)}")

    @database_sync_to_async
    def get_request_context(self):
        """Create a request object for the serializer context"""
        request = HttpRequest()
        request.user = self.scope['user']
        request.META['HTTP_HOST'] = 'localhost:8000'  # Set the host for URL generation
        request.META['wsgi.url_scheme'] = 'http'  # Set the scheme for URL generation
        return {'request': request}

    async def handle_message(self, text_data):
        try:
            data = json.loads(text_data)
            message_type = data.get('type')
            
            if message_type == 'chat_message':
                # Get the current timestamp in milliseconds
                timestamp = int(time.time() * 1000)
                
                # Create message with timestamp
                message = await self.create_message(
                    conversation=data['conversation'],
                    content=data.get('content', ''),
                    file_data=data.get('file'),
                    reply_to_id=data.get('reply_to'),
                    thread_id=data.get('thread_id'),
                    timestamp=timestamp
                )
                
                # Process message for sending
                message_data = await self.process_message_for_sending(message)
                
                # Send message to group
                await self.channel_layer.group_send(
                    f"chat_{self.conversation_id}",
                    {
                        'type': 'chat_message',
                        'message': message_data
                    }
                )
                
                # Send acknowledgment to sender
                await self.send(text_data=json.dumps({
                    'type': 'message_sent',
                    'message_id': str(message.id),
                    'timestamp': timestamp
                }))
            elif message_type == 'thread_message':
                await self.handle_thread_message(data)
            elif message_type == 'reaction':
                await self.handle_reaction(data)
            elif message_type == 'effect':
                await self.handle_effect(data)
            elif message_type == 'link_preview':
                await self.handle_link_preview(data)
            elif message_type == 'edit_message':
                await self.handle_edit_message(data)
            elif message_type == 'pin_message':
                await self.handle_pin_message(data)
            elif message_type == 'forward_message':
                await self.handle_forward_message(data)
            elif message_type == 'typing':
                await self.handle_typing(data)
            elif message_type == 'read':
                await self.handle_read(data)
            elif message_type == 'ping':
                await self.handle_ping(data)
            else:
                await self.send_error(f"Unknown message type: {message_type}")
                
        except json.JSONDecodeError:
            await self.send_error("Invalid JSON format")
        except Exception as e:
            logger.error(f"Error handling message: {str(e)}")
            await self.send_error(str(e))

    async def create_message(self, conversation, content='', file_data=None, reply_to_id=None, thread_id=None, timestamp=None):
        try:
            # Use provided timestamp or generate new one
            if not timestamp:
                timestamp = int(time.time() * 1000)
            
            # Create message
            message = await database_sync_to_async(Message.objects.create)(
                conversation=conversation,
                content=content,
                sender=self.scope['user'],
                timestamp=timestamp
            )
            
            # Handle file attachment
            if file_data:
                try:
                    # Create file instance
                    file_instance = await database_sync_to_async(File.objects.create)(
                        file=file_data['file'],
                        file_name=file_data['name'],
                        file_type=file_data['type'],
                        file_size=file_data['size']
                    )
                    
                    # Ensure the file path is set correctly
                    if file_instance.file:
                        # Generate a unique filename
                        unique_filename = f"{file_instance.id}_{file_data['name']}"
                        file_instance.file.name = f'chat_attachments/{unique_filename}'
                        await database_sync_to_async(file_instance.save)()
                        
                        # Generate thumbnail for images
                        if file_data['type'].startswith('image/'):
                        try:
                                with Image.open(file_data['file']) as img:
                                    # Convert to RGB if necessary
                                if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
                                    img = img.convert('RGB')
                                
                                    # Calculate thumbnail size
                                    max_size = (200, 200)
                                    img.thumbnail(max_size, Image.Resampling.LANCZOS)
                                    
                                    # Save thumbnail
                                thumb_io = BytesIO()
                                img.save(thumb_io, format='JPEG', quality=85)
                                thumb_io.seek(0)
                                    
                                    # Generate thumbnail filename
                                    thumb_name = f"thumb_{unique_filename}"
                                    thumb_path = f'chat_attachments/thumbnails/{thumb_name}'
                                    
                                    # Save thumbnail
                                    file_instance.thumbnail.save(thumb_path, ContentFile(thumb_io.read()), save=True)
                                file_instance.thumbnail_url = file_instance.thumbnail.url
                                    await database_sync_to_async(file_instance.save)()
                        except Exception as e:
                            logger.error(f"Error generating thumbnail: {str(e)}")
                    
                    # Add file to message
                    await database_sync_to_async(message.files.add)(file_instance)
                            except Exception as e:
                    logger.error(f"Error processing file: {str(e)}")
            
            return message
        except Exception as e:
            logger.error(f"Error creating message: {str(e)}")
            raise

    @database_sync_to_async
    def save_message(self, message):
        try:
            message.save()
        except Exception as e:
            logger.error(f"Error saving message: {str(e)}")
            raise

    @database_sync_to_async
    def create_reaction(self, data):
        try:
            message = Message.objects.get(id=data['message_id'])
            user = self.scope['user']
            
            # Check if user is a member of the conversation
            if not message.conversation.members.filter(user=user).exists():
                raise PermissionError("You are not a member of this conversation")
            
            # Check if user has permission to react
            member = message.conversation.members.get(user=user)
            if not member.has_permission('react_messages'):
                raise PermissionError("You do not have permission to react to messages")
            
            # Create or update reaction
            reaction, created = MessageReaction.objects.get_or_create(
                message=message,
                user=user,
                emoji=data['emoji']
            )
            
            if not created:
                reaction.delete()
                return None
            
            # Create a request object for the serializer
            request = HttpRequest()
            request.user = user
            
            return MessageReactionSerializer(reaction, context={'request': request}).data
            
        except Exception as e:
            print(f"Error creating reaction: {str(e)}")
            raise

    async def handle_reaction(self, data):
        try:
            print("\n=== Handling Reaction ===")
            print(f"Data: {data}")
            
            # Create reaction
            reaction_data = await self.create_reaction(data)
            print(f"Created reaction: {reaction_data}")
            
            if reaction_data:
                # Send reaction to group
                await self.channel_layer.group_send(
                    f"chat_{self.conversation_id}",
                    {
                        'type': 'reaction',
                        'reaction': reaction_data
                    }
                )
                print("Reaction sent to group")
            else:
                # Send reaction removal to group
                await self.channel_layer.group_send(
                    f"chat_{self.conversation_id}",
                    {
                        'type': 'reaction_removed',
                        'message_id': data['message_id'],
                        'user_id': self.scope['user'].id,
                        'emoji': data['emoji']
                    }
                )
                print("Reaction removal sent to group")
            
        except Exception as e:
            print(f"Error handling reaction: {str(e)}")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': str(e)
            }))

    @database_sync_to_async
    def create_thread_message(self, data):
        try:
            parent_message = Message.objects.get(id=data['parent_message_id'])
            user = self.scope['user']
            
            # Check if user is a member of the conversation
            if not parent_message.conversation.members.filter(user=user).exists():
                raise PermissionError("You are not a member of this conversation")
            
            # Get thread (it should exist since it's a OneToOneField)
            try:
                thread = MessageThread.objects.get(parent_message=parent_message)
            except MessageThread.DoesNotExist:
                # Create thread if it doesn't exist
                thread = MessageThread.objects.create(
                    parent_message=parent_message,
                    created_by=user
                )
            
            # Add user to thread participants if not already present
            thread.participants.add(user)
            
            # Create message in thread
            message = Message.objects.create(
                conversation=parent_message.conversation,
                sender=user,
                content=data['content'],
                message_type=data.get('message_type', 'text'),
                thread=thread
            )
            
            # Create a request object for the serializer
            request = HttpRequest()
            request.user = user
            
            return MessageSerializer(message, context={'request': request}).data
            
        except Exception as e:
            print(f"Error creating thread message: {str(e)}")
            raise

    async def handle_thread_message(self, data):
        try:
            print("\n=== Handling Thread Message ===")
            print(f"Data: {data}")
            
            # Create thread message
            message_data = await self.create_thread_message(data)
            print(f"Created thread message: {message_data}")
            
            # Send message to group
            await self.channel_layer.group_send(
                f"chat_{self.conversation_id}",
                {
                    'type': 'thread_message',
                    'message': message_data
                }
            )
            print("Thread message sent to group")
            
        except Exception as e:
            print(f"Error handling thread message: {str(e)}")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': str(e)
            }))

    @database_sync_to_async
    def create_effect(self, data):
        try:
            message = Message.objects.get(id=data['message_id'])
            user = self.scope['user']
            
            # Check if user is a member of the conversation
            if not message.conversation.members.filter(user=user).exists():
                raise PermissionError("You are not a member of this conversation")
            
            # Create effect
            effect = MessageEffect.objects.create(
                message=message,
                effect_type=data['effect_type'],
                intensity=data.get('intensity', 1)
            )
            
            # Create a request object for the serializer
            request = HttpRequest()
            request.user = user
            
            return MessageEffectSerializer(effect, context={'request': request}).data
            
        except Exception as e:
            print(f"Error creating effect: {str(e)}")
            raise

    async def handle_effect(self, data):
        try:
            print("\n=== Handling Effect ===")
            print(f"Data: {data}")
            
            # Create effect
            effect_data = await self.create_effect(data)
            print(f"Created effect: {effect_data}")
            
            # Send effect to group
            await self.channel_layer.group_send(
                f"chat_{self.conversation_id}",
                {
                    'type': 'effect',
                    'effect': effect_data
                }
            )
            print("Effect sent to group")
            
        except Exception as e:
            print(f"Error handling effect: {str(e)}")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': str(e)
            }))

    @database_sync_to_async
    def create_link_preview(self, data):
        try:
            message = Message.objects.get(id=data['message_id'])
            user = self.scope['user']
            
            # Check if user is a member of the conversation
            if not message.conversation.members.filter(user=user).exists():
                raise PermissionError("You are not a member of this conversation")
            
            # Create link preview
            preview = LinkPreview.objects.create(
                message=message,
                url=data['url'],
                title=data['title'],
                description=data['description'],
                image_url=data.get('image_url')
            )
            
            # Create a request object for the serializer
            request = HttpRequest()
            request.user = user
            
            return LinkPreviewSerializer(preview, context={'request': request}).data
            
        except Exception as e:
            print(f"Error creating link preview: {str(e)}")
            raise

    async def handle_link_preview(self, data):
        try:
            print("\n=== Handling Link Preview ===")
            print(f"Data: {data}")
            
            # Create link preview
            preview_data = await self.create_link_preview(data)
            print(f"Created link preview: {preview_data}")
            
            # Send preview to group
            await self.channel_layer.group_send(
                f"chat_{self.conversation_id}",
                {
                    'type': 'link_preview',
                    'preview': preview_data
                }
            )
            print("Link preview sent to group")
            
        except Exception as e:
            print(f"Error handling link preview: {str(e)}")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': str(e)
            }))

    async def chat_message(self, event):
        try:
            print("\n=== Sending Chat Message ===")
            print(f"Event: {event}")
            
            # Send message to WebSocket
            await self.send(text_data=json.dumps({
                'type': 'chat_message',
                'message': event['message']
            }))
            print("Message sent to WebSocket")
            
        except Exception as e:
            print(f"Error sending chat message: {str(e)}")

    async def reaction(self, event):
        try:
            print("\n=== Sending Reaction ===")
            print(f"Event: {event}")
            
            # Send reaction to WebSocket
            await self.send(text_data=json.dumps({
                'type': 'reaction',
                'reaction': event['reaction']
            }))
            print("Reaction sent to WebSocket")
            
        except Exception as e:
            print(f"Error sending reaction: {str(e)}")

    async def reaction_removed(self, event):
        try:
            print("\n=== Sending Reaction Removal ===")
            print(f"Event: {event}")
            
            # Send reaction removal to WebSocket
            await self.send(text_data=json.dumps({
                'type': 'reaction_removed',
                'message_id': event['message_id'],
                'user_id': event['user_id'],
                'emoji': event['emoji']
            }))
            print("Reaction removal sent to WebSocket")
            
        except Exception as e:
            print(f"Error sending reaction removal: {str(e)}")

    async def thread_message(self, event):
        try:
            print("\n=== Sending Thread Message ===")
            print(f"Event: {event}")
            
            # Send thread message to WebSocket
            await self.send(text_data=json.dumps({
                'type': 'thread_message',
                'message': event['message']
            }))
            print("Thread message sent to WebSocket")
            
        except Exception as e:
            print(f"Error sending thread message: {str(e)}")

    async def effect(self, event):
        try:
            print("\n=== Sending Effect ===")
            print(f"Event: {event}")
            
            # Send effect to WebSocket
            await self.send(text_data=json.dumps({
                'type': 'effect',
                'effect': event['effect']
            }))
            print("Effect sent to WebSocket")
            
        except Exception as e:
            print(f"Error sending effect: {str(e)}")

    async def link_preview(self, event):
        try:
            print("\n=== Sending Link Preview ===")
            print(f"Event: {event}")
            
            # Send link preview to WebSocket
            await self.send(text_data=json.dumps({
                'type': 'link_preview',
                'preview': event['preview']
            }))
            print("Link preview sent to WebSocket")
            
        except Exception as e:
            print(f"Error sending link preview: {str(e)}")

    @database_sync_to_async
    def update_thread(self, thread_id, message_id):
        try:
            thread = MessageThread.objects.get(id=thread_id)
            message = Message.objects.get(id=message_id)
            thread.messages.add(message)
            thread.last_reply_at = timezone.now()
            thread.save()
        except Exception as e:
            logger.error(f"Error updating thread: {str(e)}", exc_info=True)
            raise

    async def handle_edit_message(self, data):
        try:
            message_id = data.get('message_id')
            new_content = data.get('content')
            
            if not message_id or not new_content:
                await self.send(text_data=json.dumps({
                    'type': 'error',
                    'message': 'Message ID and content are required'
                }))
                return

            message = await self.edit_message(message_id, new_content)
            
            await self.channel_layer.group_send(
                f"chat_{self.conversation_id}",
                {
                    'type': 'message_edited',
                    'message': message
                }
            )

        except Exception as e:
            logger.error(f"Error editing message: {str(e)}", exc_info=True)
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Failed to edit message'
            }))

    @database_sync_to_async
    def edit_message(self, message_id, new_content):
        try:
            message = Message.objects.get(id=message_id, sender=self.scope['user'])
            message.content = new_content
            message.is_edited = True
            message.save()
            return MessageSerializer(message).data
        except Message.DoesNotExist:
            raise Exception("Message not found or you don't have permission to edit it")

    async def handle_pin_message(self, data):
        try:
            message_id = data.get('message_id')
            is_pinned = data.get('is_pinned', True)
            
            if not message_id:
                await self.send(text_data=json.dumps({
                    'type': 'error',
                    'message': 'Message ID is required'
                }))
                return

            message = await self.pin_message(message_id, is_pinned)
            
            await self.channel_layer.group_send(
                f"chat_{self.conversation_id}",
                {
                    'type': 'message_pinned',
                    'message': message
                }
            )

        except Exception as e:
            logger.error(f"Error pinning message: {str(e)}", exc_info=True)
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Failed to pin/unpin message'
            }))

    @database_sync_to_async
    def pin_message(self, message_id, is_pinned):
        try:
            message = Message.objects.get(id=message_id)
            # Check if user has permission to pin messages
            member = ConversationMember.objects.get(
                conversation=message.conversation,
                user=self.scope['user']
            )
            if not member.has_permission('pin_messages'):
                raise Exception("You don't have permission to pin messages")
            
            message.is_pinned = is_pinned
            message.save()
            return MessageSerializer(message).data
        except Message.DoesNotExist:
            raise Exception("Message not found")

    async def handle_forward_message(self, data):
        try:
            message_id = data.get('message_id')
            target_conversation_id = data.get('target_conversation_id')
            
            if not message_id or not target_conversation_id:
                await self.send(text_data=json.dumps({
                    'type': 'error',
                    'message': 'Message ID and target conversation ID are required'
                }))
                return

            message = await self.forward_message(message_id, target_conversation_id)
            
            # Send to both source and target conversations
            await self.channel_layer.group_send(
                f"chat_{self.conversation_id}",
                {
                    'type': 'message_forwarded',
                    'message': message
                }
            )
            
            target_room = f"chat_{target_conversation_id}"
            await self.channel_layer.group_send(
                target_room,
                {
                    'type': 'chat_message',
                    'message': message
                }
            )

        except Exception as e:
            logger.error(f"Error forwarding message: {str(e)}", exc_info=True)
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Failed to forward message'
            }))

    @database_sync_to_async
    def forward_message(self, message_id, target_conversation_id):
        try:
            original_message = Message.objects.get(id=message_id)
            target_conversation = Conversation.objects.get(id=target_conversation_id)
            
            # Check if user has access to target conversation
            if not target_conversation.is_participant(self.scope['user']):
                raise Exception("You don't have access to the target conversation")
            
            # Create forwarded message
            forwarded_message = Message.objects.create(
                conversation=target_conversation,
                sender=self.scope['user'],
                content=original_message.content,
                message_type=original_message.message_type,
                is_forwarded=True,
                original_message=original_message
            )
            
            # Copy attachments
            for file in original_message.files.all():
                forwarded_message.files.add(file)
            
            return MessageSerializer(forwarded_message).data
        except Message.DoesNotExist:
            raise Exception("Original message not found")
        except Conversation.DoesNotExist:
            raise Exception("Target conversation not found")

    async def message_edited(self, event):
        await self.send(text_data=json.dumps({
            'type': 'message_edited',
            'message': event['message']
        }))

    async def message_pinned(self, event):
        await self.send(text_data=json.dumps({
            'type': 'message_pinned',
            'message': event['message']
        }))

    async def message_forwarded(self, event):
        await self.send(text_data=json.dumps({
            'type': 'message_forwarded',
            'message': event['message']
        }))

    async def message_effect_added(self, event):
        await self.send(text_data=json.dumps({
            'type': 'message_effect_added',
            'effect': event['effect']
        }))

    async def typing_status(self, event):
        # Send typing status to WebSocket
        await self.send(text_data=json.dumps({
            'type': 'typing',
            'user_id': event['user_id'],
            'is_typing': event['is_typing']
        }))

    async def message_status(self, event):
        # Send message status to WebSocket
        await self.send(text_data=json.dumps({
            'type': 'message_status',
            'message_id': event['message_id'],
            'status': event['status']
        }))

    async def read_status(self, event):
        # Send read status to WebSocket
        await self.send(text_data=json.dumps({
            'type': 'read',
            'message_id': event['message_id'],
            'user_id': event['user_id']
        }))

        # Update message status in database
        await self.mark_messages_as_read(event['message_ids'])

    async def handle_ping(self, data):
        await self.send(text_data=json.dumps({
            'type': 'pong',
            'timestamp': timezone.now().timestamp()
        }))

    async def handle_typing(self, data):
        try:
            is_typing = data.get('is_typing', True)
            
            await self.channel_layer.group_send(
                f"chat_{self.conversation_id}",
                {
                    'type': 'typing_status',
                    'user_id': self.scope['user'].id,
                    'is_typing': is_typing
                }
            )
        except Exception as e:
            logger.error(f"Error handling typing status: {str(e)}", exc_info=True)

    async def handle_read(self, data):
        try:
            message_ids = data.get('message_ids', [])
            if not message_ids:
                return

            await self.channel_layer.group_send(
                f"chat_{self.conversation_id}",
                {
                    'type': 'read_status',
                    'message_ids': message_ids,
                    'user_id': self.scope['user'].id
                }
            )
        except Exception as e:
            logger.error(f"Error handling read status: {str(e)}", exc_info=True)

    @database_sync_to_async
    def mark_messages_as_read(self, message_ids):
        try:
            messages = Message.objects.filter(
                id__in=message_ids,
                conversation_id=self.conversation_id
            )
            
            for message in messages:
                message.status = 'read'
                message.save()
                
            # Update conversation member's last_read and reset unread count
            member = ConversationMember.objects.get(
                conversation_id=self.conversation_id,
                user=self.scope['user']
            )
            member.last_read = timezone.now()
            member.unread_count = 0  # Reset unread count when messages are read
            member.save()
            
        except Exception as e:
            logger.error(f"Error marking messages as read: {str(e)}", exc_info=True)

    async def send_error(self, message):
        await self.send(text_data=json.dumps({
            'type': 'error',
            'message': message
        })) 