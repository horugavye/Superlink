from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.contrib.contenttypes.models import ContentType
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from .models import Community, CommunityMember, Event, EventParticipant
from notifications.models import Notification

@receiver(post_save, sender=CommunityMember)
def handle_community_member_notifications(sender, instance, created, **kwargs):
    """Create notifications for community member actions and send WebSocket updates"""
    channel_layer = get_channel_layer()
    community_slug = instance.community.slug

    if created:
        # When a user joins a community
        if instance.role == 'member':
            # Create notification
            Notification.objects.create(
                recipient=instance.user,
                sender=instance.community.created_by,
                notification_type='community_join',
                title=f'Welcome to {instance.community.name}',
                message=f'You have successfully joined {instance.community.name}',
                content_type=ContentType.objects.get_for_model(instance.community),
                object_id=instance.community.id,
                data={
                    'community_type': 'private' if instance.community.is_private else 'public',
                    'community_id': instance.community.id,
                    'community_name': instance.community.name
                }
            )

            # Send WebSocket update
            async_to_sync(channel_layer.group_send)(
                f"community_{community_slug}",
                {
                    'type': 'member_update',
                    'data': {
                        'action': 'join',
                        'member': {
                            'id': instance.id,
                            'user_id': instance.user.id,
                            'username': instance.user.username,
                            'role': instance.role,
                            'joined_at': instance.joined_at.isoformat()
                        }
                    }
                }
            )
    elif instance.role in ['admin', 'moderator']:
        # When a user's role changes
        # Create notification
        Notification.objects.create(
            recipient=instance.user,
            sender=instance.community.created_by,
            notification_type='community_role_change',
            title=f'Role Update in {instance.community.name}',
            message=f'Your role in {instance.community.name} has been updated to {instance.role}',
            content_type=ContentType.objects.get_for_model(instance.community),
            object_id=instance.community.id,
            data={
                'community_type': 'private' if instance.community.is_private else 'public',
                'community_id': instance.community.id,
                'community_name': instance.community.name,
                'new_role': instance.role
            }
        )

        # Send WebSocket update
        async_to_sync(channel_layer.group_send)(
            f"community_{community_slug}",
            {
                'type': 'member_update',
                'data': {
                    'action': 'role_change',
                    'member': {
                        'id': instance.id,
                        'user_id': instance.user.id,
                        'username': instance.user.username,
                        'role': instance.role
                    }
                }
            }
        )

@receiver(post_save, sender=Event)
def handle_event_notifications(sender, instance, created, **kwargs):
    """Create notifications for community events and send WebSocket updates"""
    channel_layer = get_channel_layer()
    community_slug = instance.community.slug

    if created:
        # Notify all community members about a new event
        for member in instance.community.members.all():
            Notification.objects.create(
                recipient=member.user,
                sender=instance.created_by,
                notification_type='event',
                title=f'New Event in {instance.community.name}',
                message=f'{instance.title} - {instance.description[:100]}...',
                content_type=ContentType.objects.get_for_model(instance),
                object_id=instance.id,
                data={
                    'event_type': instance.event_type,
                    'start_date': instance.start_date.isoformat(),
                    'community_name': instance.community.name
                }
            )

        # Send WebSocket update
        async_to_sync(channel_layer.group_send)(
            f"community_{community_slug}",
            {
                'type': 'event_update',
                'data': {
                    'action': 'create',
                    'event': {
                        'id': instance.id,
                        'title': instance.title,
                        'event_type': instance.event_type,
                        'start_date': instance.start_date.isoformat(),
                        'end_date': instance.end_date.isoformat(),
                        'status': instance.status,
                        'created_by': instance.created_by.username
                    }
                }
            }
        )

@receiver(post_save, sender=EventParticipant)
def handle_event_participant_notifications(sender, instance, created, **kwargs):
    """Create notifications for event participation and send WebSocket updates"""
    channel_layer = get_channel_layer()
    community_slug = instance.event.community.slug

    if created:
        # Notify event creator when someone joins
        Notification.objects.create(
            recipient=instance.event.created_by,
            sender=instance.user,
            notification_type='event',
            title=f'New Participant in {instance.event.title}',
            message=f'{instance.user.get_full_name()} has joined your event',
            content_type=ContentType.objects.get_for_model(instance.event),
            object_id=instance.event.id,
            data={
                'event_type': instance.event.event_type,
                'community_name': instance.event.community.name
            }
        )

        # Send WebSocket update
        async_to_sync(channel_layer.group_send)(
            f"community_{community_slug}",
            {
                'type': 'event_update',
                'data': {
                    'action': 'participant_join',
                    'event_id': instance.event.id,
                    'participant': {
                        'id': instance.id,
                        'user_id': instance.user.id,
                        'username': instance.user.username,
                        'joined_at': instance.joined_at.isoformat()
                    }
                }
            }
        ) 