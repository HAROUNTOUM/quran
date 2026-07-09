from django.urls import path
from apps.reports import views

app_name = "reports"

urlpatterns = [
    path("dashboard/reports/csv/", views.report_csv_export, name="csv_export"),
]
