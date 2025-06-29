from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from connections.models import UserSuggestion

class Command(BaseCommand):
    help = "List alchemy (AI) suggested friends for a user"

    def add_arguments(self, parser):
        parser.add_argument('--username', type=str, help='Username of the user')

    def handle(self, *args, **options):
        username = options['username']
        User = get_user_model()
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"User '{username}' does not exist."))
            return

        alchemy_suggestions = UserSuggestion.objects.filter(
            user=user,
            is_active=True
        ).exclude(match_highlights=[])

        if not alchemy_suggestions:
            self.stdout.write(self.style.WARNING(f"No alchemy friends found for {user.username}."))
            return

        self.stdout.write(self.style.SUCCESS(f"Alchemy friends for {user.username}:"))
        for suggestion in alchemy_suggestions:
            self.stdout.write(
                f"- {suggestion.suggested_user.username} (score: {suggestion.score})\n  Explanation: {suggestion.match_highlights[0] if suggestion.match_highlights else ''}\n"
            ) 