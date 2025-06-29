from django.core.management.base import BaseCommand
from openai import OpenAI
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Test the OpenRouter API connection'

    def handle(self, *args, **options):
        try:
            self.stdout.write('Testing OpenRouter API connection...')
            
            client = OpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key="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",
            )
            
            response = client.chat.completions.create(
                model="deepseek/deepseek-r1-0528:free",
                messages=[
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": "Hello, are you working?"}
                ],
                temperature=0.7,
                top_p=1.0,
                extra_headers={
                    "HTTP-Referer": "http://localhost:8000",
                    "X-Title": "SuperLink",
                }
            )
            
            self.stdout.write(self.style.SUCCESS('OpenRouter API test successful!'))
            self.stdout.write(f'Response: {response.choices[0].message.content}')
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'OpenRouter API test failed: {str(e)}'))
            logger.error(f"OpenRouter API test failed: {str(e)}", exc_info=True) 