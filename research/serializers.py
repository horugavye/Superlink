from rest_framework import serializers
from users.models import User, PersonalityTag
from django.db.models import Q

class PersonalityTagSerializer(serializers.ModelSerializer):
    class Meta:
        model = PersonalityTag
        fields = ['name', 'color']

class UserSerializer(serializers.ModelSerializer):
    personality_tags = PersonalityTagSerializer(many=True)
    name = serializers.SerializerMethodField()
    avatarUrl = serializers.SerializerMethodField()
    connection_status = serializers.SerializerMethodField()
    connection_request_id = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'username', 'first_name', 'last_name', 'avatar', 'role', 'personality_tags', 'name', 'avatarUrl', 'connection_status', 'connection_request_id']

    def get_name(self, obj):
        full_name = f"{obj.first_name} {obj.last_name}".strip()
        return full_name if full_name else obj.username

    def get_avatarUrl(self, obj):
        request = self.context.get('request', None)
        if obj.avatar:
            avatar_url = obj.avatar.url if hasattr(obj.avatar, 'url') else obj.avatar
            if request is not None:
                return request.build_absolute_uri(avatar_url)
            else:
                return avatar_url
        return None

    def get_connection_status(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return 'connect'
            
        # Don't show connection status for self
        if obj == request.user:
            return None
            
        # Check if users are already connected
        from connections.models import Connection, ConnectionRequest
        try:
            current_user = request.user
            profile_user = obj
            
            # First check for active connections
            is_connected = Connection.objects.filter(
                (Q(user1=current_user, user2=profile_user) | 
                 Q(user1=profile_user, user2=current_user)),
                is_active=True
            ).exists()
            
            if is_connected:
                return 'connected'
            
            # Then check for pending connection request from current user
            pending_request = ConnectionRequest.objects.filter(
                sender=current_user,
                receiver=profile_user,
                status='pending'
            ).exists()
            
            if pending_request:
                return 'pending'
            
            # Check for pending request from other user to current user
            received_pending = ConnectionRequest.objects.filter(
                sender=profile_user,
                receiver=current_user,
                status='pending'
            ).exists()
            
            if received_pending:
                return 'received'
                
            return 'connect'
            
        except Exception as e:
            return 'connect'

    def get_connection_request_id(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return None
            
        # Don't return request ID for self
        if obj == request.user:
            return None
            
        # Check if there's a pending connection request
        from connections.models import ConnectionRequest
        try:
            existing_request = ConnectionRequest.objects.filter(
                sender=request.user,
                receiver=obj,
                status='pending'
            ).first()
            if existing_request:
                return existing_request.id
        except Exception:
            pass
            
        return None 