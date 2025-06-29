from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta
from .utils import is_user_online, update_user_online_status, get_user_online_status

User = get_user_model()

class OnlineStatusTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )

    def test_user_starts_offline(self):
        """Test that new users start with offline status."""
        self.assertEqual(self.user.online_status, 'offline')
        self.assertFalse(is_user_online(self.user))

    def test_update_online_status(self):
        """Test updating user online status."""
        # Update to online
        success = update_user_online_status(self.user, 'online')
        self.assertTrue(success)
        self.user.refresh_from_db()
        self.assertEqual(self.user.online_status, 'online')
        self.assertTrue(is_user_online(self.user))

        # Update to away
        success = update_user_online_status(self.user, 'away')
        self.assertTrue(success)
        self.user.refresh_from_db()
        self.assertEqual(self.user.online_status, 'away')
        self.assertFalse(is_user_online(self.user))

    def test_invalid_status(self):
        """Test that invalid status returns False."""
        success = update_user_online_status(self.user, 'invalid_status')
        self.assertFalse(success)

    def test_activity_threshold(self):
        """Test that users are considered offline after inactivity threshold."""
        # Set user as online with recent activity
        self.user.online_status = 'online'
        self.user.last_active = timezone.now()
        self.user.save()
        self.assertTrue(is_user_online(self.user))

        # Set user as online with old activity (6 minutes ago)
        self.user.last_active = timezone.now() - timedelta(minutes=6)
        self.user.save()
        self.assertFalse(is_user_online(self.user))

    def test_get_user_online_status(self):
        """Test getting detailed online status information."""
        self.user.online_status = 'online'
        self.user.last_active = timezone.now()
        self.user.save()

        status_info = get_user_online_status(self.user)
        self.assertEqual(status_info['online_status'], 'online')
        self.assertTrue(status_info['is_online'])
        self.assertEqual(status_info['activity_threshold_minutes'], 5)
