from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("login/", views.ChalaaniLoginView.as_view(), name="login"),
    path("logout/", views.ChalaaniLogoutView.as_view(), name="logout"),
    path("signup/", views.signup, name="signup"),
]
