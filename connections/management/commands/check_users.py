from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from connections.models import Connection, ConnectionRequest, UserSuggestion

User = get_user_model()

class Command(BaseCommand):
    help = 'Check users and their connections in the database'

    def handle(self, *args, **kwargs):
        # Check total users
        total_users = User.objects.count()
        self.stdout.write(f'Total users in system: {total_users}')
        
        # List all users
        self.stdout.write('\nAll users:')
        for user in User.objects.all():
            self.stdout.write(f'- {user.username} (ID: {user.id})')
        
        # Check connections
        total_connections = Connection.objects.count()
        self.stdout.write(f'\nTotal connections: {total_connections}')
        
        # Check connection requests
        total_requests = ConnectionRequest.objects.count()
        self.stdout.write(f'Total connection requests: {total_requests}')
        
        # Check suggestions
        total_suggestions = UserSuggestion.objects.count()
        self.stdout.write(f'Total suggestions: {total_suggestions}')
        
        # Check active suggestions
        active_suggestions = UserSuggestion.objects.filter(is_active=True).count()
        self.stdout.write(f'Active suggestions: {active_suggestions}') 