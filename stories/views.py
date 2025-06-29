from django.shortcuts import render
from rest_framework import viewsets, status, permissions, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.db.models import Q, Avg, Count
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from .models import (
    Story, StoryCollaborator, StoryInteractive, StoryInteraction,
    StoryShare, StoryRating, StoryView, StoryTag,
    StoryBookmark, StoryReport, StoryAnalytics
)
from .serializers import (
    StorySerializer, StoryCreateSerializer, StoryUpdateSerializer,
    StoryCollaboratorSerializer, StoryCollaboratorCreateSerializer,
    StoryInteractiveSerializer, StoryInteractiveCreateSerializer,
    StoryInteractionSerializer, StoryInteractionCreateSerializer,
    StoryShareSerializer, StoryRatingSerializer, StoryRatingCreateSerializer,
    StoryViewSerializer, StoryViewCreateSerializer,
    StoryBookmarkSerializer, StoryBookmarkCreateSerializer,
    StoryReportSerializer, StoryReportCreateSerializer,
    StoryTagSerializer, StoryAnalyticsSerializer
)
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser
from django.db import models
from rest_framework.permissions import IsAuthenticated


class IsAuthorOrReadOnly(permissions.BasePermission):
    """Custom permission to only allow authors to edit their stories"""
    
    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        return obj.author == request.user


class IsCollaboratorOrReadOnly(permissions.BasePermission):
    """Custom permission for story collaborators"""
    
    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        return obj.story.author == request.user or obj.user == request.user


class StoryViewSet(viewsets.ModelViewSet):
    """ViewSet for Story model"""
    queryset = Story.objects.all()
    serializer_class = StorySerializer
    permission_classes = [permissions.IsAuthenticated, IsAuthorOrReadOnly]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['type', 'theme', 'author', 'is_public', 'is_active']
    search_fields = ['content', 'location_name', 'tags']
    ordering_fields = ['created_at', 'updated_at', 'views_count', 'rating']
    ordering = ['-created_at']
    
    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['request'] = self.request
        return context
    
    def get_queryset(self):
        queryset = Story.objects.filter(is_active=True)
        now = timezone.now()
        queryset = queryset.filter(models.Q(expires_at__isnull=True) | models.Q(expires_at__gt=now))

        if not self.request.user.is_staff:
            # Get friend IDs
            from connections.models import Connection
            friend_ids = set()
            connections = Connection.objects.filter(
                (Q(user1=self.request.user) | Q(user2=self.request.user)),
                is_active=True
            )
            for connection in connections:
                friend = connection.user2 if connection.user1 == self.request.user else connection.user1
                friend_ids.add(friend.id)
            queryset = queryset.filter(
                Q(author=self.request.user) |
                Q(author__id__in=friend_ids) |
                Q(collaborators__user=self.request.user)
            ).distinct()
        return queryset
    
    def get_serializer_class(self):
        if self.action == 'create':
            return StoryCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return StoryUpdateSerializer
        return StorySerializer
    
    def perform_create(self, serializer):
        serializer.save(author=self.request.user)
    
    @action(detail=True, methods=['post'])
    def like(self, request, pk=None):
        """Like/unlike a story"""
        story = self.get_object()
        user = request.user
        
        interaction, created = StoryInteraction.objects.get_or_create(
            story=story,
            user=user,
            interaction_type='like',
            defaults={'value': {'liked': True}}
        )
        
        if not created:
            # Toggle like status
            current_value = interaction.value.get('liked', False)
            interaction.value = {'liked': not current_value}
            interaction.save()
        
        return Response({'status': 'success'})
    
    @action(detail=True, methods=['post'])
    def share(self, request, pk=None):
        """Share a story"""
        story = self.get_object()
        platform = request.data.get('platform', '')
        
        share = StoryShare.objects.create(
            story=story,
            user=request.user,
            platform=platform
        )
        
        # Update story share count
        story.shares_count = story.shares.count()
        story.save(update_fields=['shares_count'])
        
        return Response(StoryShareSerializer(share).data)
    
    @action(detail=True, methods=['post'])
    def bookmark(self, request, pk=None):
        """Bookmark/unbookmark a story"""
        story = self.get_object()
        user = request.user
        
        bookmark, created = StoryBookmark.objects.get_or_create(
            story=story,
            user=user
        )
        
        if not created:
            bookmark.delete()
            return Response({'status': 'unbookmarked'})
        
        return Response(StoryBookmarkSerializer(bookmark).data)
    
    @action(detail=True, methods=['post'])
    def report(self, request, pk=None):
        """Report a story"""
        story = self.get_object()
        serializer = StoryReportCreateSerializer(data=request.data, context={'request': request})
        
        if serializer.is_valid():
            report = serializer.save()
            return Response(StoryReportSerializer(report).data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['get'])
    def analytics(self, request, pk=None):
        """Get story analytics"""
        story = self.get_object()
        analytics, created = StoryAnalytics.objects.get_or_create(story=story)
        analytics.update_analytics()
        return Response(StoryAnalyticsSerializer(analytics).data)
    
    @action(detail=False, methods=['get'])
    def my_stories(self, request):
        """Get current user's stories"""
        stories = Story.objects.filter(author=request.user).order_by('-created_at')
        page = self.paginate_queryset(stories)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(stories, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def bookmarked(self, request):
        """Get user's bookmarked stories"""
        bookmarked_stories = Story.objects.filter(
            bookmarks__user=request.user
        ).order_by('-bookmarks__created_at')
        page = self.paginate_queryset(bookmarked_stories)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(bookmarked_stories, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def trending(self, request):
        """Get trending stories"""
        trending_stories = Story.objects.filter(
            is_public=True,
            is_active=True
        ).annotate(
            engagement_score=Count('shares') + Count('ratings')
        ).order_by('-engagement_score', '-created_at')[:20]
        
        serializer = self.get_serializer(trending_stories, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post', 'delete'], permission_classes=[IsAuthenticated])
    def rate(self, request, pk=None):
        story = self.get_object()
        user = request.user
        from .models import StoryRating

        if request.method == 'DELETE':
            # Remove the user's rating
            StoryRating.objects.filter(story=story, user=user).delete()
            # Recalculate average rating and total ratings
            all_ratings = story.ratings.all()
            total_ratings = all_ratings.count()
            avg_rating = all_ratings.aggregate(models.Avg('rating'))['rating__avg'] or 0.0
            story.rating = avg_rating
            story.total_ratings = total_ratings
            story.save(update_fields=['rating', 'total_ratings'])
            return Response({
                'story_id': str(story.id),
                'rating': avg_rating,
                'total_ratings': total_ratings,
                'user_rating': 0
            })

        # POST logic
        rating_value = int(request.data.get('rating', 0))
        if rating_value < 1 or rating_value > 5:
            return Response({'error': 'Rating must be between 1 and 5'}, status=status.HTTP_400_BAD_REQUEST)

        rating_obj, created = StoryRating.objects.update_or_create(
            story=story,
            user=user,
            defaults={'rating': rating_value}
        )

        all_ratings = story.ratings.all()
        total_ratings = all_ratings.count()
        avg_rating = all_ratings.aggregate(models.Avg('rating'))['rating__avg'] or 0.0
        story.rating = avg_rating
        story.total_ratings = total_ratings
        story.save(update_fields=['rating', 'total_ratings'])

        return Response({
            'story_id': str(story.id),
            'rating': avg_rating,
            'total_ratings': total_ratings,
            'user_rating': rating_value
        })

    @action(detail=True, methods=['get'])
    def raters(self, request, pk=None):
        """Get all raters for a story"""
        story = self.get_object()
        raters = story.ratings.select_related('user').all()
        data = []
        BASE_URL = request.build_absolute_uri('/')[:-1]  # e.g. http://127.0.0.1:8000
        for r in raters:
            user = r.user
            # Get avatar or default
            if hasattr(user, 'avatar') and user.avatar:
                avatar = user.avatar.url if hasattr(user.avatar, 'url') else str(user.avatar)
            else:
                avatar = '/media/avatars/default.jpeg'
            # Ensure avatar is absolute URL
            if not avatar.startswith('http'):
                avatar = BASE_URL + avatar
            data.append({
                'id': user.id,
                'username': user.username,
                'first_name': getattr(user, 'first_name', ''),
                'last_name': getattr(user, 'last_name', ''),
                'avatar': avatar,
                'rating': r.rating,
            })
        return Response(data)

    @action(detail=True, methods=['get'])
    def viewers(self, request, pk=None):
        """Get all viewers for a story"""
        story = self.get_object()
        viewers = story.views.select_related('user').all()
        data = []
        BASE_URL = request.build_absolute_uri('/')[:-1]
        for v in viewers:
            user = v.user
            # Get avatar or default
            if hasattr(user, 'avatar') and user.avatar:
                avatar = user.avatar.url if hasattr(user.avatar, 'url') else str(user.avatar)
            else:
                avatar = '/media/avatars/default.jpeg'
            # Ensure avatar is absolute URL
            if not avatar.startswith('http'):
                avatar = BASE_URL + avatar
            data.append({
                'id': user.id,
                'username': user.username,
                'first_name': getattr(user, 'first_name', ''),
                'last_name': getattr(user, 'last_name', ''),
                'avatar': avatar,
                'viewed_at': v.viewed_at,
            })
        return Response(data)


class StoryCollaboratorViewSet(viewsets.ModelViewSet):
    """ViewSet for StoryCollaborator model"""
    queryset = StoryCollaborator.objects.all()
    serializer_class = StoryCollaboratorSerializer
    permission_classes = [permissions.IsAuthenticated, IsCollaboratorOrReadOnly]
    
    def get_serializer_class(self):
        if self.action == 'create':
            return StoryCollaboratorCreateSerializer
        return StoryCollaboratorSerializer
    
    def get_queryset(self):
        return StoryCollaborator.objects.filter(
            Q(story__author=self.request.user) | 
            Q(user=self.request.user)
        )


class StoryInteractiveViewSet(viewsets.ModelViewSet):
    """ViewSet for StoryInteractive model"""
    queryset = StoryInteractive.objects.all()
    serializer_class = StoryInteractiveSerializer
    permission_classes = [permissions.IsAuthenticated, IsAuthorOrReadOnly]
    
    def get_serializer_class(self):
        if self.action == 'create':
            return StoryInteractiveCreateSerializer
        return StoryInteractiveSerializer
    
    def get_queryset(self):
        return StoryInteractive.objects.filter(
            Q(story__author=self.request.user) | 
            Q(story__is_public=True)
        )


class StoryInteractionViewSet(viewsets.ModelViewSet):
    """ViewSet for StoryInteraction model"""
    queryset = StoryInteraction.objects.all()
    serializer_class = StoryInteractionSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_serializer_class(self):
        if self.action == 'create':
            return StoryInteractionCreateSerializer
        return StoryInteractionSerializer
    
    def get_queryset(self):
        return StoryInteraction.objects.filter(user=self.request.user)


class StoryShareViewSet(viewsets.ModelViewSet):
    """ViewSet for StoryShare model"""
    queryset = StoryShare.objects.all()
    serializer_class = StoryShareSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return StoryShare.objects.filter(user=self.request.user)


class StoryRatingViewSet(viewsets.ModelViewSet):
    """ViewSet for StoryRating model"""
    queryset = StoryRating.objects.all()
    serializer_class = StoryRatingSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_serializer_class(self):
        if self.action == 'create':
            return StoryRatingCreateSerializer
        return StoryRatingSerializer
    
    def get_queryset(self):
        return StoryRating.objects.filter(user=self.request.user)
    
    def perform_create(self, serializer):
        rating = serializer.save()
        # Update story rating
        story = rating.story
        avg_rating = story.ratings.aggregate(Avg('rating'))['rating__avg']
        story.rating = avg_rating or 0.0
        story.total_ratings = story.ratings.count()
        story.save(update_fields=['rating', 'total_ratings'])


class StoryViewViewSet(viewsets.ModelViewSet):
    """ViewSet for StoryView model"""
    queryset = StoryView.objects.all()
    serializer_class = StoryViewSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_serializer_class(self):
        if self.action == 'create':
            return StoryViewCreateSerializer
        return StoryViewSerializer
    
    def get_queryset(self):
        return StoryView.objects.filter(user=self.request.user)
    
    def perform_create(self, serializer):
        # Use get_or_create to avoid IntegrityError on duplicate (story, user)
        story = serializer.validated_data['story']
        user = self.request.user
        view, created = StoryView.objects.get_or_create(
            story=story,
            user=user,
            defaults={
                'view_duration': serializer.validated_data.get('view_duration', 0),
                'completed': serializer.validated_data.get('completed', False),
            }
        )
        # Optionally update view_duration/completed if provided and not created
        if not created:
            updated = False
            if 'view_duration' in serializer.validated_data:
                view.view_duration = serializer.validated_data['view_duration']
                updated = True
            if 'completed' in serializer.validated_data:
                view.completed = serializer.validated_data['completed']
                updated = True
            if updated:
                view.save(update_fields=['view_duration', 'completed'])
        story.views_count = story.views.count()
        story.save(update_fields=['views_count'])


class StoryBookmarkViewSet(viewsets.ModelViewSet):
    """ViewSet for StoryBookmark model"""
    queryset = StoryBookmark.objects.all()
    serializer_class = StoryBookmarkSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_serializer_class(self):
        if self.action == 'create':
            return StoryBookmarkCreateSerializer
        return StoryBookmarkSerializer
    
    def get_queryset(self):
        return StoryBookmark.objects.filter(user=self.request.user)


class StoryReportViewSet(viewsets.ModelViewSet):
    """ViewSet for StoryReport model"""
    queryset = StoryReport.objects.all()
    serializer_class = StoryReportSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_serializer_class(self):
        if self.action == 'create':
            return StoryReportCreateSerializer
        return StoryReportSerializer
    
    def get_queryset(self):
        return StoryReport.objects.filter(reporter=self.request.user)


class StoryTagViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for StoryTag model (read-only)"""
    queryset = StoryTag.objects.all()
    serializer_class = StoryTagSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [filters.SearchFilter]
    search_fields = ['name']
    
    @action(detail=False, methods=['get'])
    def popular(self, request):
        """Get popular tags"""
        popular_tags = StoryTag.objects.order_by('-usage_count')[:20]
        serializer = self.get_serializer(popular_tags, many=True)
        return Response(serializer.data)


class StoryAnalyticsViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for StoryAnalytics model (read-only)"""
    queryset = StoryAnalytics.objects.all()
    serializer_class = StoryAnalyticsSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return StoryAnalytics.objects.filter(
            Q(story__author=self.request.user) | 
            Q(story__is_public=True)
        )


class MediaUploadView(APIView):
    parser_classes = (MultiPartParser, FormParser)
    permission_classes = [permissions.IsAuthenticated]  # Or AllowAny if you want public upload

    def post(self, request, *args, **kwargs):
        file_obj = request.FILES.get('media_file')
        if not file_obj:
            return Response({'error': 'No file provided.'}, status=status.HTTP_400_BAD_REQUEST)
        from django.core.files.storage import default_storage
        file_path = default_storage.save(f'stories/media/{file_obj.name}', file_obj)
        file_url = default_storage.url(file_path)
        return Response({'media_url': file_url}, status=status.HTTP_201_CREATED)
