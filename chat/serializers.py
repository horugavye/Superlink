from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import (
    Message, 
    Conversation, 
    MessageReaction, 
    MessageThread,
    ConversationMember,
    File,
    Group
)
from django.core.files.storage import default_storage
from stories.serializers import StorySerializer

User = get_user_model()

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
        read_only_fields = ['created_at', 'uploaded_by', 'file_type', 'category']
    
    def get_url(self, obj):
        return obj.get_url()
    
    def get_thumbnail_url(self, obj):
        return obj.get_thumbnail_url()
    
    def validate(self, data):
        # Extract file extension from file_name if not provided
        if 'file_name' in data and 'file_type' not in data:
            data['file_type'] = data['file_name'].split('.')[-1].lower()
        return data

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name']

class MessageReactionSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    count = serializers.SerializerMethodField()
    users = serializers.SerializerMethodField()
    isSelected = serializers.SerializerMethodField()
    
    class Meta:
        model = MessageReaction
        fields = ['id', 'user', 'emoji', 'created_at', 'count', 'users', 'isSelected']
    
    def get_count(self, obj):
        return MessageReaction.objects.filter(
            message=obj.message,
            emoji=obj.emoji
        ).count()
    
    def get_users(self, obj):
        return list(MessageReaction.objects.filter(
            message=obj.message,
            emoji=obj.emoji
        ).values_list('user__username', flat=True))
    
    def get_isSelected(self, obj):
        request = self.context.get('request')
        if request and request.user:
            return MessageReaction.objects.filter(
                message=obj.message,
                emoji=obj.emoji,
                user=request.user
            ).exists()
        return False

class MessageSerializer(serializers.ModelSerializer):
    sender = UserSerializer(read_only=True)
    reactions = serializers.SerializerMethodField()
    files = FileSerializer(many=True, read_only=True)
    reply_to = serializers.SerializerMethodField()
    is_thread_reply = serializers.SerializerMethodField()
    story = StorySerializer(read_only=True)
    
    class Meta:
        model = Message
        fields = [
            'id', 'conversation', 'sender', 'content', 'message_type',
            'files', 'status', 'created_at', 'updated_at', 'is_edited',
            'is_pinned', 'is_forwarded', 'reply_to', 'thread', 'reactions',
            'is_thread_reply', 'story'
        ]
        read_only_fields = ['sender', 'created_at', 'updated_at']
    
    def get_reactions(self, obj):
        # Get all reactions for this message
        reactions = MessageReaction.objects.filter(message=obj)
        
        # Group reactions by emoji
        reaction_groups = {}
        for reaction in reactions:
            if reaction.emoji not in reaction_groups:
                reaction_groups[reaction.emoji] = {
                    'emoji': reaction.emoji,
                    'count': 0,
                    'users': [],
                    'isSelected': False
                }
            
            reaction_groups[reaction.emoji]['count'] += 1
            reaction_groups[reaction.emoji]['users'].append(reaction.user.username)
            
            # Check if current user has this reaction
            request = self.context.get('request')
            if request and request.user and reaction.user == request.user:
                reaction_groups[reaction.emoji]['isSelected'] = True
        
        return list(reaction_groups.values())
    
    def get_is_thread_reply(self, obj):
        # A message is a thread reply if:
        # 1. It has is_thread_reply=True, or
        # 2. It has a thread and is not the parent message
        return bool(obj.is_thread_reply or (obj.thread and obj.thread.parent_message_id != obj.id))
    
    def get_reply_to(self, obj):
        if obj.reply_to:
            return {
                'id': obj.reply_to.id,
                'content': obj.reply_to.content,
                'sender': UserSerializer(obj.reply_to.sender).data,
                'files': FileSerializer(obj.reply_to.files.all(), many=True).data
            }
        return None

class ConversationMemberSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    
    class Meta:
        model = ConversationMember
        fields = ['id', 'user', 'role', 'joined_at', 'last_read', 
                 'is_muted', 'is_pinned', 'unread_count']

class GroupSerializer(serializers.ModelSerializer):
    class Meta:
        model = Group
        fields = ['id', 'name']

class ConversationSerializer(serializers.ModelSerializer):
    members = ConversationMemberSerializer(many=True, read_only=True)
    last_message = MessageSerializer(read_only=True)
    participant1 = UserSerializer(read_only=True)
    participant2 = UserSerializer(read_only=True)
    group = GroupSerializer(read_only=True)
    
    class Meta:
        model = Conversation
        fields = [
            'id', 'type', 'name', 'group', 'participant1', 'participant2',
            'created_at', 'updated_at', 'is_active', 'last_message', 'members',
            'group_id'
        ]
        read_only_fields = ['created_at', 'updated_at']

class MessageThreadSerializer(serializers.ModelSerializer):
    parent_message = MessageSerializer(read_only=True)
    participants = UserSerializer(many=True, read_only=True)
    messages = MessageSerializer(many=True, read_only=True)
    
    class Meta:
        model = MessageThread
        fields = ['id', 'parent_message', 'participants', 'messages',
                 'last_reply_at', 'created_at', 'created_by']
        read_only_fields = ['created_at', 'last_reply_at']
    
    def create(self, validated_data):
        # Get the parent_message from the context
        parent_message = self.context.get('parent_message')
        if not parent_message:
            raise serializers.ValidationError("Parent message is required")
        
        # Create the thread with the parent message
        thread = MessageThread.objects.create(
            parent_message=parent_message,
            created_by=self.context.get('request').user
        )
        
        # Add the creator as a participant
        thread.participants.add(self.context.get('request').user)
        
        return thread 