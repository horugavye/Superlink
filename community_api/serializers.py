from rest_framework import serializers
from community.models import (
    Community, Topic, CommunityMember, PersonalPost, CommunityPost,
    PostMedia, Comment, PostRating, Event, EventParticipant,
    Reply, CommentRating, ReplyRating, SavedPost
)
from connections_api.serializers import UserSerializer  # Updated import path
import json
from django.db.models import Q

class TopicSerializer(serializers.ModelSerializer):
    class Meta:
        model = Topic
        fields = ['id', 'name', 'color']

class CommunityMemberSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    role_display = serializers.CharField(source='get_role_display', read_only=True)
    avatar = serializers.SerializerMethodField()
    connectionStatus = serializers.SerializerMethodField()

    class Meta:
        model = CommunityMember
        fields = ['id', 'user', 'role', 'role_display', 'is_active', 'contributions', 
                 'joined_at', 'last_active', 'avatar', 'connectionStatus']
        read_only_fields = ['contributions', 'joined_at', 'last_active']

    def get_avatar(self, obj):
        if obj.user.avatar:
            if obj.user.avatar.name.startswith('http'):
                return obj.user.avatar.name
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.user.avatar.url)
            return f"http://localhost:8000{obj.user.avatar.url}"
        return "http://localhost:8000/media/avatars/default.jpeg"

    def get_connectionStatus(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return 'connect'
        if obj.user == request.user:
            return None
        from connections.models import Connection, ConnectionRequest
        # Check for active connection
        is_connected = Connection.objects.filter(
            (Q(user1=request.user, user2=obj.user) | Q(user1=obj.user, user2=request.user)),
            is_active=True
        ).exists()
        if is_connected:
            return 'accepted'
        # Check for pending request
        is_pending = ConnectionRequest.objects.filter(
            sender=request.user,
            receiver=obj.user,
            status='pending'
        ).exists()
        if is_pending:
            return 'pending'
        return 'connect'

class CommunitySerializer(serializers.ModelSerializer):
    total_members = serializers.IntegerField(source='members_count', read_only=True)
    active_members = serializers.IntegerField(read_only=True)
    activity_score = serializers.IntegerField(read_only=True)
    category_display = serializers.CharField(source='get_category_display', read_only=True)
    is_member = serializers.SerializerMethodField()
    member_role = serializers.SerializerMethodField()
    topics = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        default=list
    )
    rules = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        default=list
    )

    class Meta:
        model = Community
        fields = ['id', 'name', 'slug', 'description', 'icon', 'banner', 'category',
                 'category_display', 'topics', 'total_members', 'members_count', 'active_members',
                 'activity_score', 'is_private', 'rules', 'created_at',
                 'updated_at', 'is_member', 'member_role']
        read_only_fields = ['slug', 'total_members', 'members_count', 'active_members', 'activity_score',
                           'created_at', 'updated_at']

    def get_is_member(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj.members.filter(user=request.user).exists()
        return False

    def get_member_role(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            member = obj.members.filter(user=request.user).first()
            return member.role if member else None
        return None

class PostMediaSerializer(serializers.ModelSerializer):
    class Meta:
        model = PostMedia
        fields = ['id', 'type', 'file', 'thumbnail', 'order']

class CommentSerializer(serializers.ModelSerializer):
    author = UserSerializer(read_only=True)
    replies = serializers.SerializerMethodField()
    reply_count = serializers.SerializerMethodField()
    rating = serializers.FloatField(read_only=True)
    total_ratings = serializers.IntegerField(read_only=True)
    user_rating = serializers.SerializerMethodField()
    post = serializers.SerializerMethodField()

    class Meta:
        model = Comment
        fields = ['id', 'post', 'author', 'content', 'is_top_comment',
                 'created_at', 'updated_at', 'replies', 'reply_count',
                 'rating', 'total_ratings', 'user_rating']
        read_only_fields = ['created_at', 'updated_at']

    def get_post(self, obj):
        post = obj.personal_post or obj.community_post
        if not post:
            return None
        return {
            'id': post.id,
            'community': {
                'slug': post.community.slug if hasattr(post, 'community') and post.community else None
            }
        }

    def get_replies(self, obj):
        replies = obj.replies.all()[:3]  # Limit to 3 replies
        return ReplySerializer(replies, many=True, context=self.context).data

    def get_reply_count(self, obj):
        return obj.replies.count()

    def get_user_rating(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return 0
        rating = CommentRating.objects.filter(comment=obj, user=request.user).first()
        return rating.rating if rating else 0

class ReplySerializer(serializers.ModelSerializer):
    author = UserSerializer(read_only=True)
    rating = serializers.FloatField(read_only=True)
    total_ratings = serializers.IntegerField(read_only=True)
    user_rating = serializers.SerializerMethodField()
    comment = serializers.SerializerMethodField()

    class Meta:
        model = Reply
        fields = ['id', 'comment', 'author', 'content', 'created_at', 'updated_at',
                 'parent_reply', 'rating', 'total_ratings', 'user_rating']
        read_only_fields = ['created_at', 'updated_at']

    def get_comment(self, obj):
        post = obj.comment.personal_post or obj.comment.community_post
        if not post:
            return None
        return {
            'id': obj.comment.id,
            'post': {
                'id': post.id,
                'community': {
                    'slug': post.community.slug if hasattr(post, 'community') and post.community else None
                }
            }
        }

    def get_user_rating(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return 0
        rating = ReplyRating.objects.filter(reply=obj, user=request.user).first()
        return rating.rating if rating else 0

class PostRatingSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    post = serializers.SerializerMethodField()

    class Meta:
        model = PostRating
        fields = ['id', 'post', 'user', 'rating', 'created_at']
        read_only_fields = ['created_at']

    def get_post(self, obj):
        post = obj.personal_post or obj.community_post
        if not post:
            return None
        return {
            'id': post.id,
            'community': {
                'slug': post.community.slug if hasattr(post, 'community') and post.community else None
            }
        }

class CommentRatingSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    comment = CommentSerializer(read_only=True)
    rating = serializers.FloatField()

    class Meta:
        model = CommentRating
        fields = ['id', 'comment', 'user', 'rating', 'created_at']
        read_only_fields = ['created_at']

class ReplyRatingSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    reply = ReplySerializer(read_only=True)
    rating = serializers.FloatField()

    class Meta:
        model = ReplyRating
        fields = ['id', 'reply', 'user', 'rating', 'created_at']
        read_only_fields = ['created_at']

class PostSerializer(serializers.ModelSerializer):
    author = UserSerializer(read_only=True)
    community = CommunitySerializer(read_only=True)
    media = PostMediaSerializer(many=True, read_only=True)
    comments = serializers.SerializerMethodField()
    topics = serializers.SerializerMethodField()
    user_rating = serializers.SerializerMethodField()
    is_edited = serializers.BooleanField(read_only=True)
    author_role = serializers.SerializerMethodField()
    community_slug = serializers.SlugRelatedField(
        queryset=Community.objects.all(),
        write_only=True,
        required=False,
        source='community',
        slug_field='slug'
    )
    rating = serializers.FloatField(read_only=True)
    total_ratings = serializers.IntegerField(read_only=True)
    comment_count = serializers.IntegerField(read_only=True)
    top_comment = serializers.SerializerMethodField()

    class Meta:
        model = CommunityPost  # Default to CommunityPost
        fields = ['id', 'community', 'community_slug', 'author', 'author_role', 'title', 'content',
                 'visibility', 'is_pinned', 'is_edited', 'media', 'topics', 'view_count',
                 'rating', 'total_ratings', 'comment_count', 'comments',
                 'user_rating', 'created_at', 'updated_at', 'edited_at', 'top_comment']
        read_only_fields = ['view_count', 'rating', 'total_ratings', 'comment_count',
                           'created_at', 'updated_at', 'edited_at']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Set the model based on the instance type or request data
        if self.instance is not None:
            if isinstance(self.instance, PersonalPost):
                self.Meta.model = PersonalPost
            elif isinstance(self.instance, CommunityPost):
                self.Meta.model = CommunityPost
        else:
            # For new posts, determine the model based on the request data
            request = self.context.get('request')
            if request and request.data:
                visibility = request.data.get('visibility', '')
                if visibility.startswith('personal_'):
                    self.Meta.model = PersonalPost
                else:
                    self.Meta.model = CommunityPost

    def get_topics(self, obj):
        return [{'name': topic.name, 'color': topic.color} for topic in obj.topics.all()]

    def get_author_role(self, obj):
        if not obj.author or not obj.community:
            return None
        member = obj.community.members.filter(user=obj.author).first()
        return member.role if member else None

    def get_comments(self, obj):
        top_comments = obj.comments.filter(is_top_comment=True)[:1]
        if not top_comments:
            top_comments = obj.comments.order_by('-created_at')[:1]
        return CommentSerializer(top_comments, many=True, context=self.context).data

    def get_user_rating(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return 0
        
        # Check if the instance is a PersonalPost or CommunityPost
        if isinstance(obj, PersonalPost):
            rating = PostRating.objects.filter(
                personal_post=obj,
                user=request.user
            ).first()
        else:  # CommunityPost
            rating = PostRating.objects.filter(
                community_post=obj,
                user=request.user
            ).first()
            
        return rating.rating if rating else 0

    def get_top_comment(self, obj):
        top_comment = obj.comments.order_by('-created_at').first()
        if not top_comment:
            return None
        return {
            'author': UserSerializer(top_comment.author).data,
            'content': top_comment.content,
            'timestamp': top_comment.created_at
        }

    def validate(self, data):
        visibility = data.get('visibility', 'personal')
        community = data.get('community')

        # Validate visibility and community
        if visibility.startswith('personal_'):
            if community:
                raise serializers.ValidationError("Personal posts should not have a community")
        elif visibility == 'community':
            if not community:
                raise serializers.ValidationError("Community posts must have a community")
            
            # Validate that user is a member of the community
            request = self.context.get('request')
            if request and request.user.is_authenticated:
                if not CommunityMember.objects.filter(
                    community=community,
                    user=request.user,
                    is_active=True
                ).exists():
                    raise serializers.ValidationError(
                        f"You must be a member of {community.name} to post there"
                    )

        return data

    def to_representation(self, instance):
        data = super().to_representation(instance)
        # Ensure comment_count is set to the actual count
        data['comment_count'] = instance.comments.count()
        return data

class EventParticipantSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)

    class Meta:
        model = EventParticipant
        fields = ['id', 'event', 'user', 'is_attending', 'joined_at']
        read_only_fields = ['joined_at']

class EventSerializer(serializers.ModelSerializer):
    community = CommunitySerializer(read_only=True)
    created_by = UserSerializer(read_only=True)
    participants = serializers.SerializerMethodField()
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    event_type_display = serializers.CharField(source='get_event_type_display', read_only=True)
    is_participant = serializers.SerializerMethodField()

    class Meta:
        model = Event
        fields = ['id', 'community', 'title', 'description', 'event_type',
                 'event_type_display', 'start_date', 'end_date', 'max_participants',
                 'status', 'status_display', 'participants_count', 'is_active',
                 'created_by', 'participants', 'is_participant', 'settings',
                 'created_at']
        read_only_fields = ['participants_count', 'created_at', 'status']

    def get_participants(self, obj):
        participants = obj.participants.all()[:5]  # Limit to 5 participants
        return EventParticipantSerializer(participants, many=True, context=self.context).data

    def get_is_participant(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj.participants.filter(user=request.user).exists()
        return False

class SavedPostSerializer(serializers.ModelSerializer):
    post = serializers.SerializerMethodField()

    class Meta:
        model = SavedPost
        fields = ['id', 'post', 'saved_at']
        read_only_fields = ['saved_at']

    def get_post(self, obj):
        post = obj.personal_post or obj.community_post
        return PostSerializer(post, context=self.context).data 