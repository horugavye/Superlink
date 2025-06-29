from rest_framework import serializers
from django.contrib.auth.password_validation import validate_password
from users.models import (
    User, UserSocialProfile, UserAnalytics, UserBadge,
    UserCertification, UserProject, Skill, UserEndorsement,
    UserBlock, PersonalityTag, Language, UserAvailability,
    Education, WorkExperience, Achievement, UserInterest,
    UserFollowing
)
from django.core.validators import URLValidator, MinValueValidator, MaxValueValidator
from django.utils.translation import gettext_lazy as _
from django.db import models
import logging
import sys
from users.utils import is_user_online

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

class PersonalityTagSerializer(serializers.ModelSerializer):
    class Meta:
        model = PersonalityTag
        fields = ('id', 'name', 'color')

class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True, validators=[validate_password])
    password2 = serializers.CharField(write_only=True, required=True)
    personality_tags = serializers.ListField(
        child=serializers.DictField(child=serializers.CharField()),
        write_only=True,
        required=True
    )
    interests = serializers.ListField(
        child=serializers.CharField(),
        write_only=True,
        required=True
    )
    bio = serializers.CharField(write_only=True, required=True)
    location = serializers.CharField(write_only=True, required=True)

    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'password', 'password2', 'first_name', 'last_name', 'bio', 'location', 'personality_tags', 'interests')
        extra_kwargs = {
            'first_name': {'required': True},
            'last_name': {'required': True}
        }

    def validate(self, attrs):
        if attrs['password'] != attrs['password2']:
            raise serializers.ValidationError({"password": "Password fields didn't match."})
        if not attrs.get('bio'):
            raise serializers.ValidationError({"bio": "Bio is required."})
        if not attrs.get('location'):
            raise serializers.ValidationError({"location": "Location is required."})
        if not attrs.get('personality_tags') or not isinstance(attrs['personality_tags'], list) or len(attrs['personality_tags']) == 0:
            raise serializers.ValidationError({"personality_tags": "At least one personality tag is required."})
        if not attrs.get('interests') or not isinstance(attrs['interests'], list) or len(attrs['interests']) == 0:
            raise serializers.ValidationError({"interests": "At least one interest is required."})
        return attrs

    def create(self, validated_data):
        personality_tags = validated_data.pop('personality_tags', [])
        interests = validated_data.pop('interests', [])
        bio = validated_data.pop('bio', '')
        location = validated_data.pop('location', '')
        user = User.objects.create(
            username=validated_data['username'],
            email=validated_data['email'],
            first_name=validated_data['first_name'],
            last_name=validated_data['last_name'],
            bio=bio,
            location=location
        )
        user.set_password(validated_data['password'])
        user.save()
        # Add personality tags
        for tag_obj in personality_tags:
            name = tag_obj.get('name')
            color = tag_obj.get('color', '#8888ff')
            tag, _ = PersonalityTag.objects.get_or_create(name=name, defaults={'color': color})
            # If tag already exists but color is different, update color
            if tag.color != color:
                tag.color = color
                tag.save()
            user.personality_tags.add(tag)
        # Add interests
        for interest_name in interests:
            UserInterest.objects.get_or_create(user=user, name=interest_name)
        return user

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data.pop('password', None)
        data.pop('password2', None)
        return data

class UserSocialProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserSocialProfile
        fields = (
            'linkedin_url', 'github_url', 'twitter_url', 'facebook_url',
            'instagram_url', 'youtube_url', 'medium_url', 'portfolio_url',
            'blog_url'
        )

class UserAnalyticsSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserAnalytics
        fields = (
            'profile_views', 'search_appearances', 'engagement_rate',
            'avg_response_time', 'last_profile_update', 'activity_score',
            'metrics'
        )

class UserBadgeSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserBadge
        fields = ('name', 'description', 'icon', 'awarded_date', 'category', 'level')

class UserCertificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserCertification
        fields = (
            'id', 'name', 'issuing_organization', 'issue_date', 'expiry_date',
            'credential_id', 'credential_url', 'is_verified'
        )

class UserProjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserProject
        fields = (
            'title', 'description', 'url', 'start_date', 'end_date',
            'is_ongoing', 'technologies', 'team_size', 'role',
            'achievements', 'visibility'
        )

