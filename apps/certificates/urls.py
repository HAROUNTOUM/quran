from django.urls import path

from . import views

app_name = "certificates"

urlpatterns = [
    path("certificates/", views.certificate_list, name="list"),
    path("certificates/generate/", views.certificate_generate, name="generate"),
    path("certificates/own/", views.student_certificates, name="own"),
    path("certificates/<int:pk>/download/", views.certificate_download, name="download"),
    path("certificates/<int:pk>/preview/", views.certificate_preview, name="preview"),
    path("certificates/<int:pk>/revoke/", views.certificate_revoke, name="revoke"),
]
