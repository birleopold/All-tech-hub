from django.contrib import admin

from crm.models import Customer, CustomerAddress


class AddressInline(admin.TabularInline):
    model = CustomerAddress
    extra = 0


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("name", "company_name", "email", "phone", "created_at")
    search_fields = ("name", "company_name", "email", "phone")
    inlines = [AddressInline]
