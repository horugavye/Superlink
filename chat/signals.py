from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.utils import timezone
from django.db import models
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from .models import Message, ConversationMember
import logging

logger = logging.getLogger(__name__)

@receiver(post_save, sender=Message)
def handle_message_save(sender, instance, created, **kwargs):
    """
    Signal handler for when a message is created or updated.
    Updates unread counts and broadcasts changes via WebSocket.
    """
    try:
        logger.info(f"[Message Save Signal] Message {instance.id} saved by {instance.sender.username} in conversation {instance.conversation.id}")
        
        if created:
            # Get all conversation members except the sender
            members = ConversationMember.objects.filter(
                conversation=instance.conversation
            ).exclude(user=instance.sender)

            # Update unread count for each member
            for member in members:
                logger.info(f"[Message Save Signal] Updating unread count for member {member.user.username}")
                member.unread_count = models.F('unread_count') + 1
                member.save()
                member.refresh_from_db()
                logger.info(f"[Message Save Signal] Updated unread count for {member.user.username} to {member.unread_count}")

                # Send unread count update to the member's global chat WebSocket
                channel_layer = get_channel_layer()
                async_to_sync(channel_layer.group_send)(
                    f'user_{member.user.id}_global',
                    {
                        'type': 'unread_count_update',
                        'unread_count': member.unread_count
                    }
                )
                logger.info(f"[Message Save Signal] Sent unread count update to {member.user.username}")

            # Update conversation's last message
            instance.conversation.last_message = instance
            instance.conversation.save()
            logger.info(f"[Message Save Signal] Updated conversation's last message")

    except Exception as e:
        logger.error(f"[Message Save Signal] Error handling message save: {str(e)}", exc_info=True)

@receiver(post_save, sender=ConversationMember)
def handle_conversation_member_update(sender, instance, **kwargs):
    """
    Signal handler for when a conversation member's unread count is updated.
    Broadcasts the updated unread count via WebSocket.
    """
    try:
        logger.info(f"=== Conversation Member Update Signal Triggered ===")
        logger.info(f"Member ID: {instance.id}")
        logger.info(f"User: {instance.user.username} (ID: {instance.user.id})")
        logger.info(f"Conversation: {instance.conversation.id}")
        logger.info(f"Unread count: {instance.unread_count}")
        
        channel_layer = get_channel_layer()
        
        # Send update to chat group
        async_to_sync(channel_layer.group_send)(
            f"chat_{instance.conversation.id}",
            {
                "type": "unread_count_update",
                "user_id": str(instance.user.id),
                "conversation_id": str(instance.conversation.id),
                "unread_count": instance.unread_count
            }
        )
        logger.info(f"Sent unread count update to chat group for user {instance.user.username}")
        
        # Also send update to global chat consumer
        async_to_sync(channel_layer.group_send)(
            f"user_{instance.user.id}_global",
            {
                "type": "unread_count_update",
                "unread_count": instance.unread_count
            }
        )
        logger.info(f"Sent unread count update to global chat for user {instance.user.username}")
    except Exception as e:
        logger.error(f"Error in handle_conversation_member_update signal: {str(e)}", exc_info=True)

@receiver(post_delete, sender=Message)
def handle_message_delete(sender, instance, **kwargs):
    """
    Signal handler for when a message is deleted.
    Updates the conversation's last_message if needed.
    """
    try:
        logger.info(f"=== Message Delete Signal Triggered ===")
        logger.info(f"Message ID: {instance.id}")
        logger.info(f"Conversation: {instance.conversation.id}")
        
        # Update conversation's last_message if the deleted message was the last one
        if instance.conversation.last_message_id == instance.id:
            logger.info("Deleted message was the last message, updating conversation's last message")
            last_message = Message.objects.filter(
                conversation=instance.conversation
            ).order_by('-created_at').first()
            
            instance.conversation.last_message = last_message
            instance.conversation.save()
            logger.info(f"Updated conversation's last message to: {last_message.id if last_message else 'None'}")
            
    except Exception as e:
        logger.error(f"Error in handle_message_delete signal: {str(e)}", exc_info=True) 