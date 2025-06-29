from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils import timezone
from .models import (
    Group,
    Conversation,
    ConversationMember,
    Message,
    MessageReaction,
    MessageThread,
    MessageEffect,
    LinkPreview,
    File,
)

@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    list_display = ('name', 'created_by', 'is_private', 'max_members', 'created_at', 'member_count', 'status', 'view_members')
    list_filter = ('is_private', 'created_at')
    search_fields = ('name', 'description', 'created_by__username')
    readonly_fields = ('created_at', 'updated_at', 'member_count')
    actions = ['make_private', 'make_public', 'archive_groups']
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'description', 'avatar', 'created_by')
        }),
        ('Settings', {
            'fields': ('is_private', 'max_members', 'rules', 'settings')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def member_count(self, obj):
        return obj.members.count()
    member_count.short_description = 'Members'

    def status(self, obj):
        return "Private" if obj.is_private else "Public"
    status.short_description = 'Status'

    def view_members(self, obj):
        members = obj.members.all()
        return format_html('<br>'.join([f'{member.username}' for member in members]))
    view_members.short_description = 'Members'

    def make_private(self, request, queryset):
        queryset.update(is_private=True)
    make_private.short_description = "Make selected groups private"

    def make_public(self, request, queryset):
        queryset.update(is_private=False)
    make_public.short_description = "Make selected groups public"

    def archive_groups(self, request, queryset):
        queryset.update(is_active=False)
    archive_groups.short_description = "Archive selected groups"

@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ('type', 'name', 'participant1', 'participant2', 'group', 'is_active', 'created_at', 'updated_at', 'message_count', 'view_messages')
    list_filter = ('type', 'is_active', 'created_at')
    search_fields = ('name', 'group__name', 'participant1__username', 'participant2__username')
    readonly_fields = ('created_at', 'updated_at', 'message_count')
    actions = ['archive_conversations', 'activate_conversations']
    fieldsets = (
        ('Basic Information', {
            'fields': ('type', 'name', 'group', 'participant1', 'participant2', 'is_active')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def message_count(self, obj):
        return obj.messages.count()
    message_count.short_description = 'Messages'

    def view_messages(self, obj):
        messages = obj.messages.all()[:5]
        return format_html('<br>'.join([f'{msg.sender.username}: {msg.content[:50]}...' for msg in messages]))
    view_messages.short_description = 'Recent Messages'

    def archive_conversations(self, request, queryset):
        queryset.update(is_active=False)
    archive_conversations.short_description = "Archive selected conversations"

    def activate_conversations(self, request, queryset):
        queryset.update(is_active=True)
    activate_conversations.short_description = "Activate selected conversations"

@admin.register(ConversationMember)
class ConversationMemberAdmin(admin.ModelAdmin):
    list_display = ('user', 'conversation', 'role', 'joined_at', 'last_read', 'is_muted', 'is_pinned')
    list_filter = ('role', 'is_muted', 'is_pinned', 'joined_at')
    search_fields = ('user__username', 'conversation__name', 'conversation__group__name')
    readonly_fields = ('joined_at',)
    fieldsets = (
        ('Member Information', {
            'fields': ('user', 'conversation', 'role')
        }),
        ('Settings', {
            'fields': ('is_muted', 'is_pinned', 'unread_count')
        }),
        ('Timestamps', {
            'fields': ('joined_at', 'last_read'),
            'classes': ('collapse',)
        }),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user', 'conversation', 'conversation__group')

@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ('id', 'sender', 'conversation', 'content_preview', 'file_preview', 'is_thread_reply', 'thread_info', 'created_at', 'status')
    list_filter = ('status', 'created_at', 'conversation', 'message_type', 'is_thread_reply')
    search_fields = ('content', 'sender__username', 'conversation__name', 'thread__parent_message__content')
    readonly_fields = ('id', 'created_at', 'updated_at', 'file_preview', 'thread_info')
    fieldsets = (
        ('Message Information', {
            'fields': ('id', 'conversation', 'sender', 'content', 'message_type', 'status')
        }),
        ('Files & Attachments', {
            'fields': ('files', 'file_preview'),
            'classes': ('collapse',)
        }),
        ('Thread Information', {
            'fields': ('reply_to', 'thread', 'is_thread_reply', 'thread_info'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def content_preview(self, obj):
        return obj.content[:100] + '...' if obj.content and len(obj.content) > 100 else obj.content
    content_preview.short_description = 'Content'

    def file_preview(self, obj):
        files = obj.files.all()
        if files:
            return format_html('<br>'.join([f'{f.file_name} ({f.file_type})' for f in files]))
        return '-'
    file_preview.short_description = 'Files'

    def thread_info(self, obj):
        if obj.thread:
            return f"Thread #{obj.thread.id} - {obj.thread.messages.count()} replies"
        elif obj.reply_to:
            return f"Reply to message #{obj.reply_to.id}"
        return '-'
    thread_info.short_description = 'Thread Info'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'sender', 'conversation', 'reply_to', 'thread'
        ).prefetch_related('files')

@admin.register(MessageReaction)
class MessageReactionAdmin(admin.ModelAdmin):
    list_display = ('user', 'message', 'emoji', 'created_at')
    list_filter = ('emoji', 'created_at')
    search_fields = ('user__username', 'message__content')

@admin.register(MessageThread)
class MessageThreadAdmin(admin.ModelAdmin):
    list_display = ('id', 'parent_message_preview', 'participants_count', 'replies_count', 'last_reply_at', 'created_at', 'created_by')
    list_filter = ('created_at', 'last_reply_at')
    search_fields = ('parent_message__content', 'participants__username', 'created_by__username')
    readonly_fields = ('id', 'created_at', 'last_reply_at', 'participants_list', 'replies_list')
    fieldsets = (
        ('Thread Information', {
            'fields': ('id', 'parent_message', 'created_by', 'created_at', 'last_reply_at')
        }),
        ('Participants', {
            'fields': ('participants', 'participants_list')
        }),
        ('Messages', {
            'fields': ('replies_list',)
        }),
    )

    def parent_message_preview(self, obj):
        if obj.parent_message:
            content = obj.parent_message.content[:50] + '...' if obj.parent_message.content and len(obj.parent_message.content) > 50 else obj.parent_message.content
            return f"Thread #{obj.id} - {content}"
        return f"Thread #{obj.id}"
    parent_message_preview.short_description = 'Thread'

    def participants_count(self, obj):
        return obj.participants.count()
    participants_count.short_description = 'Participants'

    def replies_count(self, obj):
        return obj.messages.count()
    replies_count.short_description = 'Replies'

    def participants_list(self, obj):
        return ", ".join([p.username for p in obj.participants.all()])
    participants_list.short_description = 'Participants List'

    def replies_list(self, obj):
        messages = obj.messages.all().order_by('created_at')
        return format_html(
            '<br>'.join([
                f'<strong>{m.sender.username}</strong> ({m.created_at}): {m.content[:100]}...' 
                if len(m.content) > 100 else f'<strong>{m.sender.username}</strong> ({m.created_at}): {m.content}'
                for m in messages
            ])
        )
    replies_list.short_description = 'Replies'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'parent_message', 'parent_message__sender', 'created_by'
        ).prefetch_related(
            'participants', 'messages', 'messages__sender'
        )

@admin.register(MessageEffect)
class MessageEffectAdmin(admin.ModelAdmin):
    list_display = ('message', 'effect_type', 'intensity', 'created_at')
    list_filter = ('effect_type', 'created_at')
    search_fields = ('message__content',)

@admin.register(LinkPreview)
class LinkPreviewAdmin(admin.ModelAdmin):
    list_display = ('message', 'url', 'title', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('url', 'title', 'description')

@admin.register(File)
class FileAdmin(admin.ModelAdmin):
    list_display = ('id', 'file_name', 'file_type', 'file_size', 'category', 'uploaded_by', 'created_at', 'file_url')
    list_filter = ('category', 'file_type', 'created_at')
    search_fields = ('file_name', 'uploaded_by__username')
    readonly_fields = ('id', 'created_at', 'file_size', 'file_url')
    fieldsets = (
        ('File Information', {
            'fields': ('id', 'file', 'file_name', 'file_type', 'file_size', 'category', 'file_url')
        }),
        ('Media Details', {
            'fields': ('thumbnail', 'duration'),
            'classes': ('collapse',)
        }),
        ('Upload Information', {
            'fields': ('uploaded_by', 'created_at')
        }),
    )

    def file_url(self, obj):
        if obj.file:
            return format_html('<a href="{}" target="_blank">{}</a>', obj.get_url(), obj.get_url())
        return '-'
    file_url.short_description = 'File URL'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('uploaded_by')
