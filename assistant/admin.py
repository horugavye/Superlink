from django.contrib import admin
from django.utils.html import format_html
from .models import (
    AssistantMemory, AssistantInterest, AISuggestion, PostSuggestion,
    CommunitySuggestion, ConnectionSuggestion, ContentRecommendation,
    SkillRecommendation, InterestAlchemy, CuriosityCollision,
    AIRatingInsight, RatingPattern, AssistantNotification, ChatMessage,
    CommunityScore, MicroCommunity
)
import json

@admin.register(AssistantMemory)
class AssistantMemoryAdmin(admin.ModelAdmin):
    list_display = ('user', 'last_interaction', 'notification_frequency', 'get_engagement_score')
    list_filter = ('notification_frequency', 'last_interaction')
    search_fields = ('user__username', 'user__email')
    readonly_fields = ('last_interaction',)
    fieldsets = (
        ('User Information', {
            'fields': ('user', 'last_interaction')
        }),
        ('Learning & Preferences', {
            'fields': (
                'personality_profile', 'learning_data', 'content_preferences',
                'interaction_patterns', 'learning_preferences'
            )
        }),
        ('Notification Settings', {
            'fields': (
                'notification_preferences', 'notification_frequency',
                'notification_quiet_hours', 'notification_priority_threshold'
            )
        }),
        ('AI Features', {
            'fields': (
                'interest_alchemy_preferences', 'curiosity_profile',
                'discovery_history', 'rating_insights', 'rating_preferences'
            )
        })
    )

    def get_engagement_score(self, obj):
        if not obj.community_engagement:
            return 0
        return sum(engagement.get('activity_score', 0) for engagement in obj.community_engagement.values())
    get_engagement_score.short_description = 'Total Engagement Score'

@admin.register(AssistantInterest)
class AssistantInterestAdmin(admin.ModelAdmin):
    list_display = ('user_interest', 'weight', 'last_updated', 'get_vector_length')
    list_filter = ('last_updated', 'weight')
    search_fields = ('user_interest__interest', 'user_interest__user__username')
    readonly_fields = ('last_updated',)

    def get_vector_length(self, obj):
        return len(obj.vector) if obj.vector else 0
    get_vector_length.short_description = 'Vector Length'

@admin.register(PostSuggestion)
class PostSuggestionAdmin(admin.ModelAdmin):
    list_display = ('user', 'get_post', 'score', 'confidence', 'is_active', 'created_at')
    list_filter = ('is_active', 'is_rejected', 'created_at')
    search_fields = ('user__username', 'personal_post__title', 'community_post__title')
    readonly_fields = ('created_at', 'updated_at')

    def get_post(self, obj):
        post = obj.personal_post or obj.community_post
        return post.title if post else '-'
    get_post.short_description = 'Post'

@admin.register(CommunitySuggestion)
class CommunitySuggestionAdmin(admin.ModelAdmin):
    list_display = ('user', 'community', 'score', 'confidence', 'member_similarity', 'is_active')
    list_filter = ('is_active', 'is_rejected', 'created_at')
    search_fields = ('user__username', 'community__name')

@admin.register(ConnectionSuggestion)
class ConnectionSuggestionAdmin(admin.ModelAdmin):
    list_display = ('user', 'suggested_user', 'score', 'interest_alchemy_score', 'is_active')
    list_filter = ('is_active', 'is_rejected', 'created_at')
    search_fields = ('user__username', 'suggested_user__username')
    readonly_fields = ('complementary_interests', 'curiosity_collisions', 'micro_community_overlap')

@admin.register(ContentRecommendation)
class ContentRecommendationAdmin(admin.ModelAdmin):
    list_display = ('user', 'title', 'source', 'score', 'confidence', 'is_active')
    list_filter = ('is_active', 'is_rejected', 'created_at', 'source')
    search_fields = ('user__username', 'title', 'description')

@admin.register(SkillRecommendation)
class SkillRecommendationAdmin(admin.ModelAdmin):
    list_display = ('user', 'skill_name', 'current_level', 'target_level', 'priority', 'is_active')
    list_filter = ('is_active', 'is_rejected', 'priority', 'created_at')
    search_fields = ('user__username', 'skill_name')

