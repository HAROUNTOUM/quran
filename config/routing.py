from django.urls import re_path
from apps.api.consumers import SessionProgressConsumer, NotificationConsumer
from apps.chat.consumers import ChatConsumer

websocket_urlpatterns = [
    re_path(r"ws/sessions/(?P<session_id>\d+)/progress/$", SessionProgressConsumer.as_asgi()),
    re_path(r"ws/notifications/$", NotificationConsumer.as_asgi()),
    re_path(r"ws/chat/(?P<conversation_id>\d+)/$", ChatConsumer.as_asgi()),
]
