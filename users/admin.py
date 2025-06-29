from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.db.models import Count
from .models import (
    User, PersonalityTag, Skill, Language, UserAvailability,
    Education, WorkExperience, Achievement, UserInterest, UserFollowing,
    UserSocialProfile, UserAnalytics, UserBadge, UserCertification,
    UserProject, UserEndorsement, UserBlock
)

@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ('username', 'email', 'full_name', 'location', 'rating', 'account_type', 
                   'profile_completion', 'is_verified', 'online_status', 'last_active')
    list_filter = ('is_staff', 'is_active', 'is_verified', 'account_type', 
                  'profile_visibility', 'online_status', 'is_mentor')
    search_fields = ('username', 'email', 'first_name', 'last_name', 'location')
    readonly_fields = ('profile_completion', 'last_active', 'date_joined', 'last_login')
    fieldsets = (
        ('Personal Info', {
            'fields': ('username', 'email', 'first_name', 'last_name', 'avatar', 
                      'cover_photo', 'bio', 'personal_story', 'date_of_birth', 'gender')
        }),
        ('Contact & Location', {
            'fields': ('phone_number', 'location', 'website', 'timezone')
        }),
        ('Profile Status', {
            'fields': ('rating', 'reputation_points', 'connection_strength', 
                      'is_verified', 'is_mentor', 'account_type', 'profile_completion')
        }),
        ('Privacy & Security', {
            'fields': ('profile_visibility', 'two_factor_enabled', 'email_verified', 
                      'online_status', 'last_active')
        }),
        ('Preferences', {
            'fields': ('language_preference', 'theme_preference')
        }),
        ('Statistics', {
            'fields': ('post_count', 'follower_count', 'following_count', 
                      'contribution_points', 'endorsement_count')
        }),
        ('Permissions', {
            'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions'),
            'classes': ('collapse',)
        }),
    )
    
    def full_name(self, obj):
        return obj.get_full_name()
    full_name.short_description = 'Full Name'

@admin.register(UserSocialProfile)
class UserSocialProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'has_linkedin', 'has_github', 'has_twitter', 'has_portfolio')
    search_fields = ('user__username', 'user__email')
    
    def has_linkedin(self, obj):
        return bool(obj.linkedin_url)
    has_linkedin.boolean = True
    
    def has_github(self, obj):
        return bool(obj.github_url)
    has_github.boolean = True
    
    def has_twitter(self, obj):
        return bool(obj.twitter_url)
    has_twitter.boolean = True
    
    def has_portfolio(self, obj):
        return bool(obj.portfolio_url)
    has_portfolio.boolean = True

@admin.register(UserAnalytics)
class UserAnalyticsAdmin(admin.ModelAdmin):
    list_display = ('user', 'profile_views', 'search_appearances', 'engagement_rate', 
                   'activity_score', 'last_profile_update')
    readonly_fields = ('last_profile_update',)
    search_fields = ('user__username', 'user__email')
    list_filter = ('last_profile_update',)

@admin.register(UserBadge)
class UserBadgeAdmin(admin.ModelAdmin):
    list_display = ('user', 'name', 'category', 'level', 'awarded_date')
    list_filter = ('category', 'level', 'awarded_date')
    search_fields = ('user__username', 'name', 'description')
    readonly_fields = ('awarded_date',)

@admin.register(UserCertification)
class UserCertificationAdmin(admin.ModelAdmin):
    list_display = ('user', 'name', 'issuing_organization', 'issue_date', 
                   'expiry_date', 'is_verified')
    list_filter = ('is_verified', 'issuing_organization', 'issue_date')
    search_fields = ('user__username', 'name', 'issuing_organization', 'credential_id')
    readonly_fields = ('is_verified',)

@admin.register(UserProject)
class UserProjectAdmin(admin.ModelAdmin):
    list_display = ('user', 'title', 'role', 'start_date', 'is_ongoing', 'team_size', 'visibility')
    list_filter = ('is_ongoing', 'visibility', 'start_date')
    search_fields = ('user__username', 'title', 'description', 'technologies')
    readonly_fields = ('technologies',)

@admin.register(UserEndorsement)
class UserEndorsementAdmin(admin.ModelAdmin):
    list_display = ('user', 'endorser', 'skill', 'created_at')
    list_filter = ('created_at', 'skill')
    search_fields = ('user__username', 'endorser__username', 'skill__name')
    readonly_fields = ('created_at',)

@admin.register(UserBlock)
class UserBlockAdmin(admin.ModelAdmin):
    list_display = ('user', 'blocked_user', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('user__username', 'blocked_user__username', 'reason')
    readonly_fields = ('created_at',)

@admin.register(PersonalityTag)
class PersonalityTagAdmin(admin.ModelAdmin):
    list_display = ('name', 'color', 'user_count')
    search_fields = ('name',)
    
    def user_count(self, obj):
        return obj.users.count()
    user_count.short_description = 'Users'

@admin.register(Skill)
class SkillAdmin(admin.ModelAdmin):
    list_display = ('name', 'user', 'level', 'endorsement_count')
    list_filter = ('level',)
    search_fields = ('name', 'user__username')
    
    def endorsement_count(self, obj):
        return obj.userendorsement_set.count()
    endorsement_count.short_description = 'Endorsements'

@admin.register(Language)
class LanguageAdmin(admin.ModelAdmin):
    list_display = ('name', 'user', 'proficiency')
    list_filter = ('proficiency',)
    search_fields = ('name', 'user__username')

@admin.register(UserAvailability)
class UserAvailabilityAdmin(admin.ModelAdmin):
    list_display = ('user', 'mentoring', 'collaboration', 'networking')
    list_filter = ('mentoring', 'collaboration', 'networking')
    search_fields = ('user__username',)

@admin.register(Education)
class EducationAdmin(admin.ModelAdmin):
    list_display = ('user', 'school', 'degree', 'field', 'year')
    search_fields = ('user__username', 'school', 'degree', 'field')
    list_filter = ('year', 'degree')

@admin.register(WorkExperience)
class WorkExperienceAdmin(admin.ModelAdmin):
    list_display = ('user', 'company', 'role', 'duration')
    search_fields = ('user__username', 'company', 'role')
    list_filter = ('company',)

@admin.register(Achievement)
class AchievementAdmin(admin.ModelAdmin):
    list_display = ('user', 'title', 'date')
    search_fields = ('user__username', 'title', 'description')
    list_filter = ('date',)

@admin.register(UserInterest)
class UserInterestAdmin(admin.ModelAdmin):
    list_display = ('user', 'name')
    search_fields = ('user__username', 'name')

@admin.register(UserFollowing)
class UserFollowingAdmin(admin.ModelAdmin):
    list_display = ('user', 'following_user', 'created_at', 'relationship_duration')
    search_fields = ('user__username', 'following_user__username')
    list_filter = ('created_at',)
    readonly_fields = ('created_at',)
    
    def relationship_duration(self, obj):
        from django.utils import timezone
        from django.utils.timesince import timesince
        return timesince(obj.created_at, timezone.now())
    relationship_duration.short_description = 'Following Duration'
