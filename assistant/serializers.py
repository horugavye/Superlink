from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import (
    AssistantMemory, AssistantNotification, InterestAlchemy,
    CuriosityCollision, MicroCommunity, PostSuggestion,
    CommunitySuggestion, ConnectionSuggestion, ContentRecommendation,
    SkillRecommendation, ChatMessage
)
from community.models import Community, PersonalPost, CommunityPost, Comment

User = get_user_model()

class AssistantMemorySerializer(serializers.ModelSerializer):
    class Meta:
        model = AssistantMemory
        fields = [
            'personality_profile', 'learning_data', 'context_window',
            'community_engagement', 'content_preferences', 'interaction_patterns',
            'notification_preferences', 'notification_frequency', 'notification_quiet_hours',
            'notification_priority_threshold', 'suggestion_preferences', 'suggestion_history',
            'learning_preferences', 'interest_alchemy_preferences', 'curiosity_profile',
            'discovery_history', 'rating_insights', 'rating_preferences'
        ]

class AssistantNotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = AssistantNotification
        fields = [
            'notification_type', 'title', 'message', 'is_read',
            'created_at', 'priority', 'action_required', 'action_taken',
            'context', 'confidence_score', 'feedback'
        ]

class InterestAlchemySerializer(serializers.ModelSerializer):
    class Meta:
        model = InterestAlchemy
        fields = [
            'interest1', 'interest2', 'complementarity_score',
            'discovery_potential', 'success_metrics', 'micro_communities'
        ]

class CuriosityCollisionSerializer(serializers.ModelSerializer):
    class Meta:
        model = CuriosityCollision
        fields = [
            'interests', 'discovered_at', 'impact_score',
            'insights', 'follow_up_actions'
        ]

class MicroCommunitySerializer(serializers.ModelSerializer):
    class Meta:
        model = MicroCommunity
        fields = [
            'name', 'description', 'parent_community', 'interest_alchemy',
            'members_count', 'activity_score', 'discovery_insights'
        ]

class PostSuggestionSerializer(serializers.ModelSerializer):
    class Meta:
        model = PostSuggestion
        fields = [
            'suggestion_type', 'score', 'confidence', 'created_at',
            'is_active', 'reasoning', 'features', 'user_feedback',
            'relevance_factors', 'engagement_prediction', 'content_similarity',
            'user_history_impact'
        ]

class CommunitySuggestionSerializer(serializers.ModelSerializer):
    class Meta:
        model = CommunitySuggestion
        fields = [
            'suggestion_type', 'score', 'confidence', 'created_at',
            'is_active', 'reasoning', 'features', 'user_feedback',
            'member_similarity', 'activity_match', 'growth_potential',
            'topic_relevance'
        ]

class ConnectionSuggestionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConnectionSuggestion
        fields = [
            'suggestion_type', 'score', 'confidence', 'created_at',
            'is_active', 'reasoning', 'features', 'user_feedback',
            'mutual_connections', 'interest_overlap', 'activity_compatibility',
            'communication_style_match', 'potential_collaboration_score',
            'complementary_interests', 'curiosity_collisions',
            'micro_community_overlap', 'interest_alchemy_score'
        ]

class ContentRecommendationSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContentRecommendation
        fields = [
            'suggestion_type', 'score', 'confidence', 'created_at',
            'is_active', 'reasoning', 'features', 'user_feedback',
            'title', 'description', 'url', 'source',
            'engagement_metrics', 'content_vector'
        ]

class SkillRecommendationSerializer(serializers.ModelSerializer):
    class Meta:
        model = SkillRecommendation
        fields = [
            'suggestion_type', 'score', 'confidence', 'created_at',
            'is_active', 'reasoning', 'features', 'user_feedback',
            'skill_name', 'current_level', 'target_level',
            'learning_path', 'resources', 'estimated_time', 'priority'
        ]

class ChatMessageSerializer(serializers.ModelSerializer):
    user = serializers.SerializerMethodField()
    message = serializers.CharField()
    is_user_message = serializers.BooleanField()
    timestamp = serializers.DateTimeField(read_only=True)
    context = serializers.JSONField(required=False, default=dict)
    metadata = serializers.JSONField(required=False, default=dict)
    conversation_id = serializers.CharField(required=False)
    response = serializers.CharField(required=False)
    community = serializers.PrimaryKeyRelatedField(queryset=Community.objects.all(), required=False, allow_null=True)
    personal_post = serializers.PrimaryKeyRelatedField(queryset=PersonalPost.objects.all(), required=False, allow_null=True)
    community_post = serializers.PrimaryKeyRelatedField(queryset=CommunityPost.objects.all(), required=False, allow_null=True)
    comment = serializers.PrimaryKeyRelatedField(queryset=Comment.objects.all(), required=False, allow_null=True)
    
    class Meta:
        model = ChatMessage
        fields = [
            'id', 'user', 'message', 'is_user_message', 'timestamp',
            'context', 'metadata', 'conversation_id', 'response',
            'community', 'personal_post', 'community_post', 'comment'
        ]
        read_only_fields = ['id', 'timestamp']
    
    def get_user(self, obj):
        return {
            'id': obj.user.id,
            'username': obj.user.username,
            'email': obj.user.email
        }
    
    def validate(self, data):
        # Ensure message is not empty
        if not data.get('message', '').strip():
            raise serializers.ValidationError("Message cannot be empty")
        
        # Validate metadata if present
        metadata = data.get('metadata', {})
        if metadata:
            if not isinstance(metadata, dict):
                raise serializers.ValidationError("Metadata must be a dictionary")
            
            # Validate analysis if present
            analysis = metadata.get('analysis')
            if analysis and not isinstance(analysis, str):
                raise serializers.ValidationError("Analysis must be a string")
            
            # Validate context if present
            context = metadata.get('context')
            if context and not isinstance(context, str):
                raise serializers.ValidationError("Context must be a string")
        
        return data 