class SkillSerializer(serializers.ModelSerializer):
    level = serializers.IntegerField(
        validators=[
            MinValueValidator(0),
            MaxValueValidator(100)
        ]
    )

    class Meta:
        model = Skill
        fields = ('id', 'name', 'level')

class UserEndorsementSerializer(serializers.ModelSerializer):
    endorser = UserSerializer(read_only=True)
    
    class Meta:
        model = UserEndorsement
        fields = ('endorser', 'skill', 'comment', 'created_at')

class LanguageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Language
        fields = ('name', 'proficiency')

class UserAvailabilitySerializer(serializers.ModelSerializer):
    class Meta:
        model = UserAvailability
        fields = ('mentoring', 'collaboration', 'networking')

class EducationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Education
        fields = (
            'id',
            'school',
            'degree',
            'field',
            'year',
            'institution_type',
            'duration',
            'gpa',
            'start_date',
            'end_date',
            'is_current',
            'description',
            'achievements',
            'skills_learned',
            'location',
            'website',
            'is_verified'
        )

class WorkExperienceSerializer(serializers.ModelSerializer):
    highlights = serializers.ListField(
        child=serializers.CharField(allow_blank=False, trim_whitespace=True),
        required=False,
        allow_empty=True,
        default=list
    )
    skills = serializers.ListField(
        child=serializers.CharField(allow_blank=False, trim_whitespace=True),
        required=False,
        allow_empty=True,
        default=list
    )
    endorsements = serializers.ListField(
        required=False,
        allow_empty=True,
        default=list
    )

    class Meta:
        model = WorkExperience
        fields = (
            'id',
            'company', 
            'role', 
            'duration', 
            'highlights',
            'employment_type',
            'skills',
            'team_size',
            'projects_count',
            'impact_score',
            'endorsements',
            'endorsement_count'
        )

    def validate_highlights(self, value):
        if value is None:
            return []
        # Filter out empty strings and whitespace-only strings
        cleaned_highlights = [h.strip() for h in value if h and h.strip()]
        return cleaned_highlights

    def validate_skills(self, value):
        if value is None:
            return []
        # Filter out empty strings and whitespace-only strings
        cleaned_skills = [s.strip() for s in value if s and s.strip()]
        return cleaned_skills

    def to_representation(self, instance):
        data = super().to_representation(instance)
        # Ensure highlights and skills are always lists, even if None in database
        if data['highlights'] is None:
            data['highlights'] = []
        if data['skills'] is None:
            data['skills'] = []
        if data['endorsements'] is None:
            data['endorsements'] = []
        return data

class AchievementSerializer(serializers.ModelSerializer):
    class Meta:
        model = Achievement
        fields = ('id', 'title', 'date', 'description', 'category', 'impact', 'team', 'link')

class UserInterestSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserInterest
        fields = ('id', 'name')

