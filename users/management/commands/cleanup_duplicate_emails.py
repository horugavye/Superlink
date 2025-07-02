from django.core.management.base import BaseCommand
from users.models import User
from django.db import models, transaction

class Command(BaseCommand):
    help = 'Remove duplicate users with the same email, keeping the user with the lowest ID.'

    def handle(self, *args, **options):
        duplicates = (
            User.objects.values('email')
            .annotate(email_count=models.Count('id'))
            .filter(email_count__gt=1)
        )
        if not duplicates:
            self.stdout.write(self.style.SUCCESS('No duplicate emails found.'))
            return

        for entry in duplicates:
            email = entry['email']
            users = User.objects.filter(email=email).order_by('id')
            keep = users.first()
            to_delete = users.exclude(id=keep.id)
            self.stdout.write(f"Email '{email}' has {users.count()} users. Keeping ID {keep.id}, deleting {[u.id for u in to_delete]}")
            with transaction.atomic():
                to_delete.delete()

        self.stdout.write(self.style.SUCCESS('Duplicate emails cleaned up.'))
