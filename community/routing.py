from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r'^ws/community/(?P<community_slug>[^/]+)/$', consumers.CommunityConsumer.as_asgi()),
    re_path(r'^ws/community/posts/(?P<post_id>\d+)/$', consumers.PostConsumer.as_asgi()),
    re_path(r'^ws/personal/posts/(?P<post_id>\d+)/$', consumers.PostConsumer.as_asgi()),
] 