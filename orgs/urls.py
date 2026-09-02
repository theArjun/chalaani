from django.urls import path

from . import views

app_name = "orgs"

urlpatterns = [
    path("new/", views.create, name="create"),
    path("switch/<int:pk>/", views.switch, name="switch"),
    path("settings/", views.settings_view, name="settings"),
    path("members/<int:pk>/remove/", views.remove_member, name="remove_member"),
]
