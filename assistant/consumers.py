import json
import uuid
import logging
import os
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import AccessToken
from .models import ChatMessage, AssistantMemory, InterestAlchemy, PostSuggestion, CommunitySuggestion, ConnectionSuggestion, ContentRecommendation, SkillRecommendation, RatingPattern, AIRatingInsight, CommunityScore
from community.models import Community, PersonalPost, CommunityPost, Comment
from django.db.models import Q, Count
from django.db.models.functions import Random
import asyncio
from functools import partial
import azure.cognitiveservices.speech as speechsdk
import base64
import urllib.parse
from django.utils import timezone
from .serializers import ChatMessageSerializer
from django.conf import settings
import queue
import threading
from notifications.models import Notification
from mistralai import Mistral

User = get_user_model()
logger = logging.getLogger(__name__)

# Initialize Mistral client
mistral_client = Mistral(api_key="4Q6ICI5AWFuwfuD5bu4cpPTWOKRbyDEY")

def test_mistral_connection():
    """Test the Mistral API connection"""
    try:
        logger.info("Testing Mistral API connection")
        response = mistral_client.chat.complete(
            model="mistral-large-latest",
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Hello, are you working?"}
            ]
        )
        logger.info("Mistral API test successful")
        return True
    except Exception as e:
        logger.error(f"Mistral API test failed: {str(e)}", exc_info=True)
        return False

# Initialize Azure Speech Service (optional)
speech_config = None
try:
    speech_key = os.getenv("AZURE_SPEECH_KEY", "your_speech_key_here")
    speech_region = os.getenv("AZURE_SPEECH_REGION", "eastus")
    if speech_key and speech_key != "your_speech_key_here":
        speech_config = speechsdk.SpeechConfig(subscription=speech_key, region=speech_region)
        speech_config.speech_synthesis_voice_name = "en-US-JennyNeural"
        logger.info("Azure Speech Service initialized successfully")
    else:
        logger.warning("Azure Speech Service not initialized - missing or invalid speech key")
except Exception as e:
    logger.error(f"Error initializing Azure Speech Service: {str(e)}")
    speech_config = None

