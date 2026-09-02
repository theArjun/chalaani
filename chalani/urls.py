from django.urls import path

from . import views

app_name = "chalani"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("chalani/", views.register, name="register"),
    path("chalani/upload/", views.upload, name="upload"),
    path("chalani/export.csv", views.export_csv, name="export_csv"),
    path("chalani/<int:pk>/", views.detail, name="detail"),
    path("chalani/<int:pk>/status/", views.status_fragment, name="status"),
    path("chalani/<int:pk>/row/", views.add_item_row, name="add_row"),
    path("chalani/<int:pk>/verify/", views.verify, name="verify"),
    path("chalani/<int:pk>/bill/", views.mark_billed, name="bill"),
    path("chalani/<int:pk>/reopen/", views.reopen, name="reopen"),
    path("chalani/<int:pk>/reextract/", views.reextract, name="reextract"),
    path("chalani/<int:pk>/delete/", views.delete, name="delete"),
    path("chalani/<int:pk>/photo/", views.photo, name="photo"),
    path("vendors/", views.vendor_list, name="vendor_list"),
    path("vendors/new/", views.vendor_form, name="vendor_create"),
    path("vendors/<int:pk>/", views.vendor_form, name="vendor_edit"),
    path("items/", views.item_list, name="item_list"),
    path("items/new/", views.item_form, name="item_create"),
    path("items/<int:pk>/", views.item_form, name="item_edit"),
    path("reports/vendors/", views.vendor_report, name="vendor_report"),
]
