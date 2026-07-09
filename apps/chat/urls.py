from django.urls import path

from . import views

app_name = "chat"

urlpatterns = [
    path("dashboard/messages/", views.inbox, name="inbox"),
    path("dashboard/messages/<int:conversation_id>/", views.inbox, name="conversation"),
    path("dashboard/messages/<int:conversation_id>/send/", views.send, name="send"),
    path("dashboard/messages/start/", views.start, name="start"),
]
