from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.db.models import Q
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
import os
import mimetypes
from .models import Message, Conversation, MessageReaction, MessageThread, ConversationMember, File
from .serializers import ConversationMemberSerializer, FileSerializer, MessageSerializer, MessageThreadSerializer
from django.conf import settings
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from stories.models import Story  # Add this import at the top

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def send_message(request):
    """
    Send a message to a conversation.
    Supports both text messages and multiple file attachments.
    """
    print('=== SEND MESSAGE REQUEST ===')
    print('Request data:', request.data)
    conversation_id = request.data.get('conversation_id')
    content = request.data.get('content', '')
    message_type = request.data.get('message_type', 'text')
    reply_to_id = request.data.get('reply_to_id') or request.data.get('parent_message_id')
    print('Reply to ID:', reply_to_id)
    thread_id = request.data.get('thread_id')
    is_thread_reply = request.data.get('is_thread_reply') == 'true'  # Convert string 'true' to boolean
    
    story_id = request.data.get('story')  # New: get story id from request
    story = None
    if story_id:
        try:
            story = Story.objects.get(id=story_id)
        except Story.DoesNotExist:
            story = None  # Or handle error as needed
    
    conversation = get_object_or_404(Conversation, id=conversation_id)
    
    # Check if user is a participant
    if not conversation.is_participant(request.user):
        return Response({'error': 'Not a participant in this conversation'}, 
                       status=status.HTTP_403_FORBIDDEN)
    
    # Handle file uploads
    files = request.FILES.getlist('files')  # Get multiple files
    uploaded_files = []
    
    for file in files:
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
        
        # Create File object
        file_obj = File.objects.create(
            file=file,
            file_name=file.name,
            file_type=file.content_type,
            file_size=file.size,
            category=category,
            uploaded_by=request.user
        )
        uploaded_files.append(file_obj)
    
    # Create message
    message = Message.objects.create(
        conversation=conversation,
        sender=request.user,
        content=content,
        message_type=message_type,
        story=story  # Attach the story if provided
    )
    
    # Add files to message
    if uploaded_files:
        message.files.set(uploaded_files)
        
        # Update message type based on files
        if any(f.category == 'image' for f in uploaded_files):
            message.message_type = 'image'
        elif any(f.category == 'video' for f in uploaded_files):
            message.message_type = 'video'
        elif any(f.category == 'audio' for f in uploaded_files):
            message.message_type = 'voice'
        else:
            message.message_type = 'file'
        message.save()
    
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
    
    # Handle thread
    if thread_id:
        thread = get_object_or_404(MessageThread, id=thread_id)
        message.thread = thread
        # If is_thread_reply is true, ensure the message is marked as a thread reply
        if is_thread_reply:
            message.is_thread_reply = True
    
    # Serialize message with context
    serializer = MessageSerializer(message, context={'request': request})
    serialized_data = serializer.data
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
    
    return Response(serialized_data)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_messages(request, conversation_id):
    """
    Get messages for a conversation with pagination.
    """
    try:
        conversation = get_object_or_404(Conversation, id=conversation_id)
        
        # Check if user is a participant
        if not conversation.is_participant(request.user):
            return Response(
                {'error': 'Not a participant in this conversation'}, 
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Get pagination parameters
        try:
            page = int(request.GET.get('page', 1))
            page_size = int(request.GET.get('page_size', 50))
        except ValueError:
            return Response(
                {'error': 'Invalid pagination parameters'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        start = (page - 1) * page_size
        end = start + page_size
        
        # Get messages with related data
        messages = Message.objects.filter(conversation=conversation)\
            .select_related('sender', 'reply_to', 'thread')\
            .prefetch_related('files', 'reactions')\
            .order_by('-created_at')[start:end]
        
        # Serialize messages
        serializer = MessageSerializer(messages, many=True, context={'request': request})
        return Response(serializer.data)
        
    except Exception as e:
        return Response(
            {'error': str(e)}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def update_message_status(request, message_id):
    """
    Update the status of a message (sent, delivered, read).
    """
    message = get_object_or_404(Message, id=message_id)
    new_status = request.data.get('status')
    
    # Check if user is a participant
    if not message.conversation.is_participant(request.user):
        return Response({'error': 'Not a participant in this conversation'}, 
                       status=status.HTTP_403_FORBIDDEN)
    
    try:
        message.update_status(new_status)
        return Response({'status': message.status})
    except ValueError as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def react_to_message(request, message_id):
    """
    Add or remove a reaction to a message.
    """
    message = get_object_or_404(Message, id=message_id)
    emoji = request.data.get('emoji')
    
    # Check if user is a participant
    if not message.conversation.is_participant(request.user):
        return Response({'error': 'Not a participant in this conversation'}, 
                       status=status.HTTP_403_FORBIDDEN)
    
    # Check if reaction already exists
    reaction = MessageReaction.objects.filter(
        message=message,
        user=request.user,
        emoji=emoji
    ).first()
    
    if reaction:
        # Remove reaction if it exists
        reaction.delete()
        return Response({'status': 'reaction_removed'})
    else:
        # Add new reaction
        reaction = MessageReaction.objects.create(
            message=message,
            user=request.user,
            emoji=emoji
        )
        return Response({
            'id': reaction.id,
            'user': reaction.user.username,
            'emoji': reaction.emoji,
            'created_at': reaction.created_at
        })

@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def create_thread(request, conversation_id, message_id):
    try:
        # Get the parent message
        parent_message = get_object_or_404(Message, id=message_id)
        
        # Check if user is a participant in the conversation
        if not parent_message.conversation.participants.filter(id=request.user.id).exists():
            return Response({'error': 'You are not a participant in this conversation'}, status=403)
        
        # Check if this is a group conversation
        if parent_message.conversation.type == 'direct':
            return Response({'error': 'Threads can only be created in group conversations'}, status=400)
        
        # Check if thread already exists
        try:
            existing_thread = MessageThread.objects.get(parent_message=parent_message)
        except MessageThread.DoesNotExist:
            existing_thread = None
        
        if request.method == 'GET':
            if existing_thread:
                serializer = MessageThreadSerializer(existing_thread)
                return Response(serializer.data)
            return Response({'error': 'Thread not found'}, status=404)
        
        # For POST request, create new thread if it doesn't exist
        if not existing_thread:
            # Create the thread directly
            thread = MessageThread.objects.create(
                parent_message=parent_message,
                created_by=request.user
            )
            # Add the creator as a participant
            thread.participants.add(request.user)
            
            # Serialize the created thread
            serializer = MessageThreadSerializer(thread)
            return Response(serializer.data, status=201)
        
        serializer = MessageThreadSerializer(existing_thread)
        return Response(serializer.data)
        
    except Exception as e:
        return Response({'error': str(e)}, status=500)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_conversation_members(request, conversation_id):
    """
    Get all members of a conversation.
    """
    conversation = get_object_or_404(Conversation, id=conversation_id)
    
    # Check if user is a participant
    if not conversation.is_participant(request.user):
        return Response({'error': 'Not a participant in this conversation'}, 
                       status=status.HTTP_403_FORBIDDEN)
    
    # Get all members
    members = conversation.members.all()
    serializer = ConversationMemberSerializer(members, many=True)
    
    return Response(serializer.data)

@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
def update_group_through_conversation(request, conversation_id):
    """
    Update a group's details through its associated conversation.
    Also updates the conversation name to match the group name.
    """
    conversation = get_object_or_404(Conversation, id=conversation_id)
    
    # Check if this is a group conversation
    if conversation.type != 'group':
        return Response({'error': 'This endpoint is only for group conversations'}, 
                       status=status.HTTP_400_BAD_REQUEST)
    
    # Check if user is a member and has admin privileges
    member = conversation.members.filter(user=request.user).first()
    if not member or member.role not in ['admin']:
        return Response({'error': 'Only group admins can update group details'}, 
                       status=status.HTTP_403_FORBIDDEN)
    
    # Get the associated group
    group = conversation.group
    if not group:
        return Response({'error': 'No group associated with this conversation'}, 
                       status=status.HTTP_400_BAD_REQUEST)
    
    # Update group details
    if 'name' in request.data:
        new_name = request.data['name']
        group.name = new_name
        # Also update the conversation name to match
        conversation.name = new_name
        conversation.save()
    
    if 'avatar' in request.FILES:
        group.avatar = request.FILES['avatar']
    
    group.save()
    
    # Broadcast the update to all group members
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        f"chat_{conversation_id}",
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
    
    return Response({
        'id': group.id,
        'name': group.name,
        'avatar': group.avatar.url if group.avatar else None,
        'conversation': {
            'id': conversation.id,
            'name': conversation.name
        }
    })

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_message(request, conversation_id, message_id):
    """
    Get a specific message from a conversation.
    """
    try:
        conversation = get_object_or_404(Conversation, id=conversation_id)
        
        # Check if user is a participant
        if not conversation.is_participant(request.user):
            return Response(
                {'error': 'Not a participant in this conversation'}, 
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Get the message with related data
        message = get_object_or_404(
            Message.objects.select_related('sender', 'reply_to', 'thread')
                         .prefetch_related('files', 'reactions'),
            id=message_id,
            conversation=conversation
        )
        
        # Serialize message
        serializer = MessageSerializer(message, context={'request': request})
        return Response(serializer.data)
        
    except Exception as e:
        return Response(
            {'error': str(e)}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
