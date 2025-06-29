from django.utils import timezone
from datetime import timedelta
from django.contrib.auth import get_user_model

User = get_user_model()

def is_user_online(user, activity_threshold_minutes=5):
    """
    Check if a user is currently online.
    
    Args:
        user: User instance
        activity_threshold_minutes: Minutes of inactivity before considering user offline
    
    Returns:
        bool: True if user is online, False otherwise
    """
    if not user.last_active:
        return False
    
    # Check if user has been active recently
    threshold_time = timezone.now() - timedelta(minutes=activity_threshold_minutes)
    recently_active = user.last_active >= threshold_time
    
    # User is online if status is 'online' and recently active
    return user.online_status == 'online' and recently_active

def get_user_online_status(user, activity_threshold_minutes=5):
    """
    Get detailed online status information for a user.
    
    Args:
        user: User instance
        activity_threshold_minutes: Minutes of inactivity before considering user offline
    
    Returns:
        dict: Dictionary with online status information
    """
    is_online = is_user_online(user, activity_threshold_minutes)
    
    return {
        'online_status': user.online_status,
        'last_active': user.last_active,
        'is_online': is_online,
        'activity_threshold_minutes': activity_threshold_minutes
    }

def update_user_online_status(user, status):
    """
    Update a user's online status.
    
    Args:
        user: User instance
        status: New status ('online', 'away', 'offline', 'busy')
    
    Returns:
        bool: True if update was successful, False otherwise
    """
    valid_statuses = ['online', 'away', 'offline', 'busy']
    
    if status not in valid_statuses:
        return False
    
    try:
        user.online_status = status
        user.last_active = timezone.now()
        user.save(update_fields=['online_status', 'last_active'])
        return True
    except Exception:
        return False

def get_online_users(queryset=None, activity_threshold_minutes=5):
    """
    Get a queryset of users who are currently online.
    
    Args:
        queryset: Optional base queryset to filter from
        activity_threshold_minutes: Minutes of inactivity before considering user offline
    
    Returns:
        QuerySet: Users who are currently online
    """
    if queryset is None:
        queryset = User.objects.all()
    
    threshold_time = timezone.now() - timedelta(minutes=activity_threshold_minutes)
    
    return queryset.filter(
        online_status='online',
        last_active__gte=threshold_time
    ) 