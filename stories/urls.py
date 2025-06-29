from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

# Create routers for all ViewSets
router = DefaultRouter()
router.register(r'stories', views.StoryViewSet, basename='story')
router.register(r'collaborators', views.StoryCollaboratorViewSet, basename='story-collaborator')
router.register(r'interactives', views.StoryInteractiveViewSet, basename='story-interactive')
router.register(r'interactions', views.StoryInteractionViewSet, basename='story-interaction')
router.register(r'shares', views.StoryShareViewSet, basename='story-share')
router.register(r'ratings', views.StoryRatingViewSet, basename='story-rating')
router.register(r'views', views.StoryViewViewSet, basename='story-view')
router.register(r'bookmarks', views.StoryBookmarkViewSet, basename='story-bookmark')
router.register(r'reports', views.StoryReportViewSet, basename='story-report')
router.register(r'tags', views.StoryTagViewSet, basename='story-tag')
router.register(r'analytics', views.StoryAnalyticsViewSet, basename='story-analytics')

urlpatterns = [
    path('media-upload/', views.MediaUploadView.as_view(), name='media-upload'),
    path('', include(router.urls)),
] 