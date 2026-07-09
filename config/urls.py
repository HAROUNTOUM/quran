from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static
from django.views.static import serve

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("apps.accounts.urls")),
    path("", include("apps.classrooms.urls")),
    path("", include("apps.memorization.urls")),
    path("api/v1/", include("apps.api.urls")),
    path("dashboard/", include("apps.certificates.urls")),
    path("", include("apps.webinars.urls")),
    path("", include("apps.reports.urls")),
    path("", include("apps.usersettings.urls")),
    path("", include("apps.chat.urls")),
    path("", include("apps.emailcenter.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += [
        path("__debug__/", include("debug_toolbar.urls")),
    ]
else:
    urlpatterns += [
        re_path(r"^static/(?P<path>.*)$", serve, {"document_root": settings.STATIC_ROOT}),
        re_path(r"^media/(?P<path>.*)$", serve, {"document_root": settings.MEDIA_ROOT}),
    ]
