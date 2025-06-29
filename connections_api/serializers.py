from rest_framework import serializers
from connections.models import Connection, ConnectionRequest, UserSuggestion
from django.contrib.auth import get_user_model
from django.conf import settings
import logging

User = get_user_model()
logger = logging.getLogger(__name__)

class UserSerializer(serializers.ModelSerializer):
    personality_tags = serializers.SerializerMethodField()
    badges = serializers.SerializerMethodField()
    avatar = serializers.SerializerMethodField()
    interests = serializers.SerializerMethodField()
    name = serializers.SerializerMethodField()
    avatarUrl = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name', 'name',
            'avatar', 'avatarUrl', 'role', 'personality_tags', 'badges',
            'last_active', 'location', 'interests'
        ]

    def get_name(self, obj):
        if obj.first_name and obj.last_name:
            return f"{obj.first_name} {obj.last_name}"
        return obj.username

    def get_avatar(self, obj):
        if obj.avatar:
            if obj.avatar.name.startswith('http'):
                return obj.avatar.name
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.avatar.url)
            return f"http://localhost:8000{obj.avatar.url}"
        return "http://localhost:8000/media/avatars/default.jpeg"

    def get_avatarUrl(self, obj):
        request = self.context.get('request', None)
        if obj.avatar:
            avatar_url = obj.avatar.url if hasattr(obj.avatar, 'url') else obj.avatar
            if request is not None:
                return request.build_absolute_uri(avatar_url)
            else:
                return avatar_url
        return None

    def get_personality_tags(self, obj):
        try:
            # Get all personality tags for the user through the ManyToManyField
            tags = obj.personality_tags.all()
            
            # Log the raw tags for debugging
            print(f"Raw personality tags for user {obj.id}:", [
                {'name': tag.name, 'color': tag.color} for tag in tags
            ])
            
            # Return the tags with their colors
            return [
                {
                    'name': tag.name,
                    'color': tag.color
                }
                for tag in tags
            ]
        except Exception as e:
            print(f"Error getting personality tags for user {obj.id}: {str(e)}")
            return []

    def get_badges(self, obj):
        try:
            return [
                {
                    'name': badge.name,
                    'icon': badge.icon or 'star',
                    'color': badge.color or 'bg-yellow-100 text-yellow-700'
                }
                for badge in obj.badges.all()
            ]
        except Exception:
            return []

    def get_interests(self, obj):
        try:
            interests = obj.interests.all()
            return [
                {
                    'id': interest.id,
                    'name': interest.name
                }
                for interest in interests
            ]
        except Exception as e:
            print(f"Error getting interests for user {obj.id}: {str(e)}")
            return []

class ConnectionSerializer(serializers.ModelSerializer):
    user1 = UserSerializer(read_only=True)
    user2 = UserSerializer(read_only=True)

    class Meta:
        model = Connection
        fields = ['id', 'user1', 'user2', 'created_at', 'updated_at', 
                 'connection_strength', 'last_interaction', 'is_active']
        read_only_fields = ['created_at', 'updated_at']

class ConnectionRequestSerializer(serializers.ModelSerializer):
    sender = UserSerializer(read_only=True)
    receiver = UserSerializer(read_only=True)
    receiver_id = serializers.IntegerField(write_only=True)

    class Meta:
        model = ConnectionRequest
        fields = ['id', 'sender', 'receiver', 'receiver_id', 'status', 'message', 
                 'created_at', 'updated_at', 'mutual_connections', 
                 'match_score', 'connection_strength', 'common_interests', 'match_highlights']
        read_only_fields = ['created_at', 'updated_at', 'mutual_connections', 
                           'match_score', 'connection_strength', 'common_interests', 'match_highlights']

    def create(self, validated_data):
        receiver_id = validated_data.pop('receiver_id')
        validated_data['receiver_id'] = receiver_id
        return super().create(validated_data)

class UserSuggestionSerializer(serializers.ModelSerializer):
    suggested_user = UserSerializer(read_only=True)
    connection_strength = serializers.SerializerMethodField()
    mutual_friends = serializers.SerializerMethodField()
    connection_status = serializers.SerializerMethodField()
    connection_request_id = serializers.SerializerMethodField()
    is_alchy = serializers.SerializerMethodField()

    class Meta:
        model = UserSuggestion
        fields = [
            'id', 'suggested_user', 'score', 'created_at', 
            'updated_at', 'match_highlights', 'common_interests', 
            'mutual_connections', 'is_active', 'connection_strength',
            'mutual_friends', 'connection_status', 'connection_request_id',
            'is_alchy'
        ]
        read_only_fields = [
            'created_at', 'updated_at', 'score', 
            'match_highlights', 'common_interests', 
            'mutual_connections', 'connection_strength',
            'mutual_friends', 'connection_status', 'connection_request_id',
            'is_alchy'
        ]

    def get_connection_strength(self, obj):
        """
        Calculate connection strength based on:
        - Mutual connections (40%)
        - Common interests (40%)
        - Profile completeness (20%)
        """
        logger.info(f"\n=== Calculating Connection Strength for Suggestion ===")
        logger.info(f"Suggestion ID: {obj.id}")
        logger.info(f"Suggested User: {obj.suggested_user.username}")
        
        # Calculate mutual connections score (40% weight)
        mutual_connections = obj.mutual_connections or 0
        max_mutual_connections = 10  # Normalize to a reasonable maximum
        mutual_score = min((mutual_connections / max_mutual_connections), 1) * 40
        
        logger.info(f"Mutual connections: {mutual_connections}")
        logger.info(f"Mutual connections score: {mutual_score}")
        
        # Calculate common interests score (40% weight)
        common_interests = len(obj.common_interests or [])
        max_interests = 10  # Normalize to a reasonable maximum
        interest_score = min((common_interests / max_interests), 1) * 40
        
        logger.info(f"Common interests: {common_interests}")
        logger.info(f"Common interests score: {interest_score}")
        
        # Calculate profile completeness (20% weight)
        def get_profile_completion(user):
            fields = ['first_name', 'last_name', 'avatar', 'role', 'location', 'interests']
            completed = sum(1 for f in fields if getattr(user, f, None))
            completion = completed / len(fields)
            logger.info(f"Profile completion for {user.username}: {completion * 100}%")
            return completion
        
        profile_score = get_profile_completion(obj.suggested_user) * 20
        logger.info(f"Profile completion score: {profile_score}")
        
        # Calculate total strength
        total_strength = min(round(mutual_score + interest_score + profile_score), 100)
        
        logger.info(f"Final connection strength: {total_strength}")
        return total_strength

    def get_mutual_friends(self, obj):
        return []  # Default empty list as per frontend expectation

    def get_connection_request_id(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return None
            
        # Check if there's a pending connection request
        from connections.models import ConnectionRequest
        try:
            existing_request = ConnectionRequest.objects.filter(
                sender=request.user,
                receiver=obj.suggested_user,
                status='pending'
            ).first()
            if existing_request:
                return existing_request.id
        except Exception:
            pass
            
        return None

    def get_connection_status(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return 'connect'
            
        # Check if there's a pending connection request
        from connections.models import ConnectionRequest
        try:
            existing_request = ConnectionRequest.objects.filter(
                sender=request.user,
                receiver=obj.suggested_user,
                status='pending'
            ).exists()
            if existing_request:
                return 'pending'
        except Exception:
            pass
            
        return 'connect'

    def get_is_alchy(self, obj):
        # Consider a suggestion "alchy" if it has match_highlights and a high score (e.g., >= 60)
        return bool(obj.match_highlights) and obj.score >= 60
