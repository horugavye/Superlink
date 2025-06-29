from django.utils import timezone
from django.contrib.auth import get_user_model
import logging

logger = logging.getLogger(__name__)
User = get_user_model()

class UserActivityMiddleware:
    """
    Middleware to track user activity and update last_active timestamp.
    Also updates online_status to 'online' when user makes requests.
    """
    
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Process request
        response = self.get_response(request)
        
        # Update user activity if authenticated
        if hasattr(request, 'user') and request.user.is_authenticated:
            try:
                # Update last_active timestamp
                request.user.last_active = timezone.now()
                
                # Update online_status to 'online' if it's not already
                if request.user.online_status != 'online':
                    request.user.online_status = 'online'
                
                # Save only the fields we're updating
                request.user.save(update_fields=['last_active', 'online_status'])
                
                logger.debug(f"Updated activity for user {request.user.username}")
                
            except Exception as e:
                logger.error(f"Error updating user activity: {str(e)}")
        
        return response 