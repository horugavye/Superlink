from django.core.management.base import BaseCommand
from django.conf import settings
import os
import logging
from openai import OpenAI

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Test OpenRouter API connection'

    def handle(self, *args, **options):
        # Get API key from environment variable or settings
        api_key = os.getenv('OPENROUTER_API_KEY', getattr(settings, 'OPENROUTER_API_KEY', None))
        site_url = os.getenv('SITE_URL', getattr(settings, 'SITE_URL', 'https://deeplink.app'))
        site_name = os.getenv('SITE_NAME', getattr(settings, 'SITE_NAME', 'Deeplink'))
        
        self.stdout.write(f"API Key found: {'Yes' if api_key else 'No'}")
        self.stdout.write(f"Site URL: {site_url}")
        self.stdout.write(f"Site Name: {site_name}")
        
        if not api_key:
            self.stdout.write(self.style.ERROR('OpenRouter API key not found. Please set OPENROUTER_API_KEY environment variable or in settings.'))
            return
        
        try:
            # Initialize OpenRouter client
            self.stdout.write('Initializing OpenRouter client...')
            client = OpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key=api_key,
            )
            
            # Test prompt
            test_prompt = "What is the capital of France?"
            
            self.stdout.write(self.style.SUCCESS('Making test request to OpenRouter API...'))
            
            # Make API request
            response = client.chat.completions.create(
                extra_headers={
                    "HTTP-Referer": site_url,
                    "X-Title": site_name,
                },
                model="deepseek/deepseek-chat-v3-0324:free",
                messages=[
                    {
                        "role": "system",
                        "content": "You are a helpful assistant."
                    },
                    {
                        "role": "user",
                        "content": test_prompt
                    }
                ]
            )
            
            # Print response
            self.stdout.write(self.style.SUCCESS('API Response:'))
            self.stdout.write(response.choices[0].message.content)
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error testing OpenRouter API: {str(e)}'))
            self.stdout.write(self.style.ERROR('Full error details:'))
            import traceback
            self.stdout.write(traceback.format_exc()) 