class UserProfileSerializer(serializers.ModelSerializer):
    # Basic Information
    username = serializers.CharField(required=True)
    email = serializers.EmailField(required=True)
    first_name = serializers.CharField(required=True)
    last_name = serializers.CharField(required=True)
    name = serializers.SerializerMethodField()
    
    # Connection Information
    connection_status = serializers.SerializerMethodField()
    connection_request_id = serializers.SerializerMethodField()
    
    # Profile Information
    bio = serializers.CharField(required=False, allow_blank=True)
    avatar = serializers.ImageField(required=False, allow_null=True)
    cover_photo = serializers.ImageField(required=False, allow_null=True)
    personal_story = serializers.CharField(required=False, allow_blank=True)
    
    # Contact Information
    location = serializers.CharField(required=False, allow_blank=True)
    website = serializers.URLField(required=False, allow_blank=True, validators=[URLValidator()])
    phone_number = serializers.CharField(required=False, allow_blank=True)
    date_of_birth = serializers.DateField(required=False, allow_null=True)
    gender = serializers.ChoiceField(
        choices=['male', 'female', 'other', 'prefer_not_to_say'],
        required=False,
        allow_blank=True
    )
    
    # Professional Information
    rating = serializers.FloatField(
        read_only=True,
        validators=[MinValueValidator(0.0), MaxValueValidator(5.0)]
    )
    reputation_points = serializers.IntegerField(read_only=True)
    connection_strength = serializers.IntegerField(read_only=True)
    is_verified = serializers.BooleanField(read_only=True)
    is_mentor = serializers.BooleanField(required=False)
    account_type = serializers.ChoiceField(
        choices=['personal', 'professional', 'business'],
        required=False
    )
    
    # Privacy Settings
    profile_visibility = serializers.ChoiceField(
        choices=['public', 'private', 'connections'],
        required=False
    )
    two_factor_enabled = serializers.BooleanField(required=False)
    email_verified = serializers.BooleanField(read_only=True)
    
    # Activity Status
    last_active = serializers.DateTimeField(read_only=True)
    online_status = serializers.ChoiceField(
        choices=['online', 'away', 'offline', 'busy'],
        required=False
    )
    is_online = serializers.BooleanField(read_only=True)
    
    # Preferences
    language_preference = serializers.CharField(required=False, allow_blank=True)
    theme_preference = serializers.ChoiceField(
        choices=['light', 'dark', 'system'],
        required=False
    )
    timezone = serializers.CharField(required=False, allow_blank=True)
    
    # Statistics
    post_count = serializers.IntegerField(read_only=True)
    follower_count = serializers.IntegerField(read_only=True)
    following_count = serializers.IntegerField(read_only=True)
    contribution_points = serializers.IntegerField(read_only=True)
    profile_completion = serializers.IntegerField(read_only=True)
    endorsement_count = serializers.IntegerField(read_only=True)

    # Related Data
    social_profile = UserSocialProfileSerializer(read_only=True)
    analytics = UserAnalyticsSerializer(read_only=True)
    badges = UserBadgeSerializer(many=True, read_only=True)
    certifications = UserCertificationSerializer(many=True, read_only=True)
    projects = UserProjectSerializer(many=True, read_only=True)
    skills = SkillSerializer(many=True, read_only=True)
    received_endorsements = UserEndorsementSerializer(many=True, read_only=True)
    personality_tags = PersonalityTagSerializer(many=True, read_only=True)
    languages = LanguageSerializer(many=True, read_only=True)
    availability = UserAvailabilitySerializer(read_only=True)
    education = EducationSerializer(many=True, read_only=True)
    work_experience = WorkExperienceSerializer(many=True, read_only=True)
    achievements = AchievementSerializer(many=True, read_only=True)
    interests = UserInterestSerializer(many=True, read_only=True)

    def get_name(self, obj):
        return obj.get_full_name()

    def get_connection_status(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            print(f"[CONNECTION CHECK] User not authenticated, returning 'connect'")
            logger.info(f"[CONNECTION CHECK] User not authenticated, returning 'connect'")
            return 'connect'
            
        # Check if users are already connected
        from connections.models import Connection, ConnectionRequest
        try:
            current_user = request.user
            profile_user = obj  # This is the user whose profile we're viewing
            
            print(f"\n=== CONNECTION STATUS CHECK ===")
            print(f"Checking connection between current user {current_user.id} and profile user {profile_user.id}")
            logger.info(f"\n=== CONNECTION STATUS CHECK ===")
            logger.info(f"Checking connection between current user {current_user.id} and profile user {profile_user.id}")
            
            # First check for active connections
            is_connected = Connection.objects.filter(
                (models.Q(user1=current_user, user2=profile_user) | 
                 models.Q(user1=profile_user, user2=current_user)),
                is_active=True
            ).exists()
            
            if is_connected:
                print(f"Found active connection between users {current_user.id} and {profile_user.id}")
                logger.info(f"Found active connection between users {current_user.id} and {profile_user.id}")
                return 'accepted'
            
            # Then check for any connection request (pending, accepted, or rejected)
            has_request = ConnectionRequest.objects.filter(
                (models.Q(sender=current_user, receiver=profile_user) |
                 models.Q(sender=profile_user, receiver=current_user))
            ).exists()
            
            if not has_request:
                print(f"No connection request found between users {current_user.id} and {profile_user.id}")
                logger.info(f"No connection request found between users {current_user.id} and {profile_user.id}")
                return 'connect'
            
            # If there is a request, check if it's pending
            pending_request = ConnectionRequest.objects.filter(
                sender=current_user,
                receiver=profile_user,
                status='pending'
            ).exists()
            
            if pending_request:
                print(f"Found pending request from {current_user.id} to {profile_user.id}")
                logger.info(f"Found pending request from {current_user.id} to {profile_user.id}")
                return 'pending'
            
            # If we get here, there was a request but it's not pending (could be accepted/rejected/canceled)
            print(f"Found non-pending request between users {current_user.id} and {profile_user.id}")
            logger.info(f"Found non-pending request between users {current_user.id} and {profile_user.id}")
            return 'connect'
            
        except Exception as e:
            print(f"Error checking connection status: {str(e)}")
            logger.error(f"Error checking connection status: {str(e)}", exc_info=True)
            return 'connect'

    def get_connection_request_id(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
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

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get('request')
        
        print(f"Processing user data for {instance.username}:")
        print(f"Raw avatar value: {instance.avatar}")
        print(f"Avatar field value: {instance.avatar.name if instance.avatar else 'No avatar'}")
        print(f"Avatar URL: {instance.avatar.url if instance.avatar else 'No URL'}")
        
        # Handle avatar URL
        if instance.avatar and instance.avatar.name != 'media/avatars/profile-default-icon-2048x2045-u3j7s5nj.png':
            if isinstance(data['avatar'], str) and data['avatar'].startswith('http'):
                print(f"Using existing full URL avatar: {data['avatar']}")
            else:
                if request:
                    data['avatar'] = request.build_absolute_uri(instance.avatar.url)
                    print(f"Built absolute URI for avatar: {data['avatar']}")
                else:
                    data['avatar'] = f"http://localhost:8000{instance.avatar.url}"
                    print(f"Built local URL for avatar: {data['avatar']}")
        else:
            data['avatar'] = "http://localhost:8000/media/avatars/profile-default-icon-2048x2045-u3j7s5nj.png"
            print("Using default avatar URL because no custom avatar found")
        
        print(f"Final avatar URL: {data['avatar']}")
        
        # Handle cover photo URL
        if data.get('cover_photo'):
            if isinstance(data['cover_photo'], str) and data['cover_photo'].startswith('http'):
                pass  # Keep the URL as is
            else:
                data['cover_photo'] = request.build_absolute_uri(instance.cover_photo.url) if request else f"http://localhost:8000{instance.cover_photo.url}"

        return data

    def get_is_online(self, obj):
        """Get whether the user is currently online."""
        return is_user_online(obj)

    class Meta:
        model = User
        fields = (
            # Basic Information
            'id', 'username', 'email', 'first_name', 'last_name', 'name',
            
            # Connection Information
            'connection_status', 'connection_request_id',
            
            # Profile Information
            'bio', 'avatar', 'cover_photo', 'personal_story',
            
            # Contact Information
            'location', 'website', 'phone_number', 'date_of_birth', 'gender',
            
            # Professional Information
            'rating', 'reputation_points', 'connection_strength',
            'is_verified', 'is_mentor', 'account_type',
            
            # Privacy Settings
            'profile_visibility', 'two_factor_enabled', 'email_verified',
            
            # Activity Status
            'last_active', 'online_status', 'is_online',
            
            # Preferences
            'language_preference', 'theme_preference', 'timezone',
            
            # Statistics
            'post_count', 'follower_count', 'following_count',
            'contribution_points', 'profile_completion', 'endorsement_count',
            
            # Related Data
            'social_profile', 'analytics', 'badges', 'certifications',
            'projects', 'skills', 'received_endorsements', 'personality_tags',
            'languages', 'availability', 'education', 'work_experience',
            'achievements', 'interests'
        )

    def validate_phone_number(self, value):
        if value and not value.isdigit():
            raise serializers.ValidationError(_("Phone number must contain only digits"))
        return value

    def validate_website(self, value):
        if value and not value.startswith(('http://', 'https://')):
            value = 'https://' + value
        return value

    def update(self, instance, validated_data):
        instance.update_profile_completion()
        return super().update(instance, validated_data)