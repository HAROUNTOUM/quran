from django.urls import path

from . import views

app_name = "emailcenter"

urlpatterns = [
    path("dashboard/email/", views.campaign_list, name="campaigns"),
    path("dashboard/email/compose/", views.email_compose, name="compose"),
    path("dashboard/email/campaigns/<int:pk>/", views.campaign_detail, name="campaign_detail"),
    path("dashboard/email/log/", views.email_log, name="log"),
    path("dashboard/email/controls/", views.automail_controls, name="controls"),
]
