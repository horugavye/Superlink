from celery import shared_task
from django.contrib.auth import get_user_model
from .services import generate_user_suggestions
import logging
import time

logger = logging.getLogger(__name__)

@shared_task
def update_all_user_suggestions(batch_size=2, delay_seconds=30):
    User = get_user_model()
    users = list(User.objects.filter(is_active=True))
    for i in range(0, len(users), batch_size):
        batch = users[i:i+batch_size]
        for user in batch:
            try:
                generate_user_suggestions(user)
                logger.info(f"Updated suggestions for user {user.username} (ID: {user.id})")
            except Exception as e:
                logger.error(f"Failed to update suggestions for user {user.id}: {str(e)}")
        if i + batch_size < len(users):
            logger.info(f"Sleeping {delay_seconds} seconds before next batch...")
            time.sleep(delay_seconds)
