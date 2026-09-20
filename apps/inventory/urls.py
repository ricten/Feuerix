from django.urls import path

from apps.core.crud import crud

from . import views
from .forms import VerleihForm
from .models import Gegenstand, Inventur, Kategorie, Standort, Verleih

urlpatterns = [
    path("verleih/<int:pk>/ausgeben/", views.verleih_ausgeben, name="verleih_ausgeben"),
    path("verleih/<int:pk>/rueckgabe/", views.verleih_rueckgabe, name="verleih_rueckgabe"),
    path("verleih/<int:pk>/stornieren/", views.verleih_stornieren, name="verleih_stornieren"),
    path("verleih/<int:pk>/leihschein/", views.verleih_leihschein, name="verleih_leihschein"),
    path("inventur/position/<int:pk>/setzen/", views.inventurposition_setzen, name="inventurposition_setzen"),
    path("inventur/<int:pk>/abschliessen/", views.inventur_abschliessen, name="inventur_abschliessen"),
]
urlpatterns += crud("inventar", Gegenstand, "inventar", list_display=("inventarnummer", "bezeichnung", "kategorie",
                    "standort", "zustand", "verleihbar", "aktueller_wert"), suche=("inventarnummer", "bezeichnung",
                    "seriennummer", "hersteller", "modell"), filter=("kategorie", "standort", "zustand", "verleihbar"),
                    select_related=("kategorie", "standort"), kontext=views.gegenstand_kontext)
urlpatterns += crud("inventar-kategorien", Kategorie, "inventar", list_display=("name",))
urlpatterns += crud("inventar-standorte", Standort, "inventar", list_display=("name", "beschreibung"))
urlpatterns += crud("verleih", Verleih, "verleih", form=VerleihForm, list_display=("gegenstand", ("wer", "Entleiher"), "von", "bis",
                    "status", "veranstaltung"), select_related=("gegenstand", "entleiher", "veranstaltung"),
                    filter=("status", "gegenstand", "entleiher", "veranstaltung"), kontext=views.verleih_kontext,
                    suche=("gegenstand__bezeichnung", "gegenstand__inventarnummer", "entleiher_name",
                           "entleiher__nachname"), ordering=("-von",),
                    bearbeitbar=lambda v: v.status in ("reserviert", "ausgegeben"),
                    loeschbar=lambda v: v.status in ("reserviert", "storniert"))
urlpatterns += crud("inventuren", Inventur, "inventur", list_display=("name", "jahr", "status", "abgeschlossen_am"),
                    kontext=views.inventur_kontext, bearbeitbar=lambda i: i.status == "laufend", delete=False)
