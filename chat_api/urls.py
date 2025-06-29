from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

# Create a router and register our viewsets with it
router = DefaultRouter()
router.register(r'conversations', views.ConversationViewSet, basename='conversation')
router.register(r'messages', views.MessageViewSet, basename='message')
router.register(r'message-reactions', views.MessageReactionViewSet, basename='message-reaction')
router.register(r'message-threads', views.MessageThreadViewSet, basename='message-thread')
router.register(r'message-effects', views.MessageEffectViewSet, basename='message-effect')
router.register(r'link-previews', views.LinkPreviewViewSet, basename='link-preview')
router.register(r'groups', views.GroupViewSet, basename='group')
router.register(r'real-time-suggestions', views.RealTimeSuggestionViewSet, basename='real-time-suggestion')

# Create nested routers for messages and related resources
from rest_framework_nested import routers
conversations_router = routers.NestedDefaultRouter(router, r'conversations', lookup='conversation')
conversations_router.register(r'messages', views.MessageViewSet, basename='conversation-messages')
conversations_router.register(r'update_group', views.UpdateGroupThroughConversationViewSet, basename='conversation-update-group')
conversations_router.register(r'real-time-suggestions', views.RealTimeSuggestionViewSet, basename='conversation-real-time-suggestions')

messages_router = routers.NestedDefaultRouter(conversations_router, r'messages', lookup='message')
messages_router.register(r'reactions', views.MessageReactionViewSet, basename='message-reactions')
messages_router.register(r'threads', views.MessageThreadViewSet, basename='message-threads')
messages_router.register(r'effects', views.MessageEffectViewSet, basename='message-effects')
messages_router.register(r'link-previews', views.LinkPreviewViewSet, basename='message-link-previews')

# The API URLs are now determined automatically by the router
urlpatterns = [
    path('', include(router.urls)),
    path('', include(conversations_router.urls)),
    path('', include(messages_router.urls)),
    path('upload/', views.upload_file, name='upload-file'),
] 