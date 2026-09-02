from django.urls import path

from . import views

app_name = "nepal"

urlpatterns = [
    path("date-preview/", views.date_preview, name="date_preview"),
    path("date-input/", views.date_input, name="date_input"),
]
