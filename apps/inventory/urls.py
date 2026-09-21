from django.urls import path

from apps.core.crud import crud, knopf

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
    path("inventar/import/", views.gegenstand_import, name="gegenstand_import"),
    path("inventar/import/vorlage/", views.gegenstand_import_vorlage, name="gegenstand_import_vorlage"),
    path("inventar/etiketten/", views.gegenstand_etiketten, name="gegenstand_etiketten"),
    path("inventar/<int:pk>/etikett/", views.gegenstand_etikett, name="gegenstand_etikett"),
    path("inventar/scan/<str:inventarnummer>/", views.gegenstand_scan, name="gegenstand_scan"),
    path("verleih/mehrere/", views.verleih_sammel_add, name="verleih_sammel_add"),
    path("verleih/vorgang/<uuid:vorgang>/", views.verleih_vorgang_detail, name="verleih_vorgang_detail"),
    path("verleih/vorgang/<uuid:vorgang>/ausgeben/", views.verleih_vorgang_ausgeben, name="verleih_vorgang_ausgeben"),
    path("verleih/vorgang/<uuid:vorgang>/rueckgabe/", views.verleih_vorgang_rueckgabe, name="verleih_vorgang_rueckgabe"),
    path("verleih/vorgang/<uuid:vorgang>/leihschein/", views.verleih_vorgang_leihschein,
        name="verleih_vorgang_leihschein"),
]


def gegenstand_listen_aktionen(request):
    from django.urls import reverse
    a = []
    if request.rechte.darf("inventar", "add"):
        a.append(knopf("Import (Excel/CSV)", reverse("gegenstand_import"), stil="outline-primary"))
    if request.rechte.darf("inventar", "view"):
        a.append(knopf("Etiketten drucken (alle)", reverse("gegenstand_etiketten")))
    return a


def verleih_listen_aktionen(request):
    from django.urls import reverse
    a = []
    if request.rechte.darf("verleih", "add"):
        a.append(knopf("Mehrere Gegenstände verleihen", reverse("verleih_sammel_add"), stil="outline-primary"))
    return a


urlpatterns += crud("inventar", Gegenstand, "inventar", list_display=("inventarnummer", "bezeichnung", "kategorie",
                    "standort", "zustand", "verleihbar", "aktueller_wert"), suche=("inventarnummer", "bezeichnung",
                    "seriennummer", "hersteller", "modell"), filter=("kategorie", "standort", "zustand", "verleihbar"),
                    select_related=("kategorie", "standort"), kontext=views.gegenstand_kontext,
                    listen_aktionen=gegenstand_listen_aktionen)
urlpatterns += crud("inventar-kategorien", Kategorie, "inventar", list_display=("name",))
urlpatterns += crud("inventar-standorte", Standort, "inventar", list_display=("name", "beschreibung"))
urlpatterns += crud("verleih", Verleih, "verleih", form=VerleihForm, list_display=("gegenstand", ("wer", "Entleiher"), "von", "bis",
                    "status", "veranstaltung"), select_related=("gegenstand", "entleiher", "veranstaltung"),
                    filter=("status", "gegenstand", "entleiher", "veranstaltung"), kontext=views.verleih_kontext,
                    suche=("gegenstand__bezeichnung", "gegenstand__inventarnummer", "entleiher_name",
                           "entleiher__nachname"), ordering=("-von",),
                    bearbeitbar=lambda v: v.status in ("reserviert", "ausgegeben"),
                    loeschbar=lambda v: v.status in ("reserviert", "storniert"), listen_aktionen=verleih_listen_aktionen)
urlpatterns += crud("inventuren", Inventur, "inventur", list_display=("name", "jahr", "status", "abgeschlossen_am"),
                    kontext=views.inventur_kontext, bearbeitbar=lambda i: i.status == "laufend", delete=False)
