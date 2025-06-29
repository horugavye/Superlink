from django.contrib import admin
from .models import Notification, NotificationPreference

@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('notification_type', 'recipient', 'sender', 'is_read', 'created_at')
    list_filter = ('notification_type', 'is_read', 'created_at')
    search_fields = ('recipient__username', 'sender__username', 'title', 'message')
    readonly_fields = ('created_at', 'updated_at')
    ordering = ('-created_at',)

@admin.register(NotificationPreference)
class NotificationPreferenceAdmin(admin.ModelAdmin):
    list_display = ('user', 'created_at', 'updated_at')
    search_fields = ('user__username',)
    readonly_fields = ('created_at', 'updated_at')
    fieldsets = (
        ('User', {
            'fields': ('user',)
        }),
        ('Email Notifications', {
            'fields': (
                'email_connection_requests',
                'email_community_invites',
                'email_messages',
                'email_achievements',
                'email_events',
            )
        }),
        ('Push Notifications', {
            'fields': (
                'push_connection_requests',
                'push_community_invites',
                'push_messages',
                'push_achievements',
                'push_events',
            )
        }),
        ('In-App Notifications', {
            'fields': (
                'in_app_connection_requests',
                'in_app_community_invites',
                'in_app_messages',
                'in_app_achievements',
                'in_app_events',
            )
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
