from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'connections', views.ConnectionViewSet, basename='connection')
router.register(r'requests', views.ConnectionRequestViewSet, basename='connection-request')
router.register(r'suggestions', views.UserSuggestionViewSet, basename='user-suggestion')

urlpatterns = [
    path('', include(router.urls)),
] 