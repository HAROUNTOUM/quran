from django.urls import path

from apps.classrooms import views

app_name = "classrooms"

urlpatterns = [
    path("dashboard/classroom/", views.my_classroom, name="my_classroom"),
    path("dashboard/classrooms/join/<slug:slug>/", views.join_room, name="join"),
    path("dashboard/classrooms/", views.rooms_admin_list, name="admin_list"),
]
