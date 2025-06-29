from celery import shared_task
from django.contrib.auth import get_user_model
from .services import generate_user_suggestions

@shared_task
def refresh_all_suggestions():
    User = get_user_model()
    for user in User.objects.filter(is_active=True):
        generate_user_suggestions(user)
