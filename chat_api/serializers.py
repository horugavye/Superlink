from rest_framework import serializers
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
from users.models import User
from django.utils import timezone
from datetime import timedelta

class UserSerializer(serializers.ModelSerializer):
    is_online = serializers.SerializerMethodField()
    personality_tags = serializers.SerializerMethodField()
    
    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name', 
            'avatar', 'is_online', 'personality_tags'
        ]
        read_only_fields = ['id', 'email']
    
    def get_is_online(self, obj):
        """
        Determine if user is online based on online_status and last_active.
        Consider user online if:
        1. online_status is 'online' AND
        2. last_active is within the last 5 minutes
        """
        if not obj.last_active:
            return False
        
        # Check if user has been active in the last 5 minutes
        five_minutes_ago = timezone.now() - timedelta(minutes=5)
        recently_active = obj.last_active >= five_minutes_ago
        
        # User is online if status is 'online' and recently active
        return obj.online_status == 'online' and recently_active
    
    def get_personality_tags(self, obj):
        # This would need to be implemented based on your personality system
        return []

class FileSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()
    thumbnail_url = serializers.SerializerMethodField()
    
    class Meta:
        model = File
        fields = [
            'id', 'file', 'file_name', 'file_type', 'file_size',
            'category', 'thumbnail', 'duration',
            'created_at', 'uploaded_by', 'url', 'thumbnail_url'
        ]
        read_only_fields = ['created_at', 'uploaded_by']
    
    def get_url(self, obj):
        request = self.context.get('request')
        if request and obj.file:
            # Get the file path relative to MEDIA_ROOT
            path = obj.file.name
            # Build the absolute URL
            url = request.build_absolute_uri(f'/media/{path}')
            return url
        return None
    
    def get_thumbnail_url(self, obj):
        request = self.context.get('request')
        if request and obj.thumbnail:
            # Get the thumbnail path relative to MEDIA_ROOT
            path = obj.thumbnail.name
            # Build the absolute URL
            url = request.build_absolute_uri(f'/media/{path}')
            return url
        return None

class GroupSerializer(serializers.ModelSerializer):
    group_id = serializers.IntegerField(read_only=True)
    conversation_id = serializers.IntegerField(read_only=True)
    
    class Meta:
        model = Group
        fields = ['id', 'name', 'description', 'avatar', 'created_by', 'created_at', 
                 'updated_at', 'is_private', 'invite_code', 'max_members', 'rules', 
                 'settings', 'group_id', 'conversation_id']
        read_only_fields = ['created_by', 'created_at', 'updated_at', 'invite_code']
    
    def validate_name(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError("Group name cannot be empty")
        return value.strip()
    
    def validate(self, data):
        # Add any additional validation here
        return data

class MessageReactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = MessageReaction
        fields = '__all__'

class MessageEffectSerializer(serializers.ModelSerializer):
    class Meta:
        model = MessageEffect
        fields = ['id', 'message', 'effect_type', 'intensity', 'created_at']
        read_only_fields = ['created_at']

class LinkPreviewSerializer(serializers.ModelSerializer):
    class Meta:
        model = LinkPreview
        fields = ['id', 'message', 'url', 'title', 'description', 'image_url', 'created_at']
        read_only_fields = ['created_at']

class MessageSerializer(serializers.ModelSerializer):
    sender = UserSerializer(read_only=True)
    files = FileSerializer(many=True, read_only=True)
    reactions = MessageReactionSerializer(many=True, read_only=True)
    reply_to = serializers.SerializerMethodField()
    thread = serializers.SerializerMethodField()
    is_edited = serializers.BooleanField(read_only=True)
    is_pinned = serializers.BooleanField(read_only=True)
    is_forwarded = serializers.BooleanField(read_only=True)
    is_thread_reply = serializers.SerializerMethodField()

    class Meta:
        model = Message
        fields = [
            'id', 'conversation', 'sender', 'content', 'message_type',
            'files', 'reactions', 'reply_to', 'thread', 'created_at',
            'updated_at', 'status', 'is_edited', 'is_pinned', 'is_forwarded',
            'is_thread_reply'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'status']

    def get_reply_to(self, obj):
        if obj.reply_to:
            return {
                'id': obj.reply_to.id,
                'content': obj.reply_to.content,
                'sender': {
                    'id': obj.reply_to.sender.id,
                    'username': obj.reply_to.sender.username
                }
            }
        return None

    def get_thread(self, obj):
        # Check if this message is a parent message of a thread
        try:
            thread = MessageThread.objects.filter(parent_message=obj).first()
            if thread:
                return {
                    'id': thread.id,
                    'parent_message_id': obj.id,
                    'created_at': thread.created_at,
                    'last_reply_at': thread.last_reply_at,
                    'participants_count': thread.participants.count(),
                    'replies_count': thread.messages.count()
                }
        except MessageThread.DoesNotExist:
            pass

        # Check if this message is part of a thread
        if obj.thread:
            return {
                'id': obj.thread.id,
                'parent_message_id': obj.thread.parent_message.id,
                'created_at': obj.thread.created_at,
                'last_reply_at': obj.thread.last_reply_at,
                'participants_count': obj.thread.participants.count(),
                'replies_count': obj.thread.messages.count()
            }
        return None

    def get_is_thread_reply(self, obj):
        # A message is a thread reply if:
        # 1. It has is_thread_reply=True, or
        # 2. It has a thread and is not the parent message
        return bool(obj.is_thread_reply or (obj.thread and obj.thread.parent_message_id != obj.id))

class MessageThreadSerializer(serializers.ModelSerializer):
    parent_message = serializers.SerializerMethodField()
    participants = UserSerializer(many=True, read_only=True)
    messages = serializers.SerializerMethodField()
    created_by = UserSerializer(read_only=True)

    class Meta:
        model = MessageThread
        fields = [
            'id', 'parent_message', 'participants', 'messages',
            'created_at', 'last_reply_at', 'created_by'
        ]
        read_only_fields = ['id', 'created_at', 'last_reply_at']

    def get_parent_message(self, obj):
        if obj.parent_message:
            return {
                'id': obj.parent_message.id,
                'content': obj.parent_message.content,
                'sender': {
                    'id': obj.parent_message.sender.id,
                    'username': obj.parent_message.sender.username
                },
                'created_at': obj.parent_message.created_at
            }
        return None

    def get_messages(self, obj):
        messages = obj.messages.all().order_by('created_at')
        return [{
            'id': msg.id,
            'content': msg.content,
            'sender': {
                'id': msg.sender.id,
                'username': msg.sender.username
            },
            'created_at': msg.created_at,
            'is_edited': msg.is_edited,
            'files': FileSerializer(msg.files.all(), many=True).data
        } for msg in messages]

class ConversationMemberSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    
    class Meta:
        model = ConversationMember
        fields = ['id', 'user', 'role', 'joined_at', 'last_read', 
                 'is_muted', 'is_pinned', 'unread_count']

class ConversationSerializer(serializers.ModelSerializer):
    participant1 = UserSerializer(read_only=True)
    participant2 = UserSerializer(read_only=True)
    last_message = MessageSerializer(read_only=True)
    members = ConversationMemberSerializer(many=True, read_only=True)
    group = GroupSerializer(read_only=True)
    
    class Meta:
        model = Conversation
        fields = [
            'id', 'type', 'name', 'group', 'participant1', 'participant2',
            'created_at', 'updated_at', 'is_active', 'last_message', 'members'
        ]
        read_only_fields = ['created_at', 'updated_at'] 