from django.shortcuts import render, get_object_or_404
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.db.models import Q
from django.conf import settings
from chat.models import (
    Group,
    Conversation,
    ConversationMember,
    Message,
    MessageReaction,
    MessageThread,
    MessageEffect,
    LinkPreview,
    File
)
from .serializers import (
    GroupSerializer,
    ConversationSerializer,
    ConversationMemberSerializer,
    MessageSerializer,
    MessageReactionSerializer,
    MessageThreadSerializer,
    MessageEffectSerializer,
    LinkPreviewSerializer
)
from django.utils import timezone
from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from PIL import Image
import os
import uuid
from io import BytesIO
from django.core.exceptions import PermissionDenied
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
import logging
from django.core.exceptions import ValidationError
from django.http import Http404
import time
from .services import RealTimeSuggestionService

# Configure logger
logger = logging.getLogger(__name__)

# Get the custom User model
User = get_user_model()

# Create your views here.

class IsMemberOrAdmin(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        if isinstance(obj, Conversation):
            return obj.members.filter(user=request.user).exists()
        elif isinstance(obj, Group):
            return obj.conversations.filter(members__user=request.user).exists()
        elif isinstance(obj, MessageThread):
            return obj.parent_message.conversation.members.filter(user=request.user).exists()
        elif isinstance(obj, Message):
            return obj.conversation.members.filter(user=request.user).exists()
        return False

class GroupViewSet(viewsets.ModelViewSet):
    queryset = Group.objects.all()
    serializer_class = GroupSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        print(f"\n=== Getting Groups for User {self.request.user.id} ===")
        groups = Group.objects.filter(conversations__members__user=self.request.user).distinct()
        print(f"Found {groups.count()} groups")
        for group in groups:
            print(f"Group ID: {group.id}, Name: {group.name}")
        return groups
    
    def get_object(self):
        print(f"\n=== Getting Group Object ===")
        print(f"Request user: {self.request.user.id}")
        print(f"Group ID from URL: {self.kwargs.get('pk')}")
        print(f"Request method: {self.request.method}")
        print(f"Request path: {self.request.path}")
        print(f"Request data: {self.request.data}")
        
        # First check if the group exists
        try:
            group_id = self.kwargs.get('pk')
            print(f"Looking for group with ID: {group_id}")
            
            # Check if the ID is valid
            if not group_id or not str(group_id).isdigit():
                print(f"Invalid group ID: {group_id}")
                raise Http404("Invalid group ID")
            
            group = Group.objects.get(id=group_id)
            print(f"Found group: {group.id} - {group.name}")
            
            # Then check if user has access
            has_access = group.conversations.filter(members__user=self.request.user).exists()
            print(f"User has access: {has_access}")
            
            if not has_access:
                print(f"User {self.request.user.id} does not have access to group {group.id}")
                raise PermissionDenied("You don't have access to this group")
                
            return group
        except Group.DoesNotExist:
            print(f"Group {self.kwargs.get('pk')} does not exist")
            raise Http404("No Group matches the given query.")
        except Exception as e:
            print(f"Unexpected error in get_object: {str(e)}")
            raise
    
    def perform_create(self, serializer):
        print("\n=== Starting Group Creation Process ===")
        
        # Get member IDs from request data
        member_ids = self.request.data.get('memberIds', [])
        print(f"Received member IDs: {member_ids}")
        print(f"Request user ID: {self.request.user.id}")
        
        # Create the group
        print("\nCreating group...")
        group = serializer.save(created_by=self.request.user)
        print(f"Group created with ID: {group.id}")
        print(f"Group name: {group.name}")
        
        # Create a conversation for this group
        print("\nCreating conversation...")
        conversation = Conversation.objects.create(
            type='group',
            group=group,
            name=group.name
        )
        print(f"Conversation created with ID: {conversation.id}")
        
        # Add creator as admin
        print("\nAdding creator as admin...")
        admin_member = ConversationMember.objects.create(
            conversation=conversation,
            user=self.request.user,
            role='admin'
        )
        print(f"Creator added as admin with ID: {admin_member.id}")
        
        # Add initial members
        print("\nAdding initial members...")
        for member_id in member_ids:
            try:
                # Convert member_id to integer if it's a string
                member_id = int(member_id)
                user = User.objects.get(id=member_id)
                if user != self.request.user:  # Skip creator as they're already added
                    # Add member to conversation
                    member = ConversationMember.objects.create(
                        conversation=conversation,
                        user=user,
                        role='member'
                    )
                    print(f"Added member {user.id} ({user.username}) to conversation with ID: {member.id}")
                else:
                    print(f"Skipping creator {user.id} as they're already added as admin")
            except (User.DoesNotExist, ValueError) as e:
                print(f"Error adding member {member_id}: {str(e)}")
                continue
        
        # Return the created group and conversation IDs
        print("\nSetting response data...")
        serializer.instance.group_id = group.id
        serializer.instance.conversation_id = conversation.id
        print(f"Group ID: {group.id}")
        print(f"Conversation ID: {conversation.id}")
        
        print("\n=== Group Creation Process Completed ===\n")

    def update(self, request, *args, **kwargs):
        try:
            instance = self.get_object()
            print(f"\n=== Starting Group Update Process ===")
            print(f"Group ID: {instance.id}")
            print(f"Group Name: {instance.name}")
            print(f"Request user: {request.user.id}")
            print(f"Request data: {request.data}")
            print(f"Request FILES: {request.FILES}")
            
            # Handle file upload
            if 'avatar' in request.FILES:
                print(f"Processing avatar file: {request.FILES['avatar']}")
                # Delete old avatar if it exists and is not the default
                if instance.avatar and instance.avatar.name != Group.DEFAULT_GROUP_AVATAR:
                    try:
                        instance.avatar.delete()
                    except Exception as e:
                        print(f"Error deleting old avatar: {str(e)}")
                
                # Save new avatar
                instance.avatar = request.FILES['avatar']
                instance.save()
                print(f"New avatar saved: {instance.avatar.name}")
            
            # Update other fields
            serializer = self.get_serializer(instance, data=request.data, partial=True)
            if not serializer.is_valid():
                print(f"Serializer errors: {serializer.errors}")
                return Response(
                    {'error': 'Invalid data', 'details': serializer.errors},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            group = serializer.save()
            
            # Update the associated conversation name if name is being updated
            if 'name' in request.data:
                conversation = group.conversations.first()
                if conversation:
                    conversation.name = request.data['name']
                    conversation.save()
                    print(f"Updated conversation name to: {conversation.name}")
            
            print("=== Group Update Process Completed ===\n")
            return Response(serializer.data)
            
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            print(f"Error updating group: {str(e)}")
            print(f"Error details: {error_details}")
            return Response(
                {'error': str(e), 'details': error_details},
                status=status.HTTP_400_BAD_REQUEST
            )

class ConversationViewSet(viewsets.ModelViewSet):
    serializer_class = ConversationSerializer
    permission_classes = [permissions.IsAuthenticated, IsMemberOrAdmin]

    def get_queryset(self):
        return Conversation.objects.filter(members__user=self.request.user).distinct()

    def perform_create(self, serializer):
        conversation_type = serializer.validated_data.get('type')
        
        if conversation_type == 'direct':
            # Handle both members array and other_user field
            other_user_id = self.request.data.get('other_user')
            members = self.request.data.get('members', [])
            
            if not other_user_id and not members:
                raise serializers.ValidationError({
                    'other_user': 'Either other_user or members field is required for direct messages'
                })
            
            # If members array is provided, use the first member as other_user
            if members and not other_user_id:
                other_user_id = members[0]
            
            try:
                other_user = User.objects.get(id=other_user_id)
                
                # Check if conversation already exists
                existing_conversation = Conversation.objects.filter(
                    type='direct',
                    participant1__in=[self.request.user, other_user],
                    participant2__in=[self.request.user, other_user]
                ).first()
                
                if existing_conversation:
                    serializer.instance = existing_conversation
                    return
                
                # Create new conversation if none exists
                conversation = Conversation.create_direct_message(self.request.user, other_user)
                serializer.instance = conversation
                
            except User.DoesNotExist:
                raise serializers.ValidationError({
                    'other_user': 'User not found'
                })
                
        else:  # group chat
            name = serializer.validated_data.get('name')
            if not name:
                raise serializers.ValidationError({'name': 'This field is required for group chats'})
            
            # For group chats, we should not create a new conversation here
            # as it's already created in the GroupViewSet
            raise serializers.ValidationError({
                'type': 'Group conversations should be created through the group creation endpoint'
            })

    @action(detail=True, methods=['post'])
    def mark_read(self, request, pk=None):
        conversation = self.get_object()
        member = conversation.members.get(user=request.user)
        member.last_read = timezone.now()
        member.unread_count = 0  # Reset unread count when marking conversation as read
        member.save()
        return Response({'status': 'marked as read'})

    @action(detail=True, methods=['post'])
    def mute(self, request, pk=None):
        conversation = self.get_object()
        member = conversation.members.get(user=request.user)
        member.is_muted = not member.is_muted
        member.save()
        return Response({'status': 'muted' if member.is_muted else 'unmuted'})

    @action(detail=False, methods=['get'])
    def direct_messages(self, request):
        """Get all direct message conversations for the current user"""
        try:
            # First check if the user is authenticated
            if not request.user.is_authenticated:
                return Response(
                    {'error': 'Authentication required'},
                    status=status.HTTP_401_UNAUTHORIZED
                )

            # Get conversations with proper error handling
            conversations = Conversation.objects.filter(
                type='direct',
                is_active=True
            ).filter(
                Q(participant1=request.user) | Q(participant2=request.user)
            ).distinct()

            # Validate that all required fields are present
            invalid_conversations = []
            for conv in conversations:
                if not (conv.participant1 and conv.participant2):
                    invalid_conversations.append(conv.id)
                    continue
                
                # Ensure both participants are members
                if not conv.members.filter(user__in=[conv.participant1, conv.participant2]).count() == 2:
                    invalid_conversations.append(conv.id)

            if invalid_conversations:
                print(f"Found invalid conversations: {invalid_conversations}")
                conversations = conversations.exclude(id__in=invalid_conversations)

            # Serialize with proper context
            serializer = self.get_serializer(conversations, many=True, context={'request': request})
            return Response(serializer.data)

        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            print(f"Error in direct_messages: {str(e)}\n{error_details}")
            return Response(
                {
                    'error': 'Failed to fetch direct messages',
                    'details': str(e)
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=['get'])
    def group_chats(self, request):
        """Get all group chat conversations for the current user"""
        conversations = Conversation.objects.filter(
            type='group',
            members__user=request.user
        ).distinct()
        serializer = self.get_serializer(conversations, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def add_member(self, request, pk=None):
        conversation = self.get_object()
        user_id = request.data.get('user_id')
        role = request.data.get('role', 'member')
        
        if not user_id:
            return Response({'error': 'user_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            member = ConversationMember.objects.create(
                conversation=conversation,
                user_id=user_id,
                role=role
            )
            return Response(ConversationMemberSerializer(member).data)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def remove_member(self, request, pk=None):
        conversation = self.get_object()
        user_id = request.data.get('user_id')
        
        if not user_id:
            return Response({'error': 'user_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            member = conversation.members.get(user_id=user_id)
            member.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except ConversationMember.DoesNotExist:
            return Response({'error': 'Member not found'}, status=status.HTTP_404_NOT_FOUND)

    @action(detail=True, methods=['put'])
    def change_member_role(self, request, pk=None):
        """Change a member's role in a group chat"""
        conversation = self.get_object()
        if conversation.type != 'group':
            return Response(
                {'error': 'Can only change roles in group chats'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        member_id = request.data.get('member_id')
        new_role = request.data.get('role')
        
        if not member_id or not new_role:
            return Response(
                {'error': 'member_id and role are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if new_role not in ['admin', 'moderator', 'member']:
            return Response(
                {'error': 'Invalid role'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            # Get the member to update
            member_to_update = conversation.members.get(user_id=member_id)
            
            # Get the requester's role
            requester_member = conversation.members.get(user=request.user)
            
            # Check permissions
            if requester_member.role != 'admin':
                return Response(
                    {'error': 'Only admins can change roles'},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            # Prevent changing the last admin's role
            if member_to_update.role == 'admin' and new_role != 'admin':
                admin_count = conversation.members.filter(role='admin').count()
                if admin_count <= 1:
                    return Response(
                        {'error': 'Cannot remove the last admin'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            
            # Update the role
            member_to_update.role = new_role
            member_to_update.save()
            
            return Response({
                'message': f'Successfully updated role to {new_role}',
                'member': {
                    'id': member_to_update.user.id,
                    'role': new_role
                }
            })
            
        except ConversationMember.DoesNotExist:
            return Response(
                {'error': 'Member not found in conversation'},
                status=status.HTTP_404_NOT_FOUND
            )

    @action(detail=True, methods=['post'])
    def fix_members(self, request, pk=None):
        """Fix conversation members for direct messages"""
        conversation = self.get_object()
        if conversation.type != 'direct':
            return Response(
                {'error': 'Can only fix members for direct messages'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if not (conversation.participant1 and conversation.participant2):
            return Response(
                {'error': 'Conversation is missing participants'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get existing members
        existing_members = set(conversation.members.values_list('user_id', flat=True))
        required_members = {conversation.participant1.id, conversation.participant2.id}
        
        # Add missing members
        for user_id in required_members - existing_members:
            try:
                user = User.objects.get(id=user_id)
                ConversationMember.objects.create(
                    conversation=conversation,
                    user=user,
                    role='member'
                )
            except User.DoesNotExist:
                return Response(
                    {'error': f'User {user_id} not found'},
                    status=status.HTTP_404_NOT_FOUND
                )
        
        return Response({
            'status': 'members fixed',
            'members': list(conversation.members.values('user_id', 'role'))
        })

    @action(detail=True, methods=['post'])
    def add_members(self, request, pk=None):
        """Add multiple members to a conversation"""
        conversation = self.get_object()
        member_ids = request.data.get('member_ids', [])
        
        if not member_ids:
            return Response({'error': 'member_ids is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        if not isinstance(member_ids, list):
            return Response({'error': 'member_ids must be a list'}, status=status.HTTP_400_BAD_REQUEST)
        
        added_members = []
        errors = []
        
        for user_id in member_ids:
            try:
                # Skip if user is already a member
                if conversation.members.filter(user_id=user_id).exists():
                    continue
                    
                member = ConversationMember.objects.create(
                    conversation=conversation,
                    user_id=user_id,
                    role='member'
                )
                added_members.append(ConversationMemberSerializer(member).data)
            except Exception as e:
                errors.append(f"Failed to add user {user_id}: {str(e)}")
        
        response_data = {
            'added_members': added_members,
            'errors': errors
        }
        
        if errors:
            return Response(response_data, status=status.HTTP_207_MULTI_STATUS)
        return Response(response_data)

    @action(detail=True, methods=['patch'])
    def update_group(self, request, pk=None):
        try:
            conversation = self.get_object()
            print(f"\n=== Starting Group Update Through Conversation ===")
            print(f"Conversation ID: {conversation.id}")
            print(f"Conversation Type: {conversation.type}")
            print(f"Request user: {request.user.id}")
            print(f"Request data: {request.data}")
            print(f"Request FILES: {request.FILES}")

            # Check if conversation is a group
            if conversation.type != 'group':
                return Response(
                    {'detail': 'This endpoint is only available for group conversations'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Check if user is an admin
            member = conversation.members.get(user=request.user)
            if member.role != 'admin':
                return Response(
                    {'detail': 'Only group admins can update group details'},
                    status=status.HTTP_403_FORBIDDEN
                )

            group = conversation.group
            print(f"Group ID: {group.id}")
            print(f"Current Group Name: {group.name}")

            # Handle file upload
            if 'avatar' in request.FILES:
                print(f"Processing avatar file: {request.FILES['avatar']}")
                # Delete old avatar if it exists and is not the default
                if group.avatar and group.avatar.name != Group.DEFAULT_GROUP_AVATAR:
                    try:
                        group.avatar.delete()
                    except Exception as e:
                        print(f"Error deleting old avatar: {str(e)}")

                # Save new avatar
                group.avatar = request.FILES['avatar']
                group.save()
                print(f"New avatar saved: {group.avatar.name}")

            # Update group name if provided
            if 'name' in request.data:
                new_name = request.data['name'].strip()
                if new_name:
                    group.name = new_name
                    # Also update conversation name to match
                    conversation.name = new_name
                    conversation.save()
                    print(f"Updated group and conversation name to: {new_name}")

            group.save()
            print(f"Group saved successfully")

            # Broadcast the update to all group members
            channel_layer = get_channel_layer()
            for member in conversation.members.all():
                async_to_sync(channel_layer.group_send)(
                    f"user_{member.user.id}",
                    {
                        "type": "group.update",
                        "group_id": group.id,
                        "conversation_id": conversation.id,
                        "name": group.name,
                        "avatar_url": group.avatar.url if group.avatar else None
                    }
                )

            # Return updated group and conversation data
            return Response({
                'group': {
                    'id': group.id,
                    'name': group.name,
                    'avatar_url': group.avatar.url if group.avatar else None
                },
                'conversation': {
                    'id': conversation.id,
                    'name': conversation.name
                }
            })

        except Exception as e:
            print(f"Error updating group: {str(e)}")
            return Response(
                {'detail': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class MessageViewSet(viewsets.ModelViewSet):
    serializer_class = MessageSerializer
    permission_classes = [permissions.IsAuthenticated, IsMemberOrAdmin]

    def get_queryset(self):
        conversation_id = self.kwargs.get('conversation_pk')
        # First check if user is a member of the conversation
        if not Conversation.objects.filter(
            id=conversation_id,
            members__user=self.request.user
        ).exists():
            raise PermissionDenied("You are not a member of this conversation")
        return Message.objects.filter(conversation_id=conversation_id).order_by('created_at')

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['request'] = self.request
        print(f'MessageViewSet.get_serializer_context:')
        print(f'- Request: {self.request}')
        print(f'- Context: {context}')
        return context

    def perform_create(self, serializer):
        try:
            print('=== MESSAGE VIEWSET CREATE ===')
            print('Request data:', self.request.data)
            print('Validated data:', serializer.validated_data)
            
            # Get the conversation from the URL
            conversation_id = self.kwargs.get('conversation_pk')
            conversation = get_object_or_404(Conversation, id=conversation_id)
            
            # Check if user is a participant
            if not conversation.is_participant(self.request.user):
                raise PermissionDenied("You are not a member of this conversation")
            
            # Get reply_to_id from request data
            reply_to_id = self.request.data.get('reply_to_id')
            print('Reply to ID:', reply_to_id)
            
            # Create the message
            message = serializer.save(
                conversation=conversation,
                sender=self.request.user
            )
            
            # Handle reply
            if reply_to_id:
                print('Setting reply_to for message:', message.id)
                reply_to = get_object_or_404(Message, id=reply_to_id)
                message.reply_to = reply_to
                message.save()
                print('Reply set:', {
                    'message_id': message.id,
                    'reply_to_id': reply_to.id,
                    'reply_to_content': reply_to.content
                })
            
            # Serialize the message with context
            serialized_data = MessageSerializer(message, context={'request': self.request}).data
            print('Serialized message:', {
                'id': serialized_data['id'],
                'content': serialized_data['content'],
                'reply_to': serialized_data.get('reply_to'),
                'has_reply_to': bool(serialized_data.get('reply_to'))
            })
            
            # Broadcast message to WebSocket
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                f"chat_{conversation_id}",
                {
                    "type": "chat_message",
                    "message": serialized_data
                }
            )
            
            return message
        except Exception as e:
            logger.error(f"Error creating message: {str(e)}")
            raise

    @action(detail=True, methods=['post'])
    def react(self, request, pk=None, conversation_pk=None):
        message = self.get_object()
        conversation = message.conversation
        try:
            member = conversation.members.get(user=request.user)
        except ConversationMember.DoesNotExist:
            return Response({'error': 'You are not a member of this conversation.'}, status=status.HTTP_403_FORBIDDEN)
        if not member.has_permission('react_messages'):
            return Response({'error': 'You do not have permission to react to messages.'}, status=status.HTTP_403_FORBIDDEN)
        emoji = request.data.get('emoji')
        if not emoji:
            return Response({'error': 'Emoji is required'}, status=status.HTTP_400_BAD_REQUEST)
        reaction, created = MessageReaction.objects.get_or_create(
            message=message,
            user=request.user,
            emoji=emoji
        )
        if not created:
            reaction.delete()
            return Response({'status': 'reaction removed'})
        return Response({'status': 'reaction added'})

    @action(detail=True, methods=['post'])
    def pin(self, request, pk=None, conversation_pk=None):
        message = self.get_object()
        message.is_pinned = not message.is_pinned
        message.save()
        return Response({'status': 'pinned' if message.is_pinned else 'unpinned'})

    @action(detail=True, methods=['post'])
    def forward(self, request, pk=None, conversation_pk=None):
        try:
            message = self.get_object()
            target_conversation_id = request.data.get('conversation_id')
            
            if not target_conversation_id:
                return Response(
                    {'error': 'Target conversation ID is required'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Get target conversation
            target_conversation = get_object_or_404(Conversation, id=target_conversation_id)
            
            # Check if user is a member of target conversation
            if not target_conversation.is_participant(request.user):
                return Response(
                    {'error': 'You are not a member of the target conversation'},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            # Create forwarded message
            forwarded_message = Message.objects.create(
                conversation=target_conversation,
                sender=request.user,
                content=message.content,
                message_type=message.message_type,
                is_forwarded=True,
                original_message=message,
                file=message.file,
                file_name=message.file_name,
                file_size=message.file_size,
                file_type=message.file_type,
                thumbnail=message.thumbnail,
                duration=message.duration
            )
            
            # Send WebSocket notification
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                f"chat_{target_conversation.id}",
                {
                    "type": "chat_message",
                    "message": MessageSerializer(forwarded_message, context={'request': request}).data
                }
            )
            
            return Response(
                MessageSerializer(forwarded_message, context={'request': request}).data,
                status=status.HTTP_201_CREATED
            )
            
        except Exception as e:
            logger.error(f"Error forwarding message: {str(e)}")
            return Response(
                {'error': 'Failed to forward message'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def perform_destroy(self, instance):
        # Check if user is the sender of the message
        if instance.sender != self.request.user:
            raise PermissionDenied("You can only delete your own messages")
        
        # Store conversation and message ID for WebSocket notification
        conversation = instance.conversation
        message_id = instance.id
        
        # Delete the message
        instance.delete()
        
        # Update conversation's last message
        last_message = Message.objects.filter(conversation=conversation).order_by('-created_at').first()
        conversation.last_message = last_message
        conversation.save()
        
        # Send WebSocket notification
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f"chat_{conversation.id}",
            {
                "type": "message_deleted",
                "message_id": message_id,
                "conversation_id": str(conversation.id),
                "user_id": str(self.request.user.id)
            }
        )

    def destroy(self, request, *args, **kwargs):
        try:
            instance = self.get_object()
            self.perform_destroy(instance)
            return Response(status=status.HTTP_204_NO_CONTENT)
        except PermissionDenied as e:
            logger.warning(f"Permission denied when deleting message: {str(e)}")
            return Response(
                {"detail": str(e)},
                status=status.HTTP_403_FORBIDDEN
            )
        except Exception as e:
            logger.error(f"Error deleting message: {str(e)}")
            return Response(
                {"detail": "An error occurred while deleting the message"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class MessageReactionViewSet(viewsets.ModelViewSet):
    serializer_class = MessageReactionSerializer
    permission_classes = [permissions.IsAuthenticated, IsMemberOrAdmin]

    def get_queryset(self):
        message_id = self.kwargs.get('message_pk')
        return MessageReaction.objects.filter(message_id=message_id)

class MessageThreadViewSet(viewsets.ModelViewSet):
    serializer_class = MessageThreadSerializer
    permission_classes = [permissions.IsAuthenticated, IsMemberOrAdmin]

    def get_queryset(self):
        message_id = self.kwargs.get('message_pk')
        try:
            return MessageThread.objects.filter(parent_message_id=message_id)
        except MessageThread.DoesNotExist:
            return MessageThread.objects.none()

    def perform_create(self, serializer):
        message_id = self.kwargs.get('message_pk')
        parent_message = get_object_or_404(Message, id=message_id)
        
        # Check if user is a participant in the conversation
        if not parent_message.conversation.members.filter(user=self.request.user).exists():
            raise PermissionDenied("You are not a participant in this conversation")
        
        # Check if this is a group conversation
        if parent_message.conversation.type == 'direct':
            raise ValidationError("Threads can only be created in group conversations")
        
        # Check if thread already exists
        try:
            thread = MessageThread.objects.get(parent_message=parent_message)
            serializer.instance = thread
            return thread
        except MessageThread.DoesNotExist:
            # Create the thread
            thread = MessageThread.objects.create(
                parent_message=parent_message,
                created_by=self.request.user
            )
            # Add the creator as a participant
            thread.participants.add(self.request.user)
            serializer.instance = thread
            return thread

class MessageEffectViewSet(viewsets.ModelViewSet):
    serializer_class = MessageEffectSerializer
    permission_classes = [permissions.IsAuthenticated, IsMemberOrAdmin]

    def get_queryset(self):
        message_id = self.kwargs.get('message_pk')
        return MessageEffect.objects.filter(message_id=message_id)

class LinkPreviewViewSet(viewsets.ModelViewSet):
    serializer_class = LinkPreviewSerializer
    permission_classes = [permissions.IsAuthenticated, IsMemberOrAdmin]

    def get_queryset(self):
        message_id = self.kwargs.get('message_pk')
        return LinkPreview.objects.filter(message_id=message_id)

@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def upload_file(request):
    """Handle file upload for chat messages (no message creation)"""
    try:
        print('\n=== File Upload Request ===')
        print('Request User:', request.user)
        print('Request Files:', request.FILES)
        print('Request Data:', request.data)

        file = request.FILES.get('file')
        if not file:
            print('Error: No file provided in request')
            return Response({'error': 'No file provided'}, status=status.HTTP_400_BAD_REQUEST)

        print(f'Processing file: {file.name} ({file.size} bytes, {file.content_type})')

        # Determine file category based on mime type
        mime_type = file.content_type
        category = 'other'
        if mime_type.startswith('image/'):
            category = 'image'
        elif mime_type.startswith('video/'):
            category = 'video'
        elif mime_type.startswith('audio/'):
            category = 'audio'
        elif mime_type.startswith('application/'):
            category = 'document'

        # Create file object with basic info
        file_obj = File.objects.create(
            file=file,
            file_name=file.name,
            file_size=file.size,
            file_type=file.content_type,
            category=category,
            uploaded_by=request.user
        )
        print(f'Created File object: {file_obj.id}')

        # Generate thumbnail for images
        if file.content_type.startswith('image/'):
            try:
                print('Generating thumbnail for image')
                # Open the image
                img = Image.open(file)
                
                # Calculate thumbnail size (max 200x200 while maintaining aspect ratio)
                max_size = (200, 200)
                img.thumbnail(max_size, Image.Resampling.LANCZOS)
                
                # Save thumbnail to BytesIO
                thumb_io = BytesIO()
                img.save(thumb_io, format=img.format or 'JPEG', quality=85)
                thumb_io.seek(0)
                
                # Generate thumbnail filename
                thumb_name = f"thumb_{os.path.basename(file.name)}"
                
                # Save thumbnail to model
                file_obj.thumbnail.save(thumb_name, ContentFile(thumb_io.read()), save=True)
                print(f'Thumbnail generated and saved: {thumb_name}')
            except Exception as e:
                print(f"Error generating thumbnail: {str(e)}")

        # Ensure the file path is set correctly
        if file_obj.file:
            file_obj.file.name = f'chat_attachments/{file.name}'
            file_obj.save()
            print(f'Updated file path: {file_obj.file.name}')

        serializer = FileSerializer(file_obj, context={'request': request})
        print('File upload successful, returning data:', serializer.data)
        return Response(serializer.data)
    except Exception as e:
        print(f'Error in file upload: {str(e)}')
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class UpdateGroupThroughConversationViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated, IsMemberOrAdmin]
    serializer_class = GroupSerializer
    http_method_names = ['patch']  # Only allow PATCH method
    
    def get_queryset(self):
        return Group.objects.none()  # We don't need to list groups here
    
    def get_object(self):
        conversation = get_object_or_404(Conversation, pk=self.kwargs.get('conversation_pk'))
        
        # Check if conversation is a group conversation
        if conversation.type != 'group':
            raise PermissionDenied('Can only update groups through group conversations')
        
        # Get the associated group
        group = conversation.group
        if not group:
            raise Http404('No group associated with this conversation')
        
        # Check if user has permission to update the group
        member = conversation.members.get(user=self.request.user)
        if not member.has_permission('update_group'):
            raise PermissionDenied('You do not have permission to update this group')
        
        return group
    
    def partial_update(self, request, *args, **kwargs):
        print("\n=== Starting Group Update Process ===")
        print(f"Request user: {request.user.id}")
        print(f"Request data: {request.data}")
        print(f"Request FILES: {request.FILES}")
        
        group = self.get_object()
        conversation = group.conversations.first()
        
        print(f"Group ID: {group.id}")
        print(f"Group Name: {group.name}")
        print(f"Current Avatar: {group.avatar.url if group.avatar else 'None'}")
        
        # Handle file upload
        if 'avatar' in request.FILES:
            print("\n=== Processing Avatar Upload ===")
            avatar_file = request.FILES['avatar']
            print(f"New avatar file: {avatar_file.name}")
            print(f"File size: {avatar_file.size} bytes")
            print(f"Content type: {avatar_file.content_type}")
            
            # Delete old avatar if it exists and is not the default
            if group.avatar and group.avatar.name != Group.DEFAULT_GROUP_AVATAR:
                try:
                    print(f"Deleting old avatar: {group.avatar.name}")
                    group.avatar.delete()
                    print("Old avatar deleted successfully")
                except Exception as e:
                    print(f"Error deleting old avatar: {str(e)}")
            
            # Save new avatar
            try:
                print("Saving new avatar...")
                group.avatar = avatar_file
                group.save()
                print(f"New avatar saved successfully: {group.avatar.name}")
                print(f"New avatar URL: {group.avatar.url}")
            except Exception as e:
                print(f"Error saving new avatar: {str(e)}")
                raise
        
        # Update other fields
        print("\n=== Updating Other Fields ===")
        serializer = self.get_serializer(group, data=request.data, partial=True)
        if not serializer.is_valid():
            print(f"Serializer errors: {serializer.errors}")
            return Response(
                {'error': 'Invalid data', 'details': serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        group = serializer.save()
        print("Other fields updated successfully")
        
        # Update the conversation name if name is being updated
        if 'name' in request.data:
            print("\n=== Updating Conversation Name ===")
            conversation.name = request.data['name']
            conversation.save()
            print(f"Conversation name updated to: {conversation.name}")
        
        # Broadcast the update to all group members
        print("\n=== Broadcasting Update ===")
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f"chat_{conversation.id}",
            {
                "type": "group_update",
                "group": {
                    "id": group.id,
                    "name": group.name,
                    "avatar": group.avatar.url if group.avatar else None
                },
                "conversation": {
                    "id": conversation.id,
                    "name": conversation.name
                }
            }
        )
        print("Update broadcasted successfully")
        
        # Prepare response data
        response_data = {
            'id': group.id,
            'name': group.name,
            'avatar': group.avatar.url if group.avatar else None,
            'conversation': {
                'id': conversation.id,
                'name': conversation.name
            }
        }
        
        print("\n=== Update Process Completed ===")
        print(f"Final group data: {response_data}")
        
        return Response(response_data)

class RealTimeSuggestionViewSet(viewsets.ViewSet):
    """ViewSet for real-time AI-powered message suggestions."""
    permission_classes = [permissions.IsAuthenticated, IsMemberOrAdmin]
    
    @action(detail=False, methods=['post'])
    def generate(self, request):
        """Generate new AI suggestions for a conversation."""
        conversation_id = request.data.get('conversation_id')
        suggestion_types = request.data.get('suggestion_types', ['quick_reply', 'context_based', 'topic_suggestion'])
        max_suggestions = request.data.get('max_suggestions', 3)
        custom_prompt = request.data.get('custom_prompt')
        
        if not conversation_id:
            return Response(
                {'error': 'conversation_id is required'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            conversation = Conversation.objects.get(id=conversation_id)
            
            # Check if user is a member of the conversation
            if not conversation.is_participant(request.user):
                raise PermissionDenied("You don't have access to this conversation")
            
            # Generate real-time suggestions
            suggestions = RealTimeSuggestionService.generate_suggestions(
                conversation=conversation,
                user=request.user,
                suggestion_types=suggestion_types,
                max_suggestions=max_suggestions,
                custom_prompt=custom_prompt
            )
            
            return Response({
                'suggestions': suggestions,
                'count': len(suggestions),
                'is_real_time': True
            })
            
        except Conversation.DoesNotExist:
            return Response(
                {'error': 'Conversation not found'}, 
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Error generating real-time suggestions: {str(e)}", exc_info=True)
            return Response(
                {'error': 'Failed to generate suggestions'}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['get'])
    def analyze_conversation(self, request):
        """Analyze conversation and provide insights for suggestions."""
        conversation_id = request.query_params.get('conversation_id')
        
        if not conversation_id:
            return Response(
                {'error': 'conversation_id is required'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            conversation = Conversation.objects.get(id=conversation_id)
            
            # Check if user is a member of the conversation
            if not conversation.is_participant(request.user):
                raise PermissionDenied("You don't have access to this conversation")
            
            # Get conversation context
            context = RealTimeSuggestionService._build_conversation_context(conversation, request.user)
            
            # Analyze conversation patterns
            analysis = RealTimeSuggestionService._analyze_conversation_patterns(context['recent_messages'])
            
            return Response({
                'conversation_analysis': analysis,
                'message_count': len(context['recent_messages']),
                'participants': context['participants'],
                'conversation_type': context['conversation_type']
            })
            
        except Conversation.DoesNotExist:
            return Response(
                {'error': 'Conversation not found'}, 
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Error analyzing conversation: {str(e)}", exc_info=True)
            return Response(
                {'error': 'Failed to analyze conversation'}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
