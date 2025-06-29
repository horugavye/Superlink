from rest_framework import serializers
from django.contrib.contenttypes.models import ContentType
from .models import Notification, NotificationPreference

class NotificationSerializer(serializers.ModelSerializer):
    sender_name = serializers.SerializerMethodField()
    time_ago = serializers.SerializerMethodField()
    content_type_name = serializers.SerializerMethodField()

    class Meta:
        model = Notification
        fields = [
            'id', 'notification_type', 'title', 'message', 'is_read',
            'created_at', 'sender_name', 'time_ago', 'content_type_name',
            'data'
        ]
        read_only_fields = ['id', 'created_at', 'sender_name', 'time_ago']

    def to_representation(self, instance):
        data = super().to_representation(instance)
        # Convert id to string
        data['id'] = str(data['id'])
        return data

    def get_sender_name(self, obj):
        return obj.sender.get_full_name() if obj.sender else None

    def get_time_ago(self, obj):
        from django.utils import timezone
        from datetime import timedelta

        now = timezone.now()
        diff = now - obj.created_at

        if diff < timedelta(minutes=1):
            return 'just now'
        elif diff < timedelta(hours=1):
            minutes = diff.seconds // 60
            return f'{minutes}m ago'
        elif diff < timedelta(days=1):
            hours = diff.seconds // 3600
            return f'{hours}h ago'
        elif diff < timedelta(days=7):
            days = diff.days
            return f'{days}d ago'
        else:
            return obj.created_at.strftime('%b %d, %Y')

    def get_content_type_name(self, obj):
        if obj.content_type:
            return obj.content_type.model
        return None

class NotificationPreferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationPreference
        fields = [
            'email_connection_requests', 'email_community_invites',
            'email_messages', 'email_achievements', 'email_events',
            'push_connection_requests', 'push_community_invites',
            'push_messages', 'push_achievements', 'push_events',
            'in_app_connection_requests', 'in_app_community_invites',
            'in_app_messages', 'in_app_achievements', 'in_app_events',
            'email_community_join', 'email_community_join_accepted', 'email_community_join_rejected', 'email_community_role_change',
            'push_community_join', 'push_community_join_accepted', 'push_community_join_rejected', 'push_community_role_change',
            'in_app_community_join', 'in_app_community_join_accepted', 'in_app_community_join_rejected', 'in_app_community_role_change',
        ] 