from django.shortcuts import render
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from .models import (
    AssistantMemory, AssistantNotification, InterestAlchemy,
    CuriosityCollision, MicroCommunity, PostSuggestion,
    CommunitySuggestion, ConnectionSuggestion, ContentRecommendation,
    SkillRecommendation
)
from .serializers import (
    AssistantMemorySerializer, AssistantNotificationSerializer,
    InterestAlchemySerializer, CuriosityCollisionSerializer,
    MicroCommunitySerializer, PostSuggestionSerializer,
    CommunitySuggestionSerializer, ConnectionSuggestionSerializer,
    ContentRecommendationSerializer, SkillRecommendationSerializer
)

# Create your views here.

class AssistantMemoryViewSet(viewsets.ModelViewSet):
    serializer_class = AssistantMemorySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return AssistantMemory.objects.filter(user=self.request.user)

    def get_object(self):
        return get_object_or_404(AssistantMemory, user=self.request.user)

    @action(detail=True, methods=['post'])
    def update_personality(self, request, pk=None):
        memory = self.get_object()
        personality_profile = request.data.get('personality_profile')
        
        if not personality_profile:
            return Response(
                {'error': 'personality_profile is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
            
        memory.personality_profile = personality_profile
        memory.save(update_fields=['personality_profile'])
        return Response(self.get_serializer(memory).data)

    @action(detail=True, methods=['post'])
    def update_context_window(self, request, pk=None):
        memory = self.get_object()
        message = request.data.get('message')
        max_size = request.data.get('max_size', 10)
        
        if not message:
            return Response(
                {'error': 'Message is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
            
        memory.update_context_window(message, max_size)
        return Response(self.get_serializer(memory).data)

    @action(detail=True, methods=['post'])
    def update_community_engagement(self, request, pk=None):
        memory = self.get_object()
        community_id = request.data.get('community_id')
        engagement_type = request.data.get('engagement_type')
        value = request.data.get('value', 1)
        
        if not all([community_id, engagement_type]):
            return Response(
                {'error': 'community_id and engagement_type are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
            
        memory.update_community_engagement(community_id, engagement_type, value)
        return Response(self.get_serializer(memory).data)

    @action(detail=True, methods=['post'])
    def update_content_preferences(self, request, pk=None):
        memory = self.get_object()
        content_type = request.data.get('content_type')
        topic = request.data.get('topic')
        value = request.data.get('value', 1)
        
        if not all([content_type, topic]):
            return Response(
                {'error': 'content_type and topic are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
            
        memory.update_content_preferences(content_type, topic, value)
        return Response(self.get_serializer(memory).data)

    @action(detail=True, methods=['post'])
    def update_notification_preferences(self, request, pk=None):
        memory = self.get_object()
        preferences = request.data.get('preferences', {})
        
        if not preferences:
            return Response(
                {'error': 'preferences are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
            
        memory.update_notification_preferences(preferences)
        return Response(self.get_serializer(memory).data)

class AssistantNotificationViewSet(viewsets.ModelViewSet):
    serializer_class = AssistantNotificationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return AssistantNotification.objects.filter(user=self.request.user)

    @action(detail=True, methods=['post'])
    def mark_as_read(self, request, pk=None):
        notification = self.get_object()
        notification.mark_as_read()
        return Response(self.get_serializer(notification).data)

    @action(detail=True, methods=['post'])
    def record_feedback(self, request, pk=None):
        notification = self.get_object()
        feedback_type = request.data.get('feedback_type')
        feedback_data = request.data.get('feedback_data')
        
        if not all([feedback_type, feedback_data]):
            return Response(
                {'error': 'feedback_type and feedback_data are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
            
        notification.record_feedback(feedback_type, feedback_data)
        return Response(self.get_serializer(notification).data)

class InterestAlchemyViewSet(viewsets.ModelViewSet):
    serializer_class = InterestAlchemySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return InterestAlchemy.objects.filter(
            models.Q(interest1__user=self.request.user) |
            models.Q(interest2__user=self.request.user)
        )

class CuriosityCollisionViewSet(viewsets.ModelViewSet):
    serializer_class = CuriosityCollisionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return CuriosityCollision.objects.filter(user=self.request.user)

class MicroCommunityViewSet(viewsets.ModelViewSet):
    serializer_class = MicroCommunitySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return MicroCommunity.objects.filter(
            models.Q(interest_alchemy__interest1__user=self.request.user) |
            models.Q(interest_alchemy__interest2__user=self.request.user)
        )

class PostSuggestionViewSet(viewsets.ModelViewSet):
    serializer_class = PostSuggestionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return PostSuggestion.objects.filter(user=self.request.user)

class CommunitySuggestionViewSet(viewsets.ModelViewSet):
    serializer_class = CommunitySuggestionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return CommunitySuggestion.objects.filter(user=self.request.user)

class ConnectionSuggestionViewSet(viewsets.ModelViewSet):
    serializer_class = ConnectionSuggestionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return ConnectionSuggestion.objects.filter(user=self.request.user)

    @action(detail=True, methods=['post'])
    def create_connection_request(self, request, pk=None):
        suggestion = self.get_object()
        message = request.data.get('message', '')
        
        request = suggestion.create_connection_request(message)
        if request:
            return Response({'status': 'Connection request created'})
        return Response(
            {'error': 'Could not create connection request'},
            status=status.HTTP_400_BAD_REQUEST
        )

class ContentRecommendationViewSet(viewsets.ModelViewSet):
    serializer_class = ContentRecommendationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return ContentRecommendation.objects.filter(user=self.request.user)

class SkillRecommendationViewSet(viewsets.ModelViewSet):
    serializer_class = SkillRecommendationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return SkillRecommendation.objects.filter(user=self.request.user)
