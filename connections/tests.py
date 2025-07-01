from django.test import TestCase
from django.contrib.auth import get_user_model
from connections.models import UserSuggestion
from connections.tasks import update_all_user_suggestions

# Create your tests here.

class UserSuggestionTaskTest(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user1 = User.objects.create_user(username='user1', password='testpass', is_active=True)
        self.user2 = User.objects.create_user(username='user2', password='testpass', is_active=True)
        self.user3 = User.objects.create_user(username='user3', password='testpass', is_active=True)

    def test_update_all_user_suggestions_creates_suggestions(self):
        # Run the task synchronously
        update_all_user_suggestions()
        # Check that UserSuggestion objects exist for each user (except self-suggestions)
        suggestions = UserSuggestion.objects.all()
        self.assertTrue(suggestions.exists(), "No suggestions were created.")
        # Each user should have suggestions for the other users
        for user in [self.user1, self.user2, self.user3]:
            other_ids = [u.id for u in [self.user1, self.user2, self.user3] if u != user]
            user_suggestions = UserSuggestion.objects.filter(user=user, suggested_user_id__in=other_ids)
            self.assertTrue(user_suggestions.exists(), f"No suggestions for user {user.username}")
