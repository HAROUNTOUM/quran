from django.urls import path

from apps.memorization import views

app_name = "memorization"

urlpatterns = [
    path("dashboard/progress/", views.student_progress, name="student_progress"),
    path("dashboard/estimator/", views.completion_estimator, name="estimator"),
]
