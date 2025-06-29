from django.urls import path
from .api_views import UserListView

urlpatterns = [
    path('people/', UserListView.as_view(), name='user-list'),
] 