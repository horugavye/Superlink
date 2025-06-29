import json
import logging
import asyncio
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from rest_framework_simplejwt.tokens import AccessToken
from django.contrib.auth import get_user_model
from .models import Community, CommunityMember, Event, EventParticipant, Post, PostRating, Comment, CommentRating, Reply, ReplyRating, PersonalPost, CommunityPost
from django.db.models import Avg
import decimal
import jwt
from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder

logger = logging.getLogger(__name__)
User = get_user_model()

class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, decimal.Decimal):
            return float(obj)
        return super(DecimalEncoder, self).default(obj)

class CommunityConsumer(AsyncWebsocketConsumer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = None
        self.community = None
        self.room_group_name = None

    @database_sync_to_async
    def get_user_from_token(self, token):
        try:
            access_token = AccessToken(token)
            user_id = access_token['user_id']
            return User.objects.get(id=user_id)
        except Exception as e:
            logger.error(f"Token validation error: {str(e)}", exc_info=True)
            return None

    @database_sync_to_async
    def get_community(self, slug):
        try:
            return Community.objects.get(slug=slug)
        except Community.DoesNotExist:
            return None

    @database_sync_to_async
    def is_community_member(self, user, community):
        return CommunityMember.objects.filter(user=user, community=community).exists()

    async def connect(self):
        try:
            # Get token from query string and community slug from URL path
            query_string = self.scope['query_string'].decode()
            token = None
            
            for param in query_string.split('&'):
                if param.startswith('token='):
                    token = param.split('=')[1]

            # Get community slug from URL path
            community_slug = self.scope['url_route']['kwargs']['community_slug']

            if not token or not community_slug:
                logger.error("Missing token or community slug")
                await self.close(code=1008)
                return

            # Validate token and get user
            self.user = await self.get_user_from_token(token)
            if not self.user:
                logger.error("Failed to validate token or get user")
                await self.close(code=1008)
                return

            # Get community
            self.community = await self.get_community(community_slug)
            if not self.community:
                logger.error(f"Community not found: {community_slug}")
                await self.close(code=1008)
                return

            # Check if user is a member of the community
            is_member = await self.is_community_member(self.user, self.community)
            if not is_member and self.community.is_private:
                logger.error(f"User {self.user.id} is not a member of private community {community_slug}")
                await self.close(code=1008)
                return

            # Join community room group
            self.room_group_name = f"community_{community_slug}"
            await self.channel_layer.group_add(
                self.room_group_name,
                self.channel_name
            )
            await self.accept()
            logger.info(f"User {self.user.id} connected to community {community_slug}")

        except Exception as e:
            logger.error(f"Error during WebSocket connection: {str(e)}", exc_info=True)
            await self.close(code=1011)

    async def disconnect(self, close_code):
        try:
            if self.room_group_name:
                await self.channel_layer.group_discard(
                    self.room_group_name,
                    self.channel_name
                )
                logger.info(f"User {self.user.id if self.user else 'unknown'} disconnected from community {self.community.slug if self.community else 'unknown'}")
        except Exception as e:
            logger.error(f"Error during disconnect: {str(e)}", exc_info=True)

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            message_type = data.get('type')

            if message_type == 'subscribe_community':
                # Handle community subscription
                await self.handle_community_subscription(data)
            elif message_type == 'unsubscribe_community':
                # Handle community unsubscription
                await self.handle_community_unsubscription(data)
            else:
                logger.warning(f"Unknown message type: {message_type}")

        except json.JSONDecodeError as e:
            logger.error(f"Error decoding message: {str(e)}", exc_info=True)
        except Exception as e:
            logger.error(f"Error handling message: {str(e)}", exc_info=True)

    async def handle_community_subscription(self, data):
        """Handle community subscription request"""
        try:
            # Send initial community data
            await self.send(text_data=json.dumps({
                'type': 'community_subscribed',
                'community': {
                    'slug': self.community.slug,
                    'name': self.community.name,
                    'members_count': self.community.members_count,
                    'online_count': self.community.online_count
                }
            }, cls=DjangoJSONEncoder))
        except Exception as e:
            logger.error(f"Error handling community subscription: {str(e)}", exc_info=True)

    async def handle_community_unsubscription(self, data):
        """Handle community unsubscription request"""
        try:
            # Remove from room group
            if self.room_group_name:
                await self.channel_layer.group_discard(
                    self.room_group_name,
                    self.channel_name
                )
        except Exception as e:
            logger.error(f"Error handling community unsubscription: {str(e)}", exc_info=True)

    async def community_update(self, event):
        """Handle community updates"""
        try:
            await self.send(text_data=json.dumps({
                'type': 'community_updated',
                'data': event['data']
            }, cls=DjangoJSONEncoder))
        except Exception as e:
            logger.error(f"Error sending community update: {str(e)}", exc_info=True)

    async def member_update(self, event):
        """Handle member updates"""
        try:
            await self.send(text_data=json.dumps({
                'type': 'member_updated',
                'data': event['data']
            }, cls=DjangoJSONEncoder))
        except Exception as e:
            logger.error(f"Error sending member update: {str(e)}", exc_info=True)

    async def event_update(self, event):
        """Handle event updates"""
        try:
            await self.send(text_data=json.dumps({
                'type': 'event_updated',
                'data': event['data']
            }, cls=DjangoJSONEncoder))
        except Exception as e:
            logger.error(f"Error sending event update: {str(e)}", exc_info=True)

    async def post_update(self, event):
        """Handle post updates"""
        await self.send_json({
            'type': 'post_updated',
            'data': event['data']
        }, cls=DjangoJSONEncoder)

    async def role_update(self, event):
        """Handle member role changes"""
        await self.send_json({
            'type': 'role_updated',
            'data': event['data']
        }, cls=DjangoJSONEncoder)

    async def settings_update(self, event):
        """Handle community settings changes"""
        await self.send_json({
            'type': 'settings_updated',
            'data': event['data']
        }, cls=DjangoJSONEncoder)

    async def connection_update(self, event):
        """Handle member connection updates"""
        await self.send_json({
            'type': 'connection_updated',
            'data': event['data']
        }, cls=DjangoJSONEncoder)

    async def comment_update(self, event):
        """Handle comment updates"""
        await self.send_json({
            'type': 'comment_updated',
            'data': event['data']
        }, cls=DjangoJSONEncoder)

class PostConsumer(AsyncWebsocketConsumer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = None
        self.post_id = None
        self.is_personal = False
        self.room_group_name = None
        self._db_lock = asyncio.Lock()
        self._update_queue = asyncio.Queue()
        self._update_task = None
        self._last_rating = None

    @database_sync_to_async
    def get_user_from_token(self, token):
        try:
            access_token = AccessToken(token)
            user_id = access_token['user_id']
            return User.objects.get(id=user_id)
        except Exception as e:
            logger.error(f"Token validation error: {str(e)}", exc_info=True)
            return None

    @database_sync_to_async
    def get_post(self, post_id, is_personal):
        try:
            if is_personal:
                return PersonalPost.objects.get(id=post_id)
            else:
                return CommunityPost.objects.get(id=post_id)
        except (PersonalPost.DoesNotExist, CommunityPost.DoesNotExist):
            return None

    @database_sync_to_async
    def get_user_rating(self, post):
        try:
            if isinstance(post, PersonalPost):
                return PostRating.objects.filter(
                    personal_post=post,
                    user=self.user
                ).first()
            else:  # CommunityPost
                return PostRating.objects.filter(
                    community_post=post,
                    user=self.user
                ).first()
        except Exception as e:
            logger.error(f"Error getting user rating: {str(e)}", exc_info=True)
            return None

    @database_sync_to_async
    def update_post_rating(self, rating):
        try:
            post = self.get_post(self.post_id, self.is_personal)
            if not post:
                logger.error(f"Post {self.post_id} not found")
                return None
            
            # Get or create user's rating
            if self.is_personal:
                user_rating, created = PostRating.objects.get_or_create(
                    personal_post=post,
                    user=self.user,
                    defaults={'rating': rating}
                )
            else:
                user_rating, created = PostRating.objects.get_or_create(
                    community_post=post,
                    user=self.user,
                    defaults={'rating': rating}
                )
            
            if not created:
                user_rating.rating = rating
                user_rating.save()

            # Calculate new average rating
            if self.is_personal:
                ratings = PostRating.objects.filter(personal_post=post)
            else:
                ratings = PostRating.objects.filter(community_post=post)
            total_ratings = ratings.count()
            avg_rating = ratings.aggregate(Avg('rating'))['rating__avg'] or 0

            # Update post
            post.rating = avg_rating
            post.total_ratings = total_ratings
            post.save()

            return {
                'type': 'rating_update',
                'data': {
                    'post_id': self.post_id,
                    'rating': float(avg_rating),
                    'total_ratings': total_ratings,
                    'user_rating': float(rating)
                }
            }
        except Exception as e:
            logger.error(f"Error updating post rating: {str(e)}", exc_info=True)
            return None

    async def connect(self):
        try:
            # Get post ID and type from URL path
            self.post_id = self.scope['url_route']['kwargs']['post_id']
            # Check if the URL path contains 'personal' to determine if it's a personal post
            self.is_personal = 'personal' in self.scope['path']
            self.room_group_name = f'post_{self.post_id}'

            # Get token from query string
            query_string = self.scope['query_string'].decode()
            token = None
            if query_string:
                params = dict(param.split('=') for param in query_string.split('&'))
                token = params.get('token')

            if not token:
                logger.error("No token provided")
                await self.close(code=4001)
                return

            try:
                # Get user from token
                self.user = await self.get_user_from_token(token)
                if not self.user:
                    logger.error("Failed to validate token or get user")
                    await self.close(code=4001)
                    return
                
                # Get post and verify it exists
                post = await self.get_post(self.post_id, self.is_personal)
                if not post:
                    logger.error(f"Post {self.post_id} not found")
                    await self.close(code=4001)
                    return

                # Join room group
                await self.channel_layer.group_add(
                    self.room_group_name,
                    self.channel_name
                )
                await self.accept()

                # Send initial data
                await self.send_initial_data()

            except Exception as e:
                logger.error(f"Error in WebSocket connect: {str(e)}", exc_info=True)
                await self.close(code=4001)

        except Exception as e:
            logger.error(f"Error during WebSocket connection: {str(e)}", exc_info=True)
            await self.close(code=1011)

    async def disconnect(self, close_code):
        try:
            if self.room_group_name:
                await self.channel_layer.group_discard(
                    self.room_group_name,
                    self.channel_name
                )
        except Exception as e:
            logger.error(f"Error during disconnect: {str(e)}", exc_info=True)

    async def send_initial_data(self):
        try:
            post = await self.get_post(self.post_id, self.is_personal)
            if not post:
                return

            user_rating = await self.get_user_rating(post)
            if user_rating is None:
                return

            await self.send(text_data=json.dumps({
                'type': 'initial_data',
                'data': {
                    'rating': post.rating,
                    'total_ratings': post.total_ratings,
                    'user_rating': user_rating.rating if user_rating else None
                }
            }, cls=DjangoJSONEncoder))
        except Exception as e:
            logger.error(f"Error sending initial data: {str(e)}", exc_info=True)

    async def receive(self, text_data):
        try:
            text_data_json = json.loads(text_data)
            message_type = text_data_json.get('type')
            data = text_data_json.get('data', {})

            if message_type == 'comment_created':
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'comment_created',
                        'data': data
                    }
                )
            elif message_type == 'reply_created':
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'reply_created',
                        'data': data
                    }
                )
        except Exception as e:
            logger.error(f"Error handling message: {str(e)}", exc_info=True)

    async def comment_created(self, event):
        try:
            await self.send(text_data=json.dumps({
                'type': 'comment_created',
                'data': event['data']
            }, cls=DjangoJSONEncoder))
        except Exception as e:
            logger.error(f"Error sending comment created: {str(e)}", exc_info=True)

    async def reply_created(self, event):
        try:
            await self.send(text_data=json.dumps({
                'type': 'reply_created',
                'data': event['data']
            }, cls=DjangoJSONEncoder))
        except Exception as e:
            logger.error(f"Error sending reply created: {str(e)}", exc_info=True)

    async def reply_deleted(self, event):
        try:
            await self.send(text_data=json.dumps({
                'type': 'reply_deleted',
                'data': event['data']
            }, cls=DjangoJSONEncoder))
        except Exception as e:
            logger.error(f"Error sending reply deleted: {str(e)}", exc_info=True)

    async def rating_update(self, event):
        try:
            await self.send(text_data=json.dumps({
                'type': 'rating_update',
                'data': event['data']
            }, cls=DjangoJSONEncoder))
        except Exception as e:
            logger.error(f"Error sending rating update: {str(e)}", exc_info=True)

    async def _process_updates(self):
        try:
            while True:
                rating = await self._update_queue.get()
                try:
                    if rating == self._last_rating:
                        logger.debug(f"Skipping duplicate rating update: {rating}")
                        continue

                    async with self._db_lock:
                        result = await self.update_post_rating(rating)
                        if result:
                            self._last_rating = rating
                            await self.channel_layer.group_send(
                                self.room_group_name,
                                {
                                    'type': 'rating_update',
                                    'data': result['data']
                                }
                            )
                            logger.info(f"Rating update broadcast: {result['data']}")
                        else:
                            logger.error("Failed to update post rating in database")
                except Exception as e:
                    logger.error(f"Error processing rating update: {str(e)}", exc_info=True)
                finally:
                    self._update_queue.task_done()
        except asyncio.CancelledError:
            logger.info("Update processor cancelled")
            raise
        except Exception as e:
            logger.error(f"Error in update processor: {str(e)}", exc_info=True)

    async def comment_updated(self, event):
        try:
            await self.send(text_data=json.dumps({
                'type': 'comment_updated',
                'data': event['data']
            }, cls=DjangoJSONEncoder))
        except Exception as e:
            logger.error(f"Error sending comment updated: {str(e)}", exc_info=True)

    async def comment_deleted(self, event):
        try:
            await self.send(text_data=json.dumps({
                'type': 'comment_deleted',
                'data': event['data']
            }, cls=DjangoJSONEncoder))
        except Exception as e:
            logger.error(f"Error sending comment deleted: {str(e)}", exc_info=True)

    async def reply_updated(self, event):
        try:
            await self.send(text_data=json.dumps({
                'type': 'reply_updated',
                'data': event['data']
            }, cls=DjangoJSONEncoder))
        except Exception as e:
            logger.error(f"Error sending reply updated: {str(e)}", exc_info=True) 