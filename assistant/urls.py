from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'memories', views.AssistantMemoryViewSet, basename='assistant-memory')
router.register(r'notifications', views.AssistantNotificationViewSet, basename='assistant-notification')
router.register(r'interest-alchemy', views.InterestAlchemyViewSet, basename='interest-alchemy')
router.register(r'curiosity-collisions', views.CuriosityCollisionViewSet, basename='curiosity-collision')
router.register(r'micro-communities', views.MicroCommunityViewSet, basename='micro-community')
router.register(r'post-suggestions', views.PostSuggestionViewSet, basename='post-suggestion')
router.register(r'community-suggestions', views.CommunitySuggestionViewSet, basename='community-suggestion')
router.register(r'connection-suggestions', views.ConnectionSuggestionViewSet, basename='connection-suggestion')
router.register(r'content-recommendations', views.ContentRecommendationViewSet, basename='content-recommendation')
router.register(r'skill-recommendations', views.SkillRecommendationViewSet, basename='skill-recommendation')

urlpatterns = [
    path('', include(router.urls)),
] 