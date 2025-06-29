from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model

@receiver(post_save, sender=get_user_model())
def create_initial_suggestions(sender, instance, created, **kwargs):
    if created:
        from connections.services import generate_user_suggestions
        generate_user_suggestions(instance) 