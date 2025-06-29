from django.urls import path
from . import views

urlpatterns = [
    path('conversations/<int:conversation_id>/messages/', views.get_messages, name='get_messages'),
    path('conversations/<int:conversation_id>/messages/<int:message_id>/', views.get_message, name='get_message'),
    path('messages/send/', views.send_message, name='send_message'),
    path('messages/<int:message_id>/status/', views.update_message_status, name='update_message_status'),
    path('messages/<int:message_id>/react/', views.react_to_message, name='react_to_message'),
    path('conversations/<int:conversation_id>/messages/<int:message_id>/threads/', views.create_thread, name='create_thread'),
    path('conversations/<int:conversation_id>/members/', views.get_conversation_members, name='get_conversation_members'),
    path('conversations/<int:conversation_id>/update_group/', views.update_group_through_conversation, name='update_group_through_conversation'),
] 