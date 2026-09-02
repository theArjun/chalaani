from django.contrib import admin

from .models import Chalani, ChalaniItem, Item, Vendor


class ChalaniItemInline(admin.TabularInline):
    model = ChalaniItem
    extra = 0


@admin.register(Chalani)
class ChalaniAdmin(admin.ModelAdmin):
    list_display = ("chalani_no", "date_bs", "vendor", "organization", "status", "extracted_by_ai")
    list_filter = ("organization", "status", "fiscal_year", "extracted_by_ai")
    search_fields = ("chalani_no", "vehicle_no", "received_by", "vendor__name", "vendor__name_np")
    date_hierarchy = "date"
    inlines = [ChalaniItemInline]
    readonly_fields = ("raw_extraction", "fiscal_year", "created_at", "updated_at")


@admin.register(Vendor)
class VendorAdmin(admin.ModelAdmin):
    list_display = ("name", "name_np", "pan_no", "phone", "organization", "is_active")
    list_filter = ("organization", "is_active", "district")
    search_fields = ("name", "name_np", "pan_no")


@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    list_display = ("name", "name_np", "unit", "default_rate", "organization", "is_active")
    list_filter = ("organization", "unit", "is_active")
    search_fields = ("name", "name_np")
