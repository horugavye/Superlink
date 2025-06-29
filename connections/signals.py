from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.contrib.contenttypes.models import ContentType
from .models import Connection, ConnectionRequest
from notifications.models import Notification

@receiver(post_save, sender=ConnectionRequest)
def handle_connection_request_notifications(sender, instance, created, **kwargs):
    """Create notifications for connection request actions"""
    if created:
        # When a connection request is sent
        Notification.objects.create(
            recipient=instance.receiver,
            sender=instance.sender,
            notification_type='connection_request',
            title='New Connection Request',
            message=f'{instance.sender.get_full_name()} sent you a connection request',
            content_type=ContentType.objects.get_for_model(instance),
            object_id=instance.id,
            data={
                'request_id': instance.id,
                'match_score': instance.match_score,
                'connection_strength': instance.connection_strength,
                'mutual_connections': instance.mutual_connections,
                'common_interests': instance.common_interests
            }
        )
    elif instance.status == 'accepted':
        # When a connection request is accepted
        Notification.objects.create(
            recipient=instance.sender,
            sender=instance.receiver,
            notification_type='connection_accepted',
            title='Connection Request Accepted',
            message=f'{instance.receiver.get_full_name()} accepted your connection request',
            content_type=ContentType.objects.get_for_model(instance),
            object_id=instance.id,
            data={
                'request_id': instance.id,
                'connection_id': instance.connection.id if hasattr(instance, 'connection') else None
            }
        )
    elif instance.status == 'rejected':
        # When a connection request is rejected
        Notification.objects.create(
            recipient=instance.sender,
            sender=instance.receiver,
            notification_type='connection_rejected',
            title='Connection Request Rejected',
            message=f'{instance.receiver.get_full_name()} rejected your connection request',
            content_type=ContentType.objects.get_for_model(instance),
            object_id=instance.id,
            data={
                'request_id': instance.id
            }
        )

@receiver(post_save, sender=Connection)
def handle_connection_notifications(sender, instance, created, **kwargs):
    """Create notifications for connection actions"""
    if created:
        # Notify both users about the new connection
        for user in [instance.user1, instance.user2]:
            other_user = instance.user2 if user == instance.user1 else instance.user1
            Notification.objects.create(
                recipient=user,
                sender=other_user,
                notification_type='connection_created',
                title='New Connection',
                message=f'You are now connected with {other_user.get_full_name()}',
                content_type=ContentType.objects.get_for_model(instance),
                object_id=instance.id,
                data={
                    'connection_id': instance.id,
                    'match_score': instance.match_score,
                    'connection_strength': instance.connection_strength,
                    'mutual_connections': instance.mutual_connections_count,
                    'common_interests': instance.common_interests
                }
            ) 