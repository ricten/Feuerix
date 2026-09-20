from django.urls import path

from . import views
from .crud import abschnitt, crud
from .forms import RolleForm, ZugangForm
from .models import AuditLog, Rolle, Zugang


def audit_kontext(request, obj):
    zeilen = [{"zellen": [feld, a if a is not None else "–", n if n is not None else "–"]}
              for feld, (a, n) in (obj.aenderungen or {}).items()]
    return {"abschnitte": [{"titel": "Änderungen", "spalten": ["Feld", "Vorher", "Nachher"], "zeilen": zeilen,
                            "add_url": None}]}


urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("nach-anmeldung/", views.nach_login, name="nach_login"),
    path("verein/waehlen/", views.verein_waehlen, name="verein_waehlen"),
    path("verein/logo/", views.verein_logo, name="verein_logo"),
    path("verein/einstellungen/", views.verein_einstellungen, name="verein_einstellungen"),
    path("datei/<str:app_label>/<str:modell>/<int:pk>/<str:feld>/", views.datei, name="datei"),
    path("auswertungen/", views.auswertungen, name="auswertungen"),
]
urlpatterns += crud("protokoll", AuditLog, "audit", add=False, edit=False, delete=False,
                    list_display=("zeit", "user_name", "aktion", "modell", "objekt_repr", "grund"),
                    suche=("objekt_repr", "user_name", "modell"), filter=("modell", "objekt_id", "aktion"),
                    ordering=("-zeit",), kontext=audit_kontext, detail_ausblenden=("aenderungen",))
urlpatterns += crud("rollen", Rolle, "verwaltung", form=RolleForm, list_display=("name", "ist_superadmin",
                    ("anzahl_rechte", "Anzahl Rechte")), ordering=("name",))
urlpatterns += crud("benutzer", Zugang, "verwaltung", form=ZugangForm,
                    list_display=(("user", "Benutzer"), "rolle", "aktiv"), select_related=("user", "rolle"),
                    detail_ausblenden=("extra_rechte",))
