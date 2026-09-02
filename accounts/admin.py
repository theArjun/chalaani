from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class ChalaaniUserAdmin(UserAdmin):
    list_display = ("username", "full_name_np", "email", "active_organization", "is_staff")
    fieldsets = UserAdmin.fieldsets + (
        ("चलानी", {"fields": ("full_name_np", "phone", "active_organization")}),
    )
