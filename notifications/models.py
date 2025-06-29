from django.db import models
from django.conf import settings
from django.utils import timezone
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from asgiref.sync import async_to_sync
from .utils import broadcast_notification
import logging

logger = logging.getLogger(__name__)

class Notification(models.Model):
    NOTIFICATION_TYPES = [
        ('connection_request', 'Connection Request'),
        ('connection_accepted', 'Connection Accepted'),
        ('community_invite', 'Community Invitation'),
        ('community_join', 'Community Join Request'),
        ('community_join_accepted', 'Community Join Accepted'),
        ('community_join_rejected', 'Community Join Rejected'),
        ('community_role_change', 'Community Role Change'),
        ('message', 'New Message'),
        ('achievement', 'Achievement Unlocked'),
        ('event', 'Event Update'),
        ('mention', 'Mention'),
        ('like', 'Like'),
        ('comment', 'Comment'),
    ]

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications'
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sent_notifications'
    )
    notification_type = models.CharField(max_length=50, choices=NOTIFICATION_TYPES)
    title = models.CharField(max_length=255)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Generic relation to the related object (community, connection, etc.)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, null=True, blank=True)
    object_id = models.PositiveIntegerField(null=True, blank=True)
    content_object = GenericForeignKey('content_type', 'object_id')

    # Additional data stored as JSON
    data = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['recipient', 'is_read', 'created_at']),
            models.Index(fields=['notification_type', 'created_at']),
        ]

    def __str__(self):
        return f"{self.notification_type} - {self.recipient.username}"

    def mark_as_read(self):
        self.is_read = True
        self.save(update_fields=['is_read', 'updated_at'])

    def mark_as_unread(self):
        self.is_read = False
        self.save(update_fields=['is_read', 'updated_at'])

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        super().save(*args, **kwargs)
        if is_new:  # Only broadcast new notifications
            # Use async_to_sync to call the async broadcast function from sync context
            try:
                async_to_sync(broadcast_notification)(self)
            except Exception as e:
                logger.error(f"Error broadcasting notification {self.id}: {str(e)}", exc_info=True)

class NotificationPreference(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notification_preferences'
    )
    
    # Email notifications
    email_connection_requests = models.BooleanField(default=True)
    email_community_invites = models.BooleanField(default=True)
    email_messages = models.BooleanField(default=True)
    email_achievements = models.BooleanField(default=True)
    email_events = models.BooleanField(default=True)
    
    # Push notifications
    push_connection_requests = models.BooleanField(default=True)
    push_community_invites = models.BooleanField(default=True)
    push_messages = models.BooleanField(default=True)
    push_achievements = models.BooleanField(default=True)
    push_events = models.BooleanField(default=True)
    
    # In-app notifications
    in_app_connection_requests = models.BooleanField(default=True)
    in_app_community_invites = models.BooleanField(default=True)
    in_app_messages = models.BooleanField(default=True)
    in_app_achievements = models.BooleanField(default=True)
    in_app_events = models.BooleanField(default=True)

    # New fields for community join, join accepted, join rejected, role change
    email_community_join = models.BooleanField(default=True)
    email_community_join_accepted = models.BooleanField(default=True)
    email_community_join_rejected = models.BooleanField(default=True)
    email_community_role_change = models.BooleanField(default=True)

    push_community_join = models.BooleanField(default=True)
    push_community_join_accepted = models.BooleanField(default=True)
    push_community_join_rejected = models.BooleanField(default=True)
    push_community_role_change = models.BooleanField(default=True)

    in_app_community_join = models.BooleanField(default=True)
    in_app_community_join_accepted = models.BooleanField(default=True)
    in_app_community_join_rejected = models.BooleanField(default=True)
    in_app_community_role_change = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Notification preferences for {self.user.username}"

    class Meta:
        verbose_name = "Notification Preference"
        verbose_name_plural = "Notification Preferences"
