from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.http import JsonResponse

def health_check(request):
    return JsonResponse({"status": "healthy"})

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('api.urls')),
    path('api/connections/', include('connections_api.urls')),
    path('api/', include('community_api.urls')),
    path('api/research/', include('research.api_urls')),
    path('api/notifications/', include('notifications.urls')),
    path('api/chat/', include('chat_api.urls')),
    path('api/assistant/', include('assistant.urls')),
    path('api/stories/', include('stories.urls')),
    path('health/', health_check, name='health_check'),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
