from django.apps import apps as django_apps
from django.contrib import admin
from django.shortcuts import redirect

from .models import AuditLog, Rolle, Systemeinstellung, TenantModel, Verein, Zugang


class TenantAdmin(admin.ModelAdmin):
    list_filter = ("verein",)


@admin.register(Verein)
class VereinAdmin(admin.ModelAdmin):
    """Mandantenfähigkeit ist aktuell gesperrt: es lässt sich kein zweiter Verein anlegen, solange schon
    einer existiert (die zugrunde liegende Mandantentrennung im Datenmodell bleibt unangetastet)."""

    def has_add_permission(self, request):
        return not Verein.objects.exists()


admin.site.register(Rolle)
admin.site.register(Zugang)


@admin.register(Systemeinstellung)
class SystemeinstellungAdmin(admin.ModelAdmin):
    """Genau ein Datensatz (Singleton) - die Liste führt direkt auf die Bearbeitungsseite, "Hinzufügen" ist
    nur möglich, solange noch keiner existiert."""
    readonly_fields = ("update_verfuegbare_version", "update_geprueft_am")

    def has_add_permission(self, request):
        return not Systemeinstellung.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        obj = Systemeinstellung.laden()
        if not obj.pk:
            return super().changelist_view(request, extra_context)
        return redirect("admin:core_systemeinstellung_change", obj.pk)


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
