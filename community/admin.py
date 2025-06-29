from django.contrib import admin
from .models import (
    Community, Topic, CommunityMember, PersonalPost, CommunityPost,
    PostMedia, Comment, PostRating, Event, EventParticipant,
    Reply, CommentRating, ReplyRating, SavedPost
)

class TopicInline(admin.TabularInline):
    model = Topic
    extra = 1
    fields = ('name', 'color')

@admin.register(Community)
class CommunityAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'category', 'is_private', 'members_count', 'created_at')
    list_filter = ('category', 'is_private')
    search_fields = ('name', 'description')
    prepopulated_fields = {'slug': ('name',)}
    readonly_fields = ('members_count', 'created_at', 'updated_at')
    inlines = [TopicInline]

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        form.base_fields['icon'].help_text = 'Community profile image/icon (recommended size: 256x256px)'
        form.base_fields['banner'].help_text = 'Community cover photo (recommended size: 1200x400px)'
        return form

@admin.register(Topic)
class TopicAdmin(admin.ModelAdmin):
    list_display = ('name', 'community', 'color', 'get_post_count')
    list_filter = ('community',)
    search_fields = ('name', 'community__name')
    list_select_related = ('community',)
    
    def get_post_count(self, obj):
        return obj.personalpost_posts.count() + obj.communitypost_posts.count()
    get_post_count.short_description = 'Posts'

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related('personalpost_posts', 'communitypost_posts')

@admin.register(CommunityMember)
class CommunityMemberAdmin(admin.ModelAdmin):
    list_display = ('user', 'community', 'role', 'is_active', 'joined_at')
    list_filter = ('role', 'is_active', 'community')
    search_fields = ('user__username', 'community__name')
    readonly_fields = ('joined_at', 'last_active')

@admin.register(PersonalPost)
class PersonalPostAdmin(admin.ModelAdmin):
    list_display = ('title', 'author', 'visibility', 'is_pinned', 'created_at')
    list_filter = ('visibility', 'is_pinned')
    search_fields = ('title', 'content')
    readonly_fields = ('created_at', 'updated_at', 'edited_at', 'view_count', 'rating', 'total_ratings', 'comment_count')
    filter_horizontal = ('topics',)

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        # Add help text for visibility field
        form.base_fields['visibility'].help_text = (
            'Personal: Only visible in personal feed. '
            'Community: Only visible in selected community.'
        )
        return form

@admin.register(CommunityPost)
class CommunityPostAdmin(admin.ModelAdmin):
    list_display = ('title', 'author', 'community', 'is_pinned', 'created_at')
    list_filter = ('is_pinned', 'community')
    search_fields = ('title', 'content', 'community__name')
    readonly_fields = ('created_at', 'updated_at', 'edited_at', 'view_count', 'rating', 'total_ratings', 'comment_count')
    filter_horizontal = ('topics',)
    
    def formfield_for_manytomany(self, db_field, request, **kwargs):
        if db_field.name == "topics":
            # Get the selected community from the form
            community_id = request.POST.get('community') or request.GET.get('community')
            if community_id:
                kwargs["queryset"] = Topic.objects.filter(community_id=community_id)
            else:
                kwargs["queryset"] = Topic.objects.none()
        return super().formfield_for_manytomany(db_field, request, **kwargs)

@admin.register(PostMedia)
class PostMediaAdmin(admin.ModelAdmin):
    list_display = ('get_post', 'type', 'order')
    list_filter = ('type',)
    search_fields = ('personal_post__title', 'community_post__title')
    list_select_related = ('personal_post', 'community_post')

    def get_post(self, obj):
        post = obj.personal_post or obj.community_post
        return post.title if post else 'No Post'
    get_post.short_description = 'Post'

@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ('get_post', 'author', 'content', 'is_top_comment', 'created_at')
    list_filter = ('is_top_comment',)
    search_fields = ('content', 'personal_post__title', 'community_post__title', 'author__username')
    readonly_fields = ('created_at', 'updated_at')
    list_select_related = ('personal_post', 'community_post', 'author')

    def get_post(self, obj):
        post = obj.personal_post or obj.community_post
        return post.title if post else 'No Post'
    get_post.short_description = 'Post'

@admin.register(Reply)
class ReplyAdmin(admin.ModelAdmin):
    list_display = ('comment', 'author', 'content', 'created_at')
    search_fields = ('content', 'comment__content', 'author__username')
    readonly_fields = ('created_at', 'updated_at')

@admin.register(PostRating)
class PostRatingAdmin(admin.ModelAdmin):
    list_display = ('get_post', 'user', 'rating', 'created_at')
    list_filter = ('rating',)
    search_fields = ('personal_post__title', 'community_post__title', 'user__username')
    readonly_fields = ('created_at',)
    list_select_related = ('personal_post', 'community_post', 'user')

    def get_post(self, obj):
        post = obj.personal_post or obj.community_post
        return post.title if post else 'No Post'
    get_post.short_description = 'Post'

@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ('title', 'community', 'event_type', 'status', 'start_date', 'end_date')
    list_filter = ('event_type', 'status', 'community')
    search_fields = ('title', 'description', 'community__name')
    readonly_fields = ('created_at', 'participants_count')

@admin.register(EventParticipant)
class EventParticipantAdmin(admin.ModelAdmin):
    list_display = ('event', 'user', 'is_attending', 'joined_at')
    list_filter = ('is_attending',)
    search_fields = ('event__title', 'user__username')
    readonly_fields = ('joined_at',)

@admin.register(CommentRating)
class CommentRatingAdmin(admin.ModelAdmin):
    list_display = ('comment', 'user', 'rating', 'created_at')
    list_filter = ('rating',)
    search_fields = ('comment__content', 'user__username')
    readonly_fields = ('created_at',)

@admin.register(ReplyRating)
class ReplyRatingAdmin(admin.ModelAdmin):
    list_display = ('reply', 'user', 'rating', 'created_at')
    list_filter = ('rating',)
    search_fields = ('reply__content', 'user__username')
    readonly_fields = ('created_at',)

@admin.register(SavedPost)
class SavedPostAdmin(admin.ModelAdmin):
    list_display = ('get_post', 'user', 'saved_at')
    list_filter = ('saved_at',)
    search_fields = ('user__username', 'personal_post__title', 'community_post__title')
    readonly_fields = ('saved_at',)
    list_select_related = ('user', 'personal_post', 'community_post')

    def get_post(self, obj):
        post = obj.personal_post or obj.community_post
        return post.title if post else 'No Post'
    get_post.short_description = 'Post'
