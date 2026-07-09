from django.urls import path

from apps.usersettings import views

app_name = "usersettings"

urlpatterns = [
    path("dashboard/settings/", views.settings_home, name="home"),
]
