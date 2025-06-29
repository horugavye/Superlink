from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_nested import routers
from . import views
from .views import CommunityMembersListView, CommunityMemberDetailView

# Create a router and register our viewsets with it
router = DefaultRouter()
router.register(r'communities', views.CommunityViewSet, basename='community')
router.register(r'posts', views.PostViewSet, basename='post')
router.register(r'saved-posts', views.SavedPostViewSet, basename='saved-posts')

# Register nested routers
communities_router = routers.NestedDefaultRouter(router, r'communities', lookup='community')
communities_router.register(r'posts', views.PostViewSet, basename='community-post')
communities_router.register(r'events', views.EventViewSet, basename='community-event')
communities_router.register(r'topics', views.TopicViewSet, basename='community-topic')

# Create nested router for posts
posts_router = routers.NestedDefaultRouter(communities_router, r'posts', lookup='post')
posts_router.register(r'comments', views.CommentViewSet, basename='post-comment')
posts_router.register(r'rate', views.PostViewSet, basename='post-rate')

# Create nested router for comments
comments_router = routers.NestedDefaultRouter(posts_router, r'comments', lookup='comment')
comments_router.register(r'replies', views.ReplyViewSet, basename='comment-reply')
comments_router.register(r'rate', views.CommentViewSet, basename='comment-rate')

# Create nested router for replies
replies_router = routers.NestedDefaultRouter(comments_router, r'replies', lookup='reply')
replies_router.register(r'rate', views.ReplyViewSet, basename='reply-rate')

# Add personal posts router
personal_posts_router = routers.NestedDefaultRouter(router, r'posts', lookup='post')
personal_posts_router.register(r'comments', views.CommentViewSet, basename='personal-post-comment')
personal_posts_router.register(r'rate', views.PostViewSet, basename='personal-post-rate')

# The API URLs are now determined automatically by the router
urlpatterns = [
    # Place specific URL patterns before router includes to ensure they take precedence
    path('communities/trending-topics/', views.TrendingTopicsView.as_view(), name='trending-topics'),
    path('communities/posts/feed/', views.PostViewSet.as_view({'get': 'feed'}), name='post-feed'),
    path('communities/<slug:slug>/members/', CommunityMembersListView.as_view(), name='community-members-list'),
    path('communities/<slug:slug>/members/<int:pk>/', CommunityMemberDetailView.as_view(), name='community-members-detail'),
    
    # Router-generated URLs
    path('', include(router.urls)),
    path('', include(communities_router.urls)),
    path('', include(posts_router.urls)),
    path('', include(comments_router.urls)),
    path('', include(replies_router.urls)),
    path('', include(personal_posts_router.urls)),
] 