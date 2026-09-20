from django.apps import apps as django_apps
from django.contrib import admin

from .models import AuditLog, Rolle, TenantModel, Verein, Zugang


class TenantAdmin(admin.ModelAdmin):
    list_filter = ("verein",)


admin.site.register(Verein)
admin.site.register(Rolle)
admin.site.register(Zugang)


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("zeit", "verein", "user_name", "aktion", "modell", "objekt_repr")
    list_filter = ("verein", "aktion", "modell")
    search_fields = ("objekt_repr", "user_name")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


for _m in django_apps.get_models():
    if issubclass(_m, TenantModel) and not admin.site.is_registered(_m):
        admin.site.register(_m, TenantAdmin)
