from django.core.management.base import BaseCommand
from django.utils import timezone
from django.contrib.auth import get_user_model
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)
User = get_user_model()

class Command(BaseCommand):
    help = 'Clean up stale online statuses for users who haven\'t been active'

    def add_arguments(self, parser):
        parser.add_argument(
            '--minutes',
            type=int,
            default=10,
            help='Number of minutes of inactivity before marking user as offline (default: 10)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be updated without making changes'
        )

    def handle(self, *args, **options):
        minutes = options['minutes']
        dry_run = options['dry_run']
        
        # Calculate the cutoff time
        cutoff_time = timezone.now() - timedelta(minutes=minutes)
        
        # Find users who are marked as online but haven't been active recently
        stale_users = User.objects.filter(
            online_status='online',
            last_active__lt=cutoff_time
        )
        
        count = stale_users.count()
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f'DRY RUN: Would mark {count} users as offline (inactive for {minutes} minutes)'
                )
            )
            for user in stale_users:
                self.stdout.write(f'  - {user.username} (last active: {user.last_active})')
        else:
            # Update the online status to offline
            updated_count = stale_users.update(
                online_status='offline',
                last_active=timezone.now()
            )
            
            self.stdout.write(
                self.style.SUCCESS(
                    f'Successfully marked {updated_count} users as offline'
                )
            )
            
            logger.info(f'Cleaned up online status for {updated_count} users') 