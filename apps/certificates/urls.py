from django.urls import path

from . import views

app_name = "certificates"

urlpatterns = [
    path("certificates/", views.certificate_list, name="list"),
    path("certificates/generate/", views.certificate_generate, name="generate"),
    path("certificates/<uuid:pk>/download/", views.certificate_download, name="download"),
    path("certificates/<uuid:pk>/preview/", views.certificate_preview, name="preview"),
    path("certificates/<uuid:pk>/revoke/", views.certificate_revoke, name="revoke"),
]
