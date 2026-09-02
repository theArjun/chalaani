from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("i18n/", include("django.conf.urls.i18n")),  # set_language
    path("accounts/", include("accounts.urls")),
    path("org/", include("orgs.urls")),
    path("np/", include("nepal.urls")),
    path("", include("chalani.urls")),
]