class AssistantChatConsumer(AsyncWebsocketConsumer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = None
        self.conversation_id = None
        self.user_context = None
        self.token_validation_timeout = 5  # seconds
        self.personality_tags = []
        self._cleanup_task = None
        self._heartbeat_task = None
        self._keep_alive_task = None
        self._is_shutting_down = False
        self._connection_lost = False
        self._should_stop_streaming = False
        self._streaming_thread = None

    async def connect(self):
        if self._is_shutting_down:
            logger.warning("Rejecting new connection during shutdown")
            await self.close(code=1012)  # Service Restart
            return

        try:
            logger.info("New Assistant WebSocket connection attempt")
            
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

            # Get user's personality tags
            self.personality_tags = await self.get_user_personality_tags()
            logger.info(f"User {self.user.username} authenticated successfully with personality tags: {self.personality_tags}")

            # Accept the connection
            await self.accept()
            logger.info("WebSocket connection accepted")

            # Initialize conversation ID
            self.conversation_id = f"conv_{uuid.uuid4()}"
            logger.info(f"Generated conversation ID: {self.conversation_id}")

            # Get user context
            try:
                self.user_context = await self.get_user_context()
                logger.info("User context retrieved successfully")
            except Exception as e:
                logger.error(f"Error getting user context: {str(e)}", exc_info=True)
                # Don't close the connection if context loading fails
                # Just log the error and continue

            # Send initial connection success message
            await self.send(text_data=json.dumps({
                'type': 'auth_success',
                'message': 'Successfully connected to assistant',
                'conversation_id': self.conversation_id,
                'personality_tags': self.personality_tags
            }))

            # Start heartbeat
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

        except Exception as e:
            logger.error(f"Error in connect: {str(e)}", exc_info=True)
            await self.close(code=1011)  # Internal error

    async def disconnect(self, close_code):
        logger.info(f"Assistant WebSocket disconnected with code: {close_code}")
        self._connection_lost = True
        await self._cleanup()

    async def _cleanup(self):
        """Clean up resources and cancel tasks"""
        try:
            # Cancel heartbeat task
            if self._heartbeat_task and not self._heartbeat_task.done():
                self._heartbeat_task.cancel()
                try:
                    await self._heartbeat_task
                except asyncio.CancelledError:
                    pass
                except Exception as e:
                    logger.error(f"Error cancelling heartbeat task: {str(e)}")

            # Cancel keep-alive task
            if self._keep_alive_task and not self._keep_alive_task.done():
                self._keep_alive_task.cancel()
                try:
                    await self._keep_alive_task
                except asyncio.CancelledError:
                    pass
                except Exception as e:
                    logger.error(f"Error cancelling keep-alive task: {str(e)}")

            # Clear all tasks
            self._heartbeat_task = None
            self._keep_alive_task = None
            self._cleanup_task = None

        except Exception as e:
            logger.error(f"Error during cleanup: {str(e)}", exc_info=True)

    async def _heartbeat_loop(self):
        """Send periodic heartbeats to keep the connection alive"""
        try:
            while not self._is_shutting_down and not self._connection_lost:
                await asyncio.sleep(30)  # Send heartbeat every 30 seconds
                if self.scope["type"] == "websocket" and not self._is_shutting_down:
                    try:
                        await self.send(text_data=json.dumps({
                            'type': 'heartbeat',
                            'timestamp': timezone.now().timestamp()
                        }))
                    except Exception as e:
                        logger.error(f"Error sending heartbeat: {str(e)}")
                        break
        except asyncio.CancelledError:
            logger.info("Heartbeat loop cancelled")
        except Exception as e:
            logger.error(f"Error in heartbeat loop: {str(e)}", exc_info=True)

    async def receive(self, text_data):
        if self._is_shutting_down:
            logger.warning("Ignoring message during shutdown")
            return

        try:
            data = json.loads(text_data)
            message_type = data.get('type')

            if message_type == 'authenticate':
                # Already authenticated in connect(), just send success response
                await self.send(text_data=json.dumps({
                    'type': 'auth_success',
                    'message': 'Successfully authenticated with assistant',
                    'conversation_id': self.conversation_id,
                    'personality_tags': self.personality_tags
                }))
            elif message_type == 'chat_message':
                await self.handle_chat_message(data)
            elif message_type == 'audio_message':
                await self.handle_audio_message(data)
            elif message_type == 'heartbeat':
                # Send pong response
                await self.send(text_data=json.dumps({
                    'type': 'pong',
                    'timestamp': data.get('timestamp')
                }))
            elif message_type == 'stop_stream':
                self._should_stop_streaming = True
                if self._streaming_thread and self._streaming_thread.is_alive():
                    # The thread will check _should_stop_streaming and stop gracefully
                    logger.info("Stop stream request received")
                    await self.send(text_data=json.dumps({
                        'type': 'stream_complete',
                        'conversation_id': self.conversation_id
                    }))
            else:
                logger.warning(f"Unknown message type: {message_type}")

        except json.JSONDecodeError:
            logger.error("Invalid JSON received")
        except Exception as e:
            logger.error(f"Error in receive: {str(e)}", exc_info=True)

    @database_sync_to_async
    def get_or_create_memory(self):
        """Get or create AssistantMemory for the user."""
        if not self.user:
            return None
        try:
            memory, created = AssistantMemory.objects.get_or_create(user=self.user)
            if created:
                logger.info(f"Created new AssistantMemory for user {self.user.username}")
            return memory
        except Exception as e:
            logger.error(f"Error getting/creating memory for user {self.user.id}: {str(e)}", exc_info=True)
            return None

    @database_sync_to_async
    def save_message(self, message, is_user_message, conversation_id=None):
        """Save a chat message to the database."""
        if not self.user:
            return None

        # Initialize default context
        context = {}
        memory = None

        try:
            # Get or create memory for user
            memory = AssistantMemory.objects.get_or_create(user=self.user)[0]
            if not memory:
                logger.error(f"Failed to get/create memory for user {self.user.username}")
                return None

            # Get context from user's memory
            context = {
                'personality_profile': memory.personality_profile,
                'learning_data': memory.learning_data,
                'context_window': memory.context_window,
                'community_engagement': memory.community_engagement,
                'content_preferences': memory.content_preferences,
                'interaction_patterns': memory.interaction_patterns,
                'personality_tags': self.personality_tags
            }

            # Ensure is_user_message is a boolean
            is_user_message = bool(is_user_message)

            # Create message with context and metadata
            chat_message = ChatMessage.objects.create(
                user=self.user,
                message=message,
                is_user_message=is_user_message,
                conversation_id=conversation_id,
                context=context,
                metadata={
                    'analysis': {
                        'personality_match': context.get('personality_profile', {}),
                        'learning_relevance': context.get('learning_data', {}),
                        'engagement_context': context.get('community_engagement', {}),
                        'preference_alignment': context.get('content_preferences', {}),
                        'personality_tags': self.personality_tags
                    },
                    'context': context
                }
            )

            # Update the memory with the new message
            try:
                memory.update_context_window(message, is_user_message)
                logger.info(f"Updated context window for user {self.user.username}")
            except Exception as e:
                logger.error(f"Error updating context window: {str(e)}", exc_info=True)

            return chat_message

        except Exception as e:
            logger.error(f"Error saving message: {str(e)}", exc_info=True)
            return None

    @database_sync_to_async
    def get_chat_history(self, conversation_id):
        """Get all chat messages for a conversation from the database."""
        try:
            messages = ChatMessage.objects.filter(
                conversation_id=conversation_id
            ).order_by('timestamp')
            
            # Log the number of messages found
            logger.info(f"Found {messages.count()} messages in chat history for conversation {conversation_id}")
            
            # Convert messages to the format expected by the AI model
            formatted_messages = [
                {
                    "role": "user" if msg.is_user_message else "assistant",
                    "content": msg.message
                }
                for msg in messages
            ]
            
            # Log the formatted messages for debugging
            logger.info(f"Formatted chat history: {json.dumps(formatted_messages, indent=2)}")
            
            return formatted_messages
        except Exception as e:
            logger.error(f"Error getting chat history: {str(e)}", exc_info=True)
            return []

    async def handle_chat_message(self, data):
        try:
            message = data.get('message', '').strip()
            if not message:
                await self.send(text_data=json.dumps({
                    'type': 'error',
                    'message': 'Message cannot be empty'
                }))
                return

            # Get or create conversation ID
            conversation_id = data.get('conversation_id')
            if not conversation_id:
                # Use a deterministic conversation_id per user for persistent chat history
                conversation_id = f"user_{self.user.id}_default"
                self.conversation_id = conversation_id
            else:
                self.conversation_id = conversation_id

            try:
                # Save user message
                await self.save_message(message, True, conversation_id)
                
                # Get chat history from database
                chat_history = await self.get_chat_history(conversation_id)
                logger.info(f"Retrieved {len(chat_history)} messages from chat history")

                # Pass all previous chat messages to the assistant
                response = await self.process_message(message, chat_history)
                
                # Save assistant response
                await self.save_message(response, False, conversation_id)
                
                # Send response back to client
                await self.send(text_data=json.dumps({
                    'type': 'chat_message',
                    'message': response,
                    'conversation_id': conversation_id
                }))
            except Exception as e:
                logger.error(f"Error processing message: {str(e)}", exc_info=True)
                error_message = "I'm having trouble processing your message. Please try again."
                await self.send(text_data=json.dumps({
                    'type': 'error',
                    'message': error_message
                }))

        except Exception as e:
            logger.error(f"Error handling chat message: {str(e)}", exc_info=True)
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Error processing message'
            }))

    @database_sync_to_async
    def get_user_notifications(self):
        """Get user's recent notifications from the notifications app."""
        if not self.user:
            return []
        try:
            # Get notifications from the notifications app
            notifications = Notification.objects.filter(
                recipient=self.user
            ).select_related('sender').order_by('-created_at')[:20]  # Get last 20 notifications
            
            # Format notifications
            formatted_notifications = []
            for notif in notifications:
                notification_data = {
                    'type': notif.notification_type,
                    'title': notif.title,
                    'message': notif.message,
                    'is_read': notif.is_read,
                    'created_at': notif.created_at.isoformat(),
                    'sender': notif.sender.get_full_name() if notif.sender else None,
                    'data': notif.data
                }
                
                # Add content type information if available
                if notif.content_type:
                    notification_data['content_type'] = {
                        'app_label': notif.content_type.app_label,
                        'model': notif.content_type.model
                    }
                
                formatted_notifications.append(notification_data)
            
            logger.info(f"Retrieved {len(formatted_notifications)} notifications for user {self.user.id}")
            return formatted_notifications
            
        except Exception as e:
            logger.error(f"Error getting notifications for user {self.user.id}: {str(e)}", exc_info=True)
            return []

    async def process_message(self, message, chat_history=None):
        """Process a message and generate a response."""
        try:
            # Reset stop flag for new message
            self._should_stop_streaming = False
            
            # Get or create memory for user
            memory = await self.get_or_create_memory()
            if not memory:
                logger.error(f"Failed to get/create memory for user {self.user.username}")
                return "I'm having trouble accessing your memory. Please try again in a moment."
            
            # Get user's memory, context, and notifications
            memory_data = await self.get_user_context()
            notifications = await self.get_user_notifications()
            friends = await self.get_friends()
            existing_suggestions = await self.get_existing_friend_suggestions(limit=5)
            alchemy_suggestions = await self.get_alchemy_friend_suggestions(limit=5)
            logger.info("Successfully retrieved user context, notifications, friends, and suggestions")
            
            # Create system message with user context
            system_message = {
                "role": "system",
                "content": f"""You are an AI assistant with access to the user's context, history, notifications, friends, and suggestions.
                
                User's personality tags:
                {json.dumps(self.personality_tags, indent=2)}
                
                User's recent posts:
                {json.dumps(memory_data.get('posts', []), indent=2)}
                
                User's rating insights:
                {json.dumps(memory_data.get('rating_insights', {}), indent=2)}
                
                User's personality profile:
                {json.dumps(memory_data.get('personality_profile', {}), indent=2)}
                
                User's learning data:
                {json.dumps(memory_data.get('learning_data', {}), indent=2)}
                
                User's recent notifications:
                {json.dumps(notifications, indent=2)}
                
                User's friends (connections):
                {json.dumps(friends, indent=2)}
                
                User's existing friend suggestions:
                {json.dumps(existing_suggestions, indent=2)}
                
                User's alchemy (AI) friend suggestions:
                {json.dumps(alchemy_suggestions, indent=2)}
                
                Provide helpful, friendly responses that take into account the user's personality tags, posts, rating insights, context, notifications, friends, and suggestions.
                When discussing content, consider the user's rating patterns and preferences to provide more personalized insights.
                If there are unread notifications that might be relevant to the conversation, mention them.
                For notifications about connections, communities, messages, achievements, or events, provide appropriate context and suggestions.
                When discussing social features, consider the user's friends and suggested connections.
                Maintain context from previous messages in the conversation.
                Always reference previous messages when relevant to provide more coherent and contextual responses.
                
                When presenting tabular data, always use valid GitHub-flavored markdown table syntax. For example:
                | Column 1 | Column 2 |
                |----------|----------|
                | Value 1  | Value 2  |
                Do not add extra pipes or break the markdown format.
                """
            }
            logger.info("Created system message")

            # Prepare messages array with chat history
            messages = [system_message]
            
            # Add chat history if available
            if chat_history:
                logger.info(f"Adding {len(chat_history)} messages from chat history")
                messages.extend(chat_history)
            else:
                logger.warning("No chat history available")
            
            # Add current user message
            messages.append({
                "role": "user",
                "content": message
            })
            
            # Log the full messages array for debugging
            logger.info(f"Full messages array: {json.dumps(messages, indent=2)}")

            try:
                logger.info("Starting streaming AI response (threaded)")
                full_response = ""
                await self.send(text_data=json.dumps({
                    'type': 'typing_start',
                    'conversation_id': self.conversation_id
                }))

                q = queue.Queue()
                def stream_in_thread():
                    try:
                        try:
                            for chunk in mistral_client.chat.stream(
                                model="mistral-large-latest",
                                messages=messages,
                                temperature=0.7,
                                top_p=1.0
                            ):
                                if self._should_stop_streaming:
                                    logger.info("Streaming stopped by user request")
                                    break
                                q.put(chunk)
                        except Exception as e:
                            logger.error(f"Unexpected error in Mistral streaming: {str(e)}", exc_info=True)
                            q.put(e)
                    finally:
                        q.put(None)
                
                self._streaming_thread = threading.Thread(target=stream_in_thread)
                self._streaming_thread.start()

                while True:
                    chunk = await asyncio.to_thread(q.get)
                    if chunk is None:
                        break
                    # If chunk is an exception, handle and send error to frontend
                    if isinstance(chunk, Exception):
                        error_message = "I'm having trouble generating a response right now. Please try again in a moment."
                        logger.error(f"AI streaming error: {str(chunk)}", exc_info=True)
                        await self.send(text_data=json.dumps({
                            'type': 'error',
                            'message': error_message,
                            'conversation_id': self.conversation_id
                        }))
                        return error_message
                    if hasattr(chunk.data.choices[0].delta, 'content') and chunk.data.choices[0].delta.content:
                        content = chunk.data.choices[0].delta.content
                        full_response += content
                        await self.send(text_data=json.dumps({
                            'type': 'stream_chunk',
                            'content': content,
                            'conversation_id': self.conversation_id
                        }))

                await self.send(text_data=json.dumps({
                    'type': 'stream_complete',
                    'conversation_id': self.conversation_id
                }))
                
                if full_response:  # Only save if we got some response
                    await self.save_message(full_response, False, self.conversation_id)
                return full_response

            except Exception as e:
                logger.error(f"Error getting AI response: {str(e)}", exc_info=True)
                logger.error(f"System message: {json.dumps(system_message)}")
                logger.error(f"Messages array: {json.dumps(messages)}")
                await self.send(text_data=json.dumps({
                    'type': 'error',
                    'message': "I'm having trouble generating a response right now. Please try again in a moment.",
                    'conversation_id': self.conversation_id
                }))
                return "I'm having trouble generating a response right now. Please try again in a moment."

        except Exception as e:
            logger.error(f"Error in process_message: {str(e)}", exc_info=True)
            return "I apologize, but I'm having trouble processing your request right now. Please try again in a moment."

    @database_sync_to_async
    def get_user_from_token(self, token):
        """Get user from token in a sync context."""
        try:
            access_token = AccessToken(token)
            user_id = access_token['user_id']
            return User.objects.get(id=user_id)
        except Exception as e:
            logger.error(f"Error getting user from token: {str(e)}", exc_info=True)
            return None

    @database_sync_to_async
    def get_user_posts(self):
        """Get user's personal and community posts."""
        if not self.user:
            return []
        try:
            # Get personal posts
            personal_posts = PersonalPost.objects.filter(
                author=self.user
            ).select_related('author').prefetch_related('topics')[:5]  # Get last 5 posts
            
            # Get community posts
            community_posts = CommunityPost.objects.filter(
                author=self.user
            ).select_related('author', 'community').prefetch_related('topics')[:5]  # Get last 5 posts
            
            # Combine and format posts
            posts = []
            for post in list(personal_posts) + list(community_posts):
                posts.append({
                    'id': post.id,
                    'title': post.title,
                    'content': post.content,
                    'visibility': post.visibility,
                    'created_at': post.created_at.isoformat(),
                    'topics': [{'name': topic.name, 'color': topic.color} for topic in post.topics.all()],
                    'is_personal': isinstance(post, PersonalPost),
                    'community': post.community.name if hasattr(post, 'community') and post.community else None
                })
            
            return posts
        except Exception as e:
            logger.error(f"Error getting posts for user {self.user.id}: {str(e)}")
            return []

    @database_sync_to_async
    def get_user_rating_insights(self):
        """Get user's rating patterns and insights."""
        if not self.user:
            return {}
        try:
            # Get user's rating patterns
            rating_patterns = RatingPattern.objects.filter(
                user=self.user
            ).values('pattern_type', 'confidence', 'pattern_data')
            
            # Get AI insights for user's posts
            post_insights = AIRatingInsight.objects.filter(
                content_type__model__in=['personalpost', 'communitypost'],
                object_id__in=PersonalPost.objects.filter(author=self.user).values_list('id', flat=True) |
                             CommunityPost.objects.filter(author=self.user).values_list('id', flat=True)
            ).values('sentiment_score', 'rating_patterns', 'quality_indicators', 'engagement_prediction')
            
            # Get community scores for user's posts
            community_scores = CommunityScore.objects.filter(
                models.Q(personal_post__author=self.user) | models.Q(community_post__author=self.user)
            ).values('average_score', 'engagement_score', 'quality_score', 'trending_score')
            
            return {
                'rating_patterns': list(rating_patterns),
                'post_insights': list(post_insights),
                'community_scores': list(community_scores)
            }
        except Exception as e:
            logger.error(f"Error getting rating insights for user {self.user.id}: {str(e)}")
            return {}

    @database_sync_to_async
    def get_user_context(self):
        """Get user's context including memory, posts, and rating insights."""
        if not self.user:
            logger.error("No user found in get_user_context")
            return {}

        try:
            memory = AssistantMemory.objects.get(user=self.user)
            
            # Get user's posts synchronously since we're in a sync context
            try:
                # Get personal posts
                personal_posts = PersonalPost.objects.filter(
                    author=self.user
                ).select_related('author').prefetch_related('topics')[:5]  # Get last 5 posts
                
                # Get community posts
                community_posts = CommunityPost.objects.filter(
                    author=self.user
                ).select_related('author', 'community').prefetch_related('topics')[:5]  # Get last 5 posts
                
                # Combine and format posts
                posts = []
                for post in list(personal_posts) + list(community_posts):
                    posts.append({
                        'id': post.id,
                        'title': post.title,
                        'content': post.content,
                        'visibility': post.visibility,
                        'created_at': post.created_at.isoformat(),
                        'topics': [{'name': topic.name, 'color': topic.color} for topic in post.topics.all()],
                        'is_personal': isinstance(post, PersonalPost),
                        'community': post.community.name if hasattr(post, 'community') and post.community else None
                    })
            except Exception as e:
                logger.error(f"Error getting posts for user {self.user.id}: {str(e)}")
                posts = []

            return {
                'memory': {
                    'personality_profile': memory.personality_profile,
                    'learning_data': memory.learning_data,
                    'context_window': memory.context_window,
                    'community_engagement': memory.community_engagement,
                    'content_preferences': memory.content_preferences,
                    'interaction_patterns': memory.interaction_patterns,
                    'personality_tags': self.personality_tags
                },
                'posts': posts,
                'rating_insights': {
                    'patterns': memory.rating_patterns if hasattr(memory, 'rating_patterns') else {},
                    'preferences': memory.rating_preferences if hasattr(memory, 'rating_preferences') else {},
                    'ai_insights': memory.ai_insights if hasattr(memory, 'ai_insights') else []
                }
            }
        except Exception as e:
            logger.error(f"Error getting user context: {str(e)}")
            return {}

    @database_sync_to_async
    def get_suggested_friends(self):
        """Get suggested friends based on common interests, skills, and connections"""
        if not self.user:
            logger.error("No user found for suggested friends")
            return []

        try:
            logger.info(f"Getting suggested friends for user {self.user.username}")
            
            # Get user's skills and interests directly from related models
            user_skills = set(self.user.skills.all().values_list('name', flat=True))
            user_interests = set(self.user.interests.all().values_list('name', flat=True))
            logger.info(f"User skills: {list(user_skills)}")
            logger.info(f"User interests: {list(user_interests)}")
            
            # Ge
            following = set(self.user.following.all().values_list('following_user', flat=True))
            followers = set(self.user.followers.all().values_list('user', flat=True))
            current_connections = following.union(followers)
            logger.info(f"Current connections: {current_connections}")
            
            # Find potential connections based on skills and interests
            potential_connections = User.objects.exclude(
                id__in=list(current_connections) + [self.user.id]
            ).filter(
                Q(skills__name__in=user_skills) | Q(interests__name__in=user_interests)
            ).distinct()

            # Calculate connection strength for each potential connection
            suggestions = []
            for user in potential_connections[:5]:  # Limit to 5 suggestions
                common_skills = len(set(user.skills.all().values_list('name', flat=True)) & user_skills)
                common_interests = len(set(user.interests.all().values_list('name', flat=True)) & user_interests)
                connection_strength = min(100, (common_skills * 20) + (common_interests * 15))

                # Handle avatar URL
                avatar_url = "http://localhost:8000/media/avatars/profile-default-icon-2048x2045-u3j7s5nj.png"
                if user.avatar:
                    if user.avatar.name.startswith('http'):
                        avatar_url = user.avatar.name
                    else:
                        avatar_url = f"http://localhost:8000{user.avatar.url}"

                suggestions.append({
                    'id': str(user.id),
                        'username': user.username,
                    'name': f"{user.first_name or ''} {user.last_name or ''}".strip() or user.username,
                    'avatar': avatar_url,
                    'common_skills': list(set(user.skills.all().values_list('name', flat=True)) & user_skills),
                    'common_interests': list(set(user.interests.all().values_list('name', flat=True)) & user_interests),
                    'connection_strength': connection_strength
                })

            return suggestions

        except Exception as e:
            logger.error(f"Error getting suggested friends: {str(e)}", exc_info=True)
            return []

    @database_sync_to_async
    def get_user_memory(self):
        """Get user's assistant memory"""
        try:
            memory = AssistantMemory.objects.get(user=self.user)
            return {
                'personality_profile': memory.personality_profile,
                'learning_data': memory.learning_data,
                'context_window': memory.context_window,
                'message_history': memory.message_history,
                'community_engagement': memory.community_engagement,
                'content_preferences': memory.content_preferences,
                'interaction_patterns': memory.interaction_patterns
            }
        except AssistantMemory.DoesNotExist:
            # Create new memory for user
            memory = AssistantMemory.objects.create(user=self.user)
            logger.info(f"Created new AssistantMemory for user {self.user.username}")
            return {
                'personality_profile': {},
                'learning_data': {},
                'context_window': [],
                'message_history': [],
                'community_engagement': {},
                'content_preferences': {},
                'interaction_patterns': {}
            }

    @database_sync_to_async
    def get_user_personality_tags(self):
        """Get user's personality tags in a sync context."""
        if not self.user:
            return []
        try:
            tags = self.user.personality_tags.all()
            return [
                {
                    'id': tag.id,
                    'name': tag.name,
                    'color': tag.color
                }
                for tag in tags
            ]
        except Exception as e:
            logger.error(f"Error getting personality tags for user {self.user.id}: {str(e)}")
            return [] 

    async def text_to_speech(self, text):
        """Convert text to speech using Azure's Text-to-Speech service"""
        try:
            # Create the speech synthesizer
            speech_synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config)
            
            # Convert text to speech
            result = speech_synthesizer.speak_text_async(text).get()
            
            if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
                # Get the audio data as bytes
                audio_data = result.audio_data
                # Convert to base64 for sending over WebSocket
                audio_base64 = base64.b64encode(audio_data).decode('utf-8')
                return audio_base64
            else:
                logger.error(f"Speech synthesis failed: {result.reason}")
                return None
                
        except Exception as e:
            logger.error(f"Error in text_to_speech: {str(e)}", exc_info=True)
            return None 

    @database_sync_to_async
    def get_existing_friend_suggestions(self, limit=5):
        """Fetch existing friend suggestions for the user from the connections app."""
        if not self.user:
            return []
        try:
            from connections.models import UserSuggestion
            suggestions = (
                UserSuggestion.objects.filter(user=self.user, is_active=True, is_rejected=False)
                .select_related('suggested_user')
                .order_by('-score')[:limit]
            )
            result = []
            for s in suggestions:
                user = s.suggested_user
                avatar_url = "http://localhost:8000/media/avatars/profile-default-icon-2048x2045-u3j7s5nj.png"
                if hasattr(user, 'avatar') and user.avatar:
                    if str(user.avatar).startswith('http'):
                        avatar_url = str(user.avatar)
                    else:
                        avatar_url = f"http://localhost:8000{user.avatar.url}"
                result.append({
                    'id': str(user.id),
                    'username': user.username,
                    'name': f"{user.first_name or ''} {user.last_name or ''}".strip() or user.username,
                    'avatar': avatar_url,
                    'score': s.score,
                    'common_interests': s.common_interests,
                    'mutual_connections': s.mutual_connections,
                    'match_highlights': s.match_highlights,
                })
            return result
        except Exception as e:
            logger.error(f"Error fetching existing friend suggestions: {str(e)}", exc_info=True)
            return []

    @database_sync_to_async
    def get_alchemy_friend_suggestions(self, limit=5):
        """Fetch alchemy (AI) friend suggestions for the user from the connections app."""
        if not self.user:
            return []
        try:
            from connections.models import UserSuggestion
            suggestions = (
                UserSuggestion.objects.filter(user=self.user, is_active=True, score__gte=60)
                .select_related('suggested_user')
                .order_by('-score')
            )
            result = []
            count = 0
            for s in suggestions:
                if not s.match_highlights:
                    continue
                user = s.suggested_user
                avatar_url = "http://localhost:8000/media/avatars/profile-default-icon-2048x2045-u3j7s5nj.png"
                if hasattr(user, 'avatar') and user.avatar:
                    if str(user.avatar).startswith('http'):
                        avatar_url = str(user.avatar)
                    else:
                        avatar_url = f"http://localhost:8000{user.avatar.url}"
                result.append({
                    'id': str(user.id),
                    'username': user.username,
                    'name': f"{user.first_name or ''} {user.last_name or ''}".strip() or user.username,
                    'avatar': avatar_url,
                    'score': s.score,
                    'common_interests': s.common_interests,
                    'mutual_connections': s.mutual_connections,
                    'match_highlights': s.match_highlights,
                })
                count += 1
                if count >= limit:
                    break
            return result
        except Exception as e:
            logger.error(f"Error fetching alchemy friend suggestions: {str(e)}", exc_info=True)
            return []

    @database_sync_to_async
    def get_friends(self):
        """Fetch the user's current friends (connections) from the connections app."""
        if not self.user:
            return []
        try:
            from connections.models import Connection
            connections = Connection.objects.filter(
                (models.Q(user1=self.user) | models.Q(user2=self.user)),
                is_active=True
            ).select_related('user1', 'user2')
            friends = []
            for conn in connections:
                friend = conn.user2 if conn.user1 == self.user else conn.user1
                avatar_url = "http://localhost:8000/media/avatars/profile-default-icon-2048x2045-u3j7s5nj.png"
                if hasattr(friend, 'avatar') and friend.avatar:
                    if str(friend.avatar).startswith('http'):
                        avatar_url = str(friend.avatar)
                    else:
                        avatar_url = f"http://localhost:8000{friend.avatar.url}"
                friends.append({
                    'id': str(friend.id),
                    'username': friend.username,
                    'name': f"{friend.first_name or ''} {friend.last_name or ''}".strip() or friend.username,
                    'avatar': avatar_url,
                    'connection_strength': conn.connection_strength,
                    'match_score': conn.match_score,
                    'mutual_connections_count': conn.mutual_connections_count,
                    'common_interests': conn.common_interests,
                    'connected_since': conn.created_at.isoformat() if conn.created_at else None,
                })
            return friends
        except Exception as e:
            logger.error(f"Error fetching friends (connections): {str(e)}", exc_info=True)
            return [] 