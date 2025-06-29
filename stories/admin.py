from django.contrib import admin
from .models import (
    Story, StoryCollaborator, StoryInteractive, StoryInteraction,
    StoryShare, StoryRating, StoryView, StoryTag,
    StoryBookmark, StoryReport, StoryAnalytics
)


@admin.register(Story)
class StoryAdmin(admin.ModelAdmin):
    list_display = ('id', 'author', 'type', 'theme', 'content_preview', 'created_at', 'is_active', 'is_public', 'views_count')
    list_filter = ('type', 'theme', 'is_active', 'is_public', 'created_at', 'expires_at')
    search_fields = ('content', 'author__username', 'location_name', 'tags')
    readonly_fields = ('id', 'created_at', 'updated_at', 'views_count', 'shares_count', 'rating', 'total_ratings')
    list_per_page = 25
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('id', 'author', 'type', 'content', 'theme', 'tags')
        }),
        ('Media', {
            'fields': ('media_url', 'media_file', 'duration')
        }),
        ('Location', {
            'fields': ('location_name', 'latitude', 'longitude')
        }),
        ('Time Capsule', {
            'fields': ('unlock_date', 'is_unlocked')
        }),
        ('Story Thread', {
            'fields': ('parent_story', 'thread_id', 'thread_title', 'thread_order')
        }),
        ('AI Remix', {
            'fields': ('original_story', 'ai_style', 'ai_filters')
        }),
        ('Privacy & Visibility', {
            'fields': ('is_public', 'allow_sharing')
        }),
        ('Timing', {
            'fields': ('created_at', 'updated_at', 'expires_at', 'is_active')
        }),
        ('Statistics', {
            'fields': ('views_count', 'shares_count', 'rating', 'total_ratings')
        }),
    )
    
    def content_preview(self, obj):
        return obj.content[:50] + '...' if len(obj.content) > 50 else obj.content
    content_preview.short_description = 'Content'


@admin.register(StoryCollaborator)
class StoryCollaboratorAdmin(admin.ModelAdmin):
    list_display = ('story', 'user', 'role', 'can_edit', 'can_delete', 'joined_at')
    list_filter = ('role', 'can_edit', 'can_delete', 'joined_at')
    search_fields = ('story__content', 'user__username')
    readonly_fields = ('joined_at',)


@admin.register(StoryInteractive)
class StoryInteractiveAdmin(admin.ModelAdmin):
    list_display = ('story', 'type', 'options_count')
    list_filter = ('type',)
    search_fields = ('story__content',)
    
    def options_count(self, obj):
        return len(obj.options) if obj.options else 0
    options_count.short_description = 'Options Count'


@admin.register(StoryInteraction)
class StoryInteractionAdmin(admin.ModelAdmin):
    list_display = ('story', 'user', 'interaction_type', 'created_at')
    list_filter = ('interaction_type', 'created_at')
    search_fields = ('story__content', 'user__username')
    readonly_fields = ('created_at',)


@admin.register(StoryShare)
class StoryShareAdmin(admin.ModelAdmin):
    list_display = ('story', 'user', 'platform', 'created_at')
    list_filter = ('platform', 'created_at')
    search_fields = ('story__content', 'user__username')
    readonly_fields = ('created_at',)


@admin.register(StoryRating)
class StoryRatingAdmin(admin.ModelAdmin):
    list_display = ('story', 'user', 'rating', 'created_at', 'updated_at')
    list_filter = ('rating', 'created_at')
    search_fields = ('story__content', 'user__username')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(StoryView)
class StoryViewAdmin(admin.ModelAdmin):
    list_display = ('story', 'user', 'viewed_at', 'view_duration', 'completed')
    list_filter = ('completed', 'viewed_at')
    search_fields = ('story__content', 'user__username')
    readonly_fields = ('viewed_at',)


@admin.register(StoryTag)
class StoryTagAdmin(admin.ModelAdmin):
    list_display = ('name', 'color', 'usage_count', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('name',)
    readonly_fields = ('usage_count', 'created_at')


@admin.register(StoryBookmark)
class StoryBookmarkAdmin(admin.ModelAdmin):
    list_display = ('story', 'user', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('story__content', 'user__username')
    readonly_fields = ('created_at',)


@admin.register(StoryReport)
class StoryReportAdmin(admin.ModelAdmin):
    list_display = ('story', 'reporter', 'reason', 'is_resolved', 'created_at')
    list_filter = ('reason', 'is_resolved', 'created_at')
    search_fields = ('story__content', 'reporter__username', 'description')
    readonly_fields = ('created_at',)
    actions = ['mark_as_resolved', 'mark_as_unresolved']
    
    def mark_as_resolved(self, request, queryset):
        queryset.update(is_resolved=True)
    mark_as_resolved.short_description = "Mark selected reports as resolved"
    
    def mark_as_unresolved(self, request, queryset):
        queryset.update(is_resolved=False)
    mark_as_unresolved.short_description = "Mark selected reports as unresolved"


@admin.register(StoryAnalytics)
class StoryAnalyticsAdmin(admin.ModelAdmin):
    list_display = ('story', 'total_views', 'unique_views', 'avg_view_duration', 'completion_rate', 'engagement_rate', 'last_updated')
    list_filter = ('last_updated',)
    search_fields = ('story__content',)
    readonly_fields = ('total_views', 'unique_views', 'avg_view_duration', 'completion_rate', 'engagement_rate', 'shares_count', 'last_updated')
    actions = ['update_analytics']
    
    def update_analytics(self, request, queryset):
        for analytics in queryset:
            analytics.update_analytics()
    update_analytics.short_description = "Update analytics for selected stories"
