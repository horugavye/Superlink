from django.urls import path
from . import views

urlpatterns = [
    path('discover/', views.discover_users, name='discover_users'),
    path('suggestions/refresh/', views.refresh_suggestions, name='refresh_suggestions'),
    path('alchemy-batch/', views.alchemy_batch, name='alchemy_batch'),
    path('alchemy-suggestions/', views.alchemy_suggestions, name='alchemy_suggestions'),
] 