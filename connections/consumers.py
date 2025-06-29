import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import AccessToken
from django.db.models import Q
from .models import ConnectionRequest, UserSuggestion, Connection
from connections_api.serializers import ConnectionRequestSerializer, UserSuggestionSerializer
from api.serializers import PersonalityTagSerializer, UserInterestSerializer
from django.utils import timezone
import asyncio

User = get_user_model()

class ConnectionConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        try:
            # Get token from query params
            token = self.scope['query_string'].decode().split('token=')[1].split('&')[0]
            
            # Verify token and get user
            self.user = await self.get_user_from_token(token)
            if not self.user:
                await self.close()
                return

            # Update user's online status to 'online'
            await self.update_user_online_status('online')

            # Add user to their personal group
            self.user_group = f"user_{self.user.id}"
            await self.channel_layer.group_add(
                self.user_group,
                self.channel_name
            )

            await self.accept()
            
            # Send initial connection requests, suggestions and friends
            received_requests = await self.get_pending_requests()
            sent_requests = await self.get_sent_requests()
            suggestions = await self.get_suggestions()
            friends = await self.get_friends()
            
            if received_requests:
                await self.send(text_data=json.dumps({
                    'type': 'received_requests',
                    'requests': received_requests
                }))
                
            if sent_requests:
                await self.send(text_data=json.dumps({
                    'type': 'sent_requests',
                    'requests': sent_requests
                }))
                
            if suggestions:
                await self.send(text_data=json.dumps({
                    'type': 'suggestions',
                    'suggestions': suggestions
                }))
                
            if friends:
                await self.send(text_data=json.dumps({
                    'type': 'friends',
                    'friends': friends
                }))
                
        except Exception as e:
            print(f"Error in connect: {str(e)}")
            await self.close()

    async def disconnect(self, close_code):
        # Update user's online status to 'offline'
        if hasattr(self, 'user'):
            await self.update_user_online_status('offline')
        
        # Leave user group
        if hasattr(self, 'user_group'):
            await self.channel_layer.group_discard(
                self.user_group,
                self.channel_name
            )

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            event_type = data.get('type')

            if event_type == 'connection_request':
                await self.process_connection_request(data)
            elif event_type == 'connection_response':
                await self.process_connection_response(data)
            elif event_type == 'refresh_suggestions':
                await self.process_refresh_suggestions(data)
            elif event_type == 'refresh_friends':
                await self.process_refresh_friends(data)
            elif event_type == 'refresh_requests':
                await self.process_refresh_requests(data)
            elif event_type == 'cancel_request':
                await self.process_cancel_request(data)

        except Exception as e:
            print(f"Error handling WebSocket message: {e}")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': str(e)
            }))

    async def connection_request(self, event):
        """
        Send connection request to specific user
        """
        await self.send(text_data=json.dumps({
            'type': 'connection_request_received',
            'request': event['request']
        }))

    async def connection_update(self, event):
        """
        Send connection request update to specific user
        """
        await self.send(text_data=json.dumps({
            'type': 'connection_request_updated',
            'request': event['request']
        }))

    async def suggested_friends_update(self, event):
        """
        Send suggested friends update to specific user
        """
        await self.send(text_data=json.dumps({
            'type': 'suggested_friends_updated',
            'suggestions': event['suggestions']
        }))

    async def friends_update(self, event):
        """
        Send friends list update to specific user
        """
        await self.send(text_data=json.dumps({
            'type': 'friends_updated',
            'friends': event['friends']
        }))

    async def requests_update(self, event):
        """
        Send requests update to specific user
        """
        await self.send(text_data=json.dumps({
            'type': event['update_type'],  # 'received_requests_updated' or 'sent_requests_updated'
            'requests': event['requests']
        }))

    @database_sync_to_async
    def get_user_from_token(self, token):
        try:
            access_token = AccessToken(token)
            user_id = access_token['user_id']
            return User.objects.get(id=user_id)
        except Exception as e:
            print(f"Token validation error: {e}")
            return None

    @database_sync_to_async
    def get_pending_requests(self):
        requests = ConnectionRequest.objects.filter(
            receiver=self.user,
            status='pending'
        ).select_related('sender')
        serializer = ConnectionRequestSerializer(requests, many=True)
        return serializer.data

    @database_sync_to_async
    def get_sent_requests(self):
        requests = ConnectionRequest.objects.filter(
            sender=self.user,
            status='pending'
        ).select_related('receiver')
        serializer = ConnectionRequestSerializer(requests, many=True)
        return serializer.data

    @database_sync_to_async
    def get_suggestions(self):
        suggestions = UserSuggestion.objects.filter(
            user=self.user,
            is_active=True
        ).select_related('suggested_user')
        serializer = UserSuggestionSerializer(suggestions, many=True, context={'request': self.scope.get('request')})
        return serializer.data

    @database_sync_to_async
    def get_friends(self):
        # Get all active connections where the current user is either user1 or user2
        connections = Connection.objects.filter(
            (Q(user1=self.user) | Q(user2=self.user)),
            is_active=True
        ).select_related('user1', 'user2').prefetch_related(
            'user1__interests',
            'user2__interests',
            'user1__personality_tags',
            'user2__personality_tags'
        )

        friends_data = []
        for connection in connections:
            friend = connection.user2 if connection.user1 == self.user else connection.user1
            try:
                # Get personality tags
                personality_tags = friend.personality_tags.all()
                personality_tags_data = PersonalityTagSerializer(personality_tags, many=True).data

                # Get user's interests
                user_interests = friend.interests.all()
                interests_data = UserInterestSerializer(user_interests, many=True).data

                # Get common interests
                common_interests = connection.common_interests or []

                friend_data = {
                    'id': str(friend.id),
                    'first_name': str(friend.first_name) if friend.first_name else '',
                    'last_name': str(friend.last_name) if friend.last_name else '',
                    'username': str(friend.username),
                    'avatar': str(friend.avatar) if friend.avatar else '',
                    'role': str(friend.role) if friend.role else 'AI Professional',
                    'personality_tags': personality_tags_data,
                    'badges': [str(badge) for badge in friend.badges.all()] if hasattr(friend, 'badges') else [],
                    'last_active': str(friend.last_active) if friend.last_active else 'Online',
                    'connected_since': connection.created_at.isoformat() if connection.created_at else None,
                    'connected_at': connection.created_at.isoformat() if connection.created_at else None,
                    'mutual_connections': int(connection.mutual_connections_count) if connection.mutual_connections_count is not None else 0,
                    'interests': interests_data,
                    'common_interests': common_interests,
                    'location': str(friend.location) if friend.location else 'Unknown Location',
                    'last_interaction': connection.last_interaction.isoformat() if connection.last_interaction else None,
                    'connection_strength': connection.connection_strength if connection.connection_strength is not None else 0
                }
                friends_data.append(friend_data)
            except Exception as field_error:
                print(f"Error processing friend data: {str(field_error)}")
                continue

        return friends_data

    @database_sync_to_async
    def create_connection_request(self, receiver_id):
        receiver = User.objects.get(id=receiver_id)
        request = ConnectionRequest.objects.create(
            sender=self.user,
            receiver=receiver,
            status='pending'
        )
        serializer = ConnectionRequestSerializer(request)
        return serializer.data, receiver.id

    @database_sync_to_async
    def update_connection_request(self, request_id, action):
        request = ConnectionRequest.objects.get(id=request_id)
        if request.receiver != self.user:
            raise Exception('Unauthorized')
            
        request.status = 'accepted' if action == 'accept' else 'rejected'
        request.save()
        
        # If accepted, create the connection
        if action == 'accept':
            Connection.objects.create(
                user1=request.sender,
                user2=request.receiver,
                is_active=True
            )
        
        serializer = ConnectionRequestSerializer(request)
        return serializer.data, [request.sender.id, request.receiver.id]

    @database_sync_to_async
    def cancel_connection_request(self, request_id):
        request = ConnectionRequest.objects.get(id=request_id)
        if request.sender != self.user:
            raise Exception('Unauthorized')
            
        request.delete()
        return request.receiver.id

    async def process_connection_request(self, data):
        try:
            request_data, receiver_id = await self.create_connection_request(data.get('receiver_id'))
            
            # Get updated sent requests
            sent_requests = await self.get_sent_requests()
            
            # Send to receiver's group
            await self.channel_layer.group_send(
                f"user_{receiver_id}",
                {
                    'type': 'connection_request',
                    'request': request_data
                }
            )
            
            # Send updated sent requests to sender
            await self.channel_layer.group_send(
                self.user_group,
                {
                    'type': 'requests_update',
                    'update_type': 'sent_requests_updated',
                    'requests': sent_requests
                }
            )
            
        except User.DoesNotExist:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'User not found'
            }))
        except Exception as e:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': str(e)
            }))

    async def process_connection_response(self, data):
        try:
            request_data, user_ids = await self.update_connection_request(
                data.get('request_id'),
                data.get('action')
            )
            
            # Get updated lists
            friends = await self.get_friends()
            received_requests = await self.get_pending_requests()
            
            # Notify both users about all updates
            for user_id in user_ids:
                # Send connection update
                await self.channel_layer.group_send(
                    f"user_{user_id}",
                    {
                        'type': 'connection_update',
                        'request': request_data
                    }
                )
                
                # Send friends update
                await self.channel_layer.group_send(
                    f"user_{user_id}",
                    {
                        'type': 'friends_update',
                        'friends': friends
                    }
                )
                
                # Send requests update
                await self.channel_layer.group_send(
                    f"user_{user_id}",
                    {
                        'type': 'requests_update',
                        'update_type': 'received_requests_updated',
                        'requests': received_requests
                    }
                )
                
        except ConnectionRequest.DoesNotExist:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Request not found'
            }))
        except Exception as e:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': str(e)
            }))

    async def process_refresh_suggestions(self, data):
        try:
            # Get fresh suggestions
            suggestions = await self.get_suggestions()
            
            # Send updated suggestions to the user
            await self.send(text_data=json.dumps({
                'type': 'suggested_friends_updated',
                'suggestions': suggestions
            }))
            
        except Exception as e:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': str(e)
            }))

    async def process_refresh_friends(self, data):
        try:
            # Get fresh friends list
            friends = await self.get_friends()
            
            # Send updated friends list to the user
            await self.send(text_data=json.dumps({
                'type': 'friends_updated',
                'friends': friends
            }))
            
        except Exception as e:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': str(e)
            }))

    async def process_refresh_requests(self, data):
        try:
            # Get fresh requests lists
            received_requests = await self.get_pending_requests()
            sent_requests = await self.get_sent_requests()
            
            # Send updated requests to the user
            await self.send(text_data=json.dumps({
                'type': 'received_requests_updated',
                'requests': received_requests
            }))
            
            await self.send(text_data=json.dumps({
                'type': 'sent_requests_updated',
                'requests': sent_requests
            }))
            
        except Exception as e:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': str(e)
            }))

    async def process_cancel_request(self, data):
        try:
            receiver_id = await self.cancel_connection_request(data.get('request_id'))
            
            # Get updated sent requests and suggestions
            sent_requests = await self.get_sent_requests()
            suggestions = await self.get_suggestions()
            
            # Send updated sent requests to sender
            await self.channel_layer.group_send(
                self.user_group,
                {
                    'type': 'requests_update',
                    'update_type': 'sent_requests_updated',
                    'requests': sent_requests
                }
            )
            
            # Send updated suggestions to sender
            await self.channel_layer.group_send(
                self.user_group,
                {
                    'type': 'suggested_friends_update',
                    'suggestions': suggestions
                }
            )
            
            # Notify receiver that request was cancelled
            await self.channel_layer.group_send(
                f"user_{receiver_id}",
                {
                    'type': 'requests_update',
                    'update_type': 'received_requests_updated',
                    'requests': await self.get_pending_requests()
                }
            )
            
        except ConnectionRequest.DoesNotExist:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Request not found'
            }))
        except Exception as e:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': str(e)
            }))

    @database_sync_to_async
    def update_user_online_status(self, status):
        """Update user's online status in the database and broadcast to connected users."""
        try:
            if hasattr(self, 'user') and self.user:
                old_status = self.user.online_status
                self.user.online_status = status
                self.user.last_active = timezone.now()
                self.user.save(update_fields=['online_status', 'last_active'])
                print(f"Updated {self.user.username} online status to: {status}")
                
                # Broadcast status change to connected users
                if old_status != status:
                    asyncio.create_task(self.broadcast_online_status_change(status))
        except Exception as e:
            print(f"Error updating user online status: {str(e)}")

    async def broadcast_online_status_change(self, new_status):
        """Broadcast online status change to connected users."""
        try:
            # Get all connections for this user
            connections = await self.get_user_connections()
            
            for connection in connections:
                # Send to the other user in the connection
                other_user_id = connection.user1.id if connection.user2.id == self.user.id else connection.user2.id
                await self.channel_layer.group_send(
                    f'user_{other_user_id}',
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
            print(f"Error broadcasting online status change: {str(e)}")

    @database_sync_to_async
    def get_user_connections(self):
        """Get all active connections for the user."""
        try:
            return list(Connection.objects.filter(
                (Q(user1=self.user) | Q(user2=self.user)),
                is_active=True
            ))
        except Exception as e:
            print(f"Error getting user connections: {str(e)}")
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