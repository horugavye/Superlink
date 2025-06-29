from django.core.management.base import BaseCommand
from connections.models import Connection
from connections_api.views import ConnectionViewSet
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Updates match scores for all existing connections'

    def handle(self, *args, **options):
        self.stdout.write('Starting to update connection match scores...')
        
        # Get all active connections
        connections = Connection.objects.filter(is_active=True)
        total = connections.count()
        updated = 0
        failed = 0
        
        # Create an instance of ConnectionViewSet to use its update_connection_match_score method
        viewset = ConnectionViewSet()
        
        for connection in connections:
            try:
                # Update the match score
                viewset.update_connection_match_score(connection)
                updated += 1
                
                # Log progress
                if updated % 10 == 0:
                    self.stdout.write(f'Processed {updated}/{total} connections...')
                    
            except Exception as e:
                logger.error(f"Error updating connection {connection.id}: {str(e)}", exc_info=True)
                failed += 1
                continue
        
        self.stdout.write(self.style.SUCCESS(
            f'Successfully updated {updated} connections. Failed: {failed}. Total: {total}'
        )) 