from django.urls import path

from apps.webinars import views

app_name = "webinars"

urlpatterns = [
    # Audience
    path("dashboard/webinars/", views.webinar_list, name="list"),
    path("dashboard/webinars/<int:pk>/watch/", views.webinar_watch, name="watch"),
    # Speakers (small group — the real Jitsi call)
    path("dashboard/webinars/<int:pk>/speaker-room/", views.speaker_room, name="speaker_room"),
    # Admin management (separate namespace path per Section D)
    path("dashboard/webinars/manage/", views.webinar_admin_list, name="admin_list"),
    path("dashboard/webinars/manage/create/", views.webinar_create, name="admin_create"),
    path("dashboard/webinars/manage/<int:pk>/", views.webinar_manage, name="admin_manage"),
]
