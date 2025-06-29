from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync, sync_to_async
import logging
import json

logger = logging.getLogger(__name__)

@sync_to_async
def get_notification_preferences(user):
    """Get user's notification preferences in a sync context"""
    try:
        from .models import NotificationPreference
        preferences, created = NotificationPreference.objects.get_or_create(user=user)
        logger.debug(f"[Broadcast] Got preferences for user {user.id}: {preferences}")
        return preferences
    except Exception as e:
        logger.error(f"[Broadcast] Error getting preferences for user {user.id}: {str(e)}")
        return type('Preferences', (), {'__getattr__': lambda self, name: True})()

@sync_to_async
def serialize_notification(notification):
    """Serialize notification in a sync context"""
    from .serializers import NotificationSerializer
    serializer = NotificationSerializer(notification)
    return serializer.data

async def broadcast_notification(notification):
    """Broadcast the notification to the recipient's WebSocket channel if enabled in preferences"""
    try:
        # Get user's notification preferences asynchronously
        preferences = await get_notification_preferences(notification.recipient)
        logger.debug(f"[Broadcast] Starting broadcast for notification {notification.id} to user {notification.recipient.id}")
        
        # Check if in-app notifications are enabled for this type
        notification_type = notification.notification_type
        preference_field = f"in_app_{notification_type}"
        
        # Log the preference check
        logger.debug(f"[Broadcast] Checking preference {preference_field} for user {notification.recipient.id}")
        
        # If the preference field exists and is False, don't send the notification
        if hasattr(preferences, preference_field):
            is_enabled = getattr(preferences, preference_field)
            logger.debug(f"[Broadcast] Preference {preference_field} is {'enabled' if is_enabled else 'disabled'}")
            if not is_enabled:
                logger.debug(f"[Broadcast] Notification {notification.id} blocked by preference {preference_field}")
                return
        else:
            logger.debug(f"[Broadcast] Preference field {preference_field} not found, defaulting to enabled")
        
        # Get channel layer and serialize notification
        channel_layer = get_channel_layer()
        serialized_data = await serialize_notification(notification)
        channel_name = f"notifications_{notification.recipient.id}"
        
        # Prepare the message with proper type and data structure
        message = {
            "type": "notification_message",
            "data": {
                **serialized_data,
                "created_at": notification.created_at.isoformat(),
                "is_read": notification.is_read
            }
        }
        
        # Log the message being sent
        logger.debug(f"[Broadcast] Sending message to channel {channel_name}: {json.dumps(message)}")
        
        # Send the message to the channel layer
        await channel_layer.group_send(
            channel_name,
            message
        )
        logger.debug(f"[Broadcast] Successfully sent notification {notification.id} to user {notification.recipient.id}")
    except Exception as e:
        logger.error(f"[Broadcast] Error broadcasting notification {notification.id}: {str(e)}", exc_info=True) 