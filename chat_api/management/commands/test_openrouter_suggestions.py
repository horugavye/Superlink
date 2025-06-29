from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from chat.models import Conversation
from chat_api.services import RealTimeSuggestionService
import logging

logger = logging.getLogger(__name__)
User = get_user_model()

class Command(BaseCommand):
    help = 'Test OpenRouter integration for RealTimeSuggestionService'

    def handle(self, *args, **options):
        try:
            self.stdout.write('Testing OpenRouter integration for RealTimeSuggestionService...')
            
            # Get or create test users
            user1, created = User.objects.get_or_create(
                username='test_user_1',
                defaults={
                    'email': 'test1@example.com',
                    'first_name': 'Test',
                    'last_name': 'User1'
                }
            )
            
            user2, created = User.objects.get_or_create(
                username='test_user_2',
                defaults={
                    'email': 'test2@example.com',
                    'first_name': 'Test',
                    'last_name': 'User2'
                }
            )
            
            # Create a test conversation
            conversation, created = Conversation.objects.get_or_create(
                name='Test Conversation',
                defaults={
                    'type': 'direct',
                    'created_by': user1
                }
            )
            
            # Add participants if not already added
            if user1 not in conversation.get_participants():
                conversation.participants.add(user1)
            if user2 not in conversation.get_participants():
                conversation.participants.add(user2)
            
            # Add some test messages
            from chat.models import Message
            Message.objects.get_or_create(
                conversation=conversation,
                sender=user2,
                content="Hello! How are you doing today?",
                defaults={'message_type': 'text'}
            )
            
            Message.objects.get_or_create(
                conversation=conversation,
                sender=user1,
                content="I'm doing well, thanks for asking!",
                defaults={'message_type': 'text'}
            )
            
            self.stdout.write('Test conversation created with messages')
            
            # Test suggestion generation
            self.stdout.write('Generating suggestions...')
            suggestions = RealTimeSuggestionService.generate_suggestions(
                conversation=conversation,
                user=user1,
                max_suggestions=3
            )
            
            if suggestions:
                self.stdout.write(self.style.SUCCESS(f'Successfully generated {len(suggestions)} suggestions:'))
                for i, suggestion in enumerate(suggestions, 1):
                    self.stdout.write(f'{i}. Type: {suggestion["suggestion_type"]}')
                    self.stdout.write(f'   Content: {suggestion["content"]}')
                    self.stdout.write(f'   Confidence: {suggestion["confidence_score"]}')
                    self.stdout.write('')
            else:
                self.stdout.write(self.style.WARNING('No suggestions generated'))
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error testing OpenRouter integration: {str(e)}'))
            logger.error(f"Error testing OpenRouter integration: {str(e)}", exc_info=True) 