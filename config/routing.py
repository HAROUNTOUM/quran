from django.urls import re_path
from apps.api.consumers import SessionProgressConsumer, NotificationConsumer

websocket_urlpatterns = [
    re_path(r"ws/sessions/(?P<session_id>\d+)/progress/$", SessionProgressConsumer.as_asgi()),
    re_path(r"ws/notifications/$", NotificationConsumer.as_asgi()),
]
