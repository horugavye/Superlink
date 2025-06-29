from django.shortcuts import render
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Q
from django.utils import timezone
import logging
from .models import Notification, NotificationPreference
from .serializers import NotificationSerializer, NotificationPreferenceSerializer

logger = logging.getLogger(__name__)

# Create your views here.

class NotificationViewSet(viewsets.ModelViewSet):
    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        queryset = Notification.objects.filter(recipient=self.request.user)
        logger.info(f"Fetching notifications for user {self.request.user.id}. Found {queryset.count()} notifications")
        return queryset

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        logger.info(f"Returning {len(serializer.data)} notifications for user {request.user.id}")
        logger.info(f"Notification data: {serializer.data}")
        return Response(serializer.data)

    @action(detail=False, methods=['post'])
    def create_test(self, request):
        """Create a test notification for the current user"""
        try:
            notification = Notification.objects.create(
                recipient=request.user,
                notification_type='message',
                title='Test Notification',
                message='This is a test notification to verify the system is working.',
                is_read=False
            )
            logger.info(f"Created test notification {notification.id} for user {request.user.id}")
            serializer = self.get_serializer(notification)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        except Exception as e:
            logger.error(f"Error creating test notification: {str(e)}")
            return Response(
                {'error': 'Failed to create test notification'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=['post'])
    def mark_all_read(self, request):
        self.get_queryset().update(is_read=True, updated_at=timezone.now())
        return Response({'status': 'success'})

    @action(detail=True, methods=['post'], url_path='mark-read', url_name='mark-read')
    def mark_read(self, request, pk=None):
        notification = self.get_object()
        notification.mark_as_read()
        return Response({'status': 'success'})

    @action(detail=True, methods=['post'])
    def mark_unread(self, request, pk=None):
        notification = self.get_object()
        notification.mark_as_unread()
        return Response({'status': 'success'})

    @action(detail=False, methods=['get'])
    def unread_count(self, request):
        count = self.get_queryset().filter(is_read=False).count()
        return Response({'count': count})

class NotificationPreferenceViewSet(viewsets.ModelViewSet):
    serializer_class = NotificationPreferenceSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        obj, created = NotificationPreference.objects.get_or_create(
            user=self.request.user
        )
        return obj

    def get_queryset(self):
        return NotificationPreference.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @action(detail=False, methods=['put', 'patch'], url_path='update_current')
    def update_current(self, request):
        obj = self.get_object()
        partial = request.method == 'PATCH'
        serializer = self.get_serializer(obj, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)
