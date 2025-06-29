from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import (
    Story, StoryCollaborator, StoryInteractive, StoryInteraction,
    StoryShare, StoryRating, StoryView, StoryTag,
    StoryBookmark, StoryReport, StoryAnalytics
)

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'first_name', 'last_name', 'email']


class StoryTagSerializer(serializers.ModelSerializer):
    class Meta:
        model = StoryTag
        fields = '__all__'


class StoryCollaboratorSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    
    class Meta:
        model = StoryCollaborator
        fields = '__all__'


class StoryInteractiveSerializer(serializers.ModelSerializer):
    class Meta:
        model = StoryInteractive
        fields = '__all__'


class StoryInteractionSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    
    class Meta:
        model = StoryInteraction
        fields = '__all__'


class StoryShareSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    
    class Meta:
        model = StoryShare
        fields = '__all__'


class StoryRatingSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    
    class Meta:
        model = StoryRating
        fields = '__all__'


class StoryViewSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    
    class Meta:
        model = StoryView
        fields = '__all__'


class StoryBookmarkSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    
    class Meta:
        model = StoryBookmark
        fields = '__all__'


class StoryReportSerializer(serializers.ModelSerializer):
    reporter = UserSerializer(read_only=True)
    
    class Meta:
        model = StoryReport
        fields = '__all__'


class StoryAnalyticsSerializer(serializers.ModelSerializer):
    class Meta:
        model = StoryAnalytics
        fields = '__all__'


class StorySerializer(serializers.ModelSerializer):
    author = UserSerializer(read_only=True)
    collaborators = StoryCollaboratorSerializer(many=True, read_only=True)
    interactive = StoryInteractiveSerializer(read_only=True)
    shares = StoryShareSerializer(many=True, read_only=True)
    ratings = StoryRatingSerializer(many=True, read_only=True)
    views = StoryViewSerializer(many=True, read_only=True)
    bookmarks = StoryBookmarkSerializer(many=True, read_only=True)
    reports = StoryReportSerializer(many=True, read_only=True)
    analytics = StoryAnalyticsSerializer(read_only=True)
    child_stories = serializers.SerializerMethodField()
    remixes = serializers.SerializerMethodField()
    userRating = serializers.SerializerMethodField()
    totalRatings = serializers.SerializerMethodField()
    viewed = serializers.SerializerMethodField()
    
    class Meta:
        model = Story
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at', 'views_count', 'shares_count', 'rating', 'total_ratings']
    
    def get_child_stories(self, obj):
        child_stories = Story.objects.filter(parent_story=obj).order_by('thread_order')
        return StorySerializer(child_stories, many=True).data
    
    def get_remixes(self, obj):
        remixes = Story.objects.filter(original_story=obj)
        return StorySerializer(remixes, many=True).data

    def get_userRating(self, obj):
        user = self.context.get('request').user if self.context.get('request') else None
        if not user or not user.is_authenticated:
            return 0
        rating = obj.ratings.filter(user=user).first()
        return rating.rating if rating else 0

    def get_totalRatings(self, obj):
        return obj.ratings.count()

    def get_viewed(self, obj):
        user = self.context.get('request').user if self.context.get('request') else None
        if not user or not user.is_authenticated:
            return False
        return obj.views.filter(user=user).exists()


class StoryCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Story
        fields = [
            'type', 'content', 'theme', 'media_url', 'media_file', 'duration',
            'location_name', 'latitude', 'longitude', 'unlock_date',
            'parent_story', 'thread_id', 'thread_title', 'thread_order',
            'original_story', 'ai_style', 'ai_filters', 'tags',
            'expires_at', 'is_public', 'allow_sharing'
        ]
    
    def create(self, validated_data):
        validated_data['author'] = self.context['request'].user
        return super().create(validated_data)


class StoryUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Story
        fields = [
            'content', 'theme', 'media_url', 'media_file', 'duration',
            'location_name', 'latitude', 'longitude', 'unlock_date',
            'thread_title', 'thread_order', 'ai_style', 'ai_filters', 'tags',
            'expires_at', 'is_public', 'allow_sharing'
        ]


class StoryInteractionCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = StoryInteraction
        fields = ['story', 'interaction_type', 'value']
    
    def create(self, validated_data):
        validated_data['user'] = self.context['request'].user
        return super().create(validated_data)


class StoryRatingCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = StoryRating
        fields = ['story', 'rating']
    
    def create(self, validated_data):
        validated_data['user'] = self.context['request'].user
        return super().create(validated_data)


class StoryViewCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = StoryView
        fields = ['story', 'view_duration', 'completed']
    
    def create(self, validated_data):
        validated_data['user'] = self.context['request'].user
        return super().create(validated_data)


class StoryBookmarkCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = StoryBookmark
        fields = ['story']
    
    def create(self, validated_data):
        validated_data['user'] = self.context['request'].user
        return super().create(validated_data)


class StoryReportCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = StoryReport
        fields = ['story', 'reason', 'description']
    
    def create(self, validated_data):
        validated_data['reporter'] = self.context['request'].user
        return super().create(validated_data)


class StoryCollaboratorCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = StoryCollaborator
        fields = ['story', 'user', 'role', 'can_edit', 'can_delete']


class StoryInteractiveCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = StoryInteractive
        fields = ['story', 'type', 'options', 'correct_answer', 'settings'] 