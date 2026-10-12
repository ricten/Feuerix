from django.urls import path

from . import benutzer_sicherheit, hilfe, matrix_views, sicherung_views, views, zf_views
from .crud import abschnitt, crud
from .forms import RolleForm, ZugangForm
from .models import AuditLog, Rolle, Zugang


def audit_kontext(request, obj):
    zeilen = [{"zellen": [feld, a if a is not None else "–", n if n is not None else "–"]}
              for feld, (a, n) in (obj.aenderungen or {}).items()]
    return {"abschnitte": [{"titel": "Änderungen", "spalten": ["Feld", "Vorher", "Nachher"], "zeilen": zeilen,
                            "add_url": None}]}


def benutzer_kontext(request, zugang):
    knoepfe, hinweise = benutzer_sicherheit.aktionen(request, zugang)
    return {"aktionen": knoepfe, "hinweise": hinweise}


urlpatterns = [
    path("benutzer/<int:pk>/entsperren/", benutzer_sicherheit.benutzer_entsperren, name="benutzer_entsperren"),
    path("benutzer/<int:pk>/2fa-zuruecksetzen/", benutzer_sicherheit.benutzer_zf_reset, name="benutzer_zf_reset"),
    path("benutzer/<int:pk>/passwort/", benutzer_sicherheit.benutzer_passwort, name="benutzer_passwort"),
    path("", views.dashboard, name="dashboard"),
    path("dashboard/kacheln/", views.dashboard_kacheln_speichern, name="dashboard_kacheln_speichern"),
    path("nach-anmeldung/", views.nach_login, name="nach_login"),
    path("zwei-faktor/", zf_views.zf_verwalten, name="zf_verwalten"),
    path("zwei-faktor/einrichten/", zf_views.zf_einrichten, name="zf_einrichten"),
    path("zwei-faktor/pruefen/", zf_views.zf_pruefen, name="zf_pruefen"),
    path("verein/waehlen/", views.verein_waehlen, name="verein_waehlen"),
    path("verein/logo/", views.verein_logo, name="verein_logo"),
    path("verein/einstellungen/", views.verein_einstellungen, name="verein_einstellungen"),
    path("datei/<str:app_label>/<str:modell>/<int:pk>/<str:feld>/", views.datei, name="datei"),
    path("auswertungen/", views.auswertungen, name="auswertungen"),
    path("verwaltung/anbindungen/", views.anbindungen_uebersicht, name="anbindungen"),
    path("verwaltung/berechtigungsmatrix/", matrix_views.berechtigungsmatrix, name="berechtigungsmatrix"),
    path("verwaltung/berechtigungsmatrix/datenschutzordnung/", matrix_views.berechtigungsmatrix_dso,
         name="berechtigungsmatrix_dso"),
    path("verwaltung/datensicherung/", sicherung_views.datensicherung_einstellungen, name="datensicherung"),
    path("verwaltung/datensicherung/jetzt/", sicherung_views.datensicherung_jetzt, name="datensicherung_jetzt"),
    path("verwaltung/datensicherung/test/", sicherung_views.datensicherung_test, name="datensicherung_test"),
    path("verwaltung/datensicherung/wiederherstellen/", sicherung_views.datensicherung_wiederherstellen,
         name="datensicherung_wiederherstellen"),
    path("verwaltung/datensicherung/hochladen/", sicherung_views.datensicherung_hochladen,
         name="datensicherung_hochladen"),
    path("verwaltung/datensicherung/datei/<str:name>/", sicherung_views.datensicherung_download,
         name="datensicherung_download"),
    path("impressum/<slug:kuerzel>/", views.impressum, name="impressum"),
    path("downloads/<slug:kuerzel>/", views.oeffentliche_dokumente, name="oeffentliche_dokumente"),
    path("downloads/<slug:kuerzel>/<int:pk>/", views.oeffentliches_dokument_download,
        name="oeffentliches_dokument_download"),
    path("hilfe/", hilfe.hilfe, name="hilfe"),
    path("hilfe/<slug:slug>/", hilfe.hilfe_dokument, name="hilfe_dokument"),
]
urlpatterns += crud("protokoll", AuditLog, "audit", add=False, edit=False, delete=False,
                    list_display=("zeit", "user_name", "aktion", "modell", "objekt_repr", "grund"),
                    suche=("objekt_repr", "user_name", "modell"), filter=("modell", "objekt_id", "aktion"),
                    ordering=("-zeit",), kontext=audit_kontext, detail_ausblenden=("aenderungen",))
urlpatterns += crud("rollen", Rolle, "verwaltung", form=RolleForm, list_display=("name", "ist_superadmin",
                    ("anzahl_rechte", "Anzahl Rechte")), ordering=("name",),
                    hinweis="Für Fortgeschrittene / technische Betreuung: Rechte lassen sich für die meisten "
                            "Fälle einfacher über Tags vergeben (Verwaltung › Funktionen: Tags – dort auch mit "
                            "oder ohne eigene Rechte neu anlegbar) oder in der Berechtigungsmatrix anpassen.")
urlpatterns += crud("benutzer", Zugang, "verwaltung", form=ZugangForm,
                    list_display=(("user", "Benutzer"), "rolle", "aktiv"), select_related=("user", "rolle"),
                    detail_ausblenden=("extra_rechte",), kontext=benutzer_kontext)