@admin.register(InterestAlchemy)
class InterestAlchemyAdmin(admin.ModelAdmin):
    list_display = ('get_interests', 'complementarity_score', 'discovery_potential', 'created_at')
    list_filter = ('created_at', 'last_updated')
    search_fields = ('interest1__interest', 'interest2__interest')
    readonly_fields = ('success_metrics', 'micro_communities')

    def get_interests(self, obj):
        return f"{obj.interest1.interest} + {obj.interest2.interest}"
    get_interests.short_description = 'Interest Pair'

@admin.register(CuriosityCollision)
class CuriosityCollisionAdmin(admin.ModelAdmin):
    list_display = ('user', 'get_interests', 'impact_score', 'discovered_at')
    list_filter = ('discovered_at', 'impact_score')
    search_fields = ('user__username', 'interests__interest')
    readonly_fields = ('insights', 'follow_up_actions')

    def get_interests(self, obj):
        return ", ".join(interest.interest for interest in obj.interests.all())
    get_interests.short_description = 'Interests'

@admin.register(AIRatingInsight)
class AIRatingInsightAdmin(admin.ModelAdmin):
    list_display = ('get_content', 'sentiment_score', 'engagement_prediction', 'created_at')
    list_filter = ('created_at', 'updated_at')
    search_fields = ('content_type__model', 'object_id')
    readonly_fields = ('rating_patterns', 'quality_indicators')

    def get_content(self, obj):
        content = obj.content_object
        if hasattr(content, 'title'):
            return content.title
        return f"{obj.content_type.model} #{obj.object_id}"
    get_content.short_description = 'Content'

@admin.register(RatingPattern)
class RatingPatternAdmin(admin.ModelAdmin):
    list_display = ('user', 'pattern_type', 'confidence', 'created_at')
    list_filter = ('pattern_type', 'created_at')
    search_fields = ('user__username', 'pattern_type')
    readonly_fields = ('pattern_data',)

@admin.register(AssistantNotification)
class AssistantNotificationAdmin(admin.ModelAdmin):
    list_display = ('user', 'notification_type', 'title', 'is_read', 'priority', 'created_at')
    list_filter = ('notification_type', 'is_read', 'priority', 'created_at')
    search_fields = ('user__username', 'title', 'message')
    readonly_fields = ('created_at', 'context', 'feedback')

@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ('user', 'get_message_preview', 'is_user_message', 'timestamp', 'get_context', 'get_metadata')
    list_filter = ('is_user_message', 'timestamp')
    search_fields = ('user__username', 'message')
    readonly_fields = ('timestamp', 'context', 'metadata')

    def get_message_preview(self, obj):
        return obj.message[:50] + '...' if len(obj.message) > 50 else obj.message
    get_message_preview.short_description = 'Message'

    def get_context(self, obj):
        return format_html('<pre>{}</pre>', json.dumps(obj.context, indent=2)) if obj.context else '-'
    get_context.short_description = 'Context'

    def get_metadata(self, obj):
        return format_html('<pre>{}</pre>', json.dumps(obj.metadata, indent=2)) if obj.metadata else '-'
    get_metadata.short_description = 'Metadata'

@admin.register(CommunityScore)
class CommunityScoreAdmin(admin.ModelAdmin):
    list_display = ('get_post', 'total_ratings', 'average_score', 'engagement_score', 'trending_score')
    list_filter = ('last_updated',)
    search_fields = ('personal_post__title', 'community_post__title')
    readonly_fields = ('last_updated', 'rating_distribution')

    def get_post(self, obj):
        post = obj.personal_post or obj.community_post
        return post.title if post else '-'
    get_post.short_description = 'Post'

@admin.register(MicroCommunity)
class MicroCommunityAdmin(admin.ModelAdmin):
    list_display = ('name', 'parent_community', 'members_count', 'activity_score', 'created_at')
    list_filter = ('created_at', 'activity_score')
    search_fields = ('name', 'description', 'parent_community__name')
    readonly_fields = ('discovery_insights',)
