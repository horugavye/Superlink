from django.contrib import admin
from .models import Connection, ConnectionRequest, UserSuggestion

@admin.register(Connection)
class ConnectionAdmin(admin.ModelAdmin):
    list_display = ('user1', 'user2', 'connection_strength', 'created_at', 'last_interaction', 'is_active')
    list_filter = ('is_active', 'created_at', 'last_interaction')
    search_fields = ('user1__username', 'user2__username')
    raw_id_fields = ('user1', 'user2')
    date_hierarchy = 'created_at'

@admin.register(ConnectionRequest)
class ConnectionRequestAdmin(admin.ModelAdmin):
    list_display = ('sender', 'receiver', 'status', 'created_at', 'match_score', 'mutual_connections')
    list_filter = ('status', 'created_at')
    search_fields = ('sender__username', 'receiver__username')
    raw_id_fields = ('sender', 'receiver')
    date_hierarchy = 'created_at'
    readonly_fields = ('match_score', 'mutual_connections', 'common_interests', 'match_highlights')

@admin.register(UserSuggestion)
class UserSuggestionAdmin(admin.ModelAdmin):
    list_display = ('user', 'suggested_user', 'score', 'created_at', 'is_active', 'mutual_connections')
    list_filter = ('is_active', 'created_at')
    search_fields = ('user__username', 'suggested_user__username')
    raw_id_fields = ('user', 'suggested_user')
    date_hierarchy = 'created_at'
    readonly_fields = ('score', 'common_interests', 'match_highlights', 'mutual_connections')
