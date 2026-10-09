from django.urls import path

from apps.core.crud import crud

from . import views
from .forms import AufgabeForm
from .models import (Anmeldung, Aufgabe, AufgabeNotiz, Kostenposition, Schicht, Schichteinsatz, Tagesordnungspunkt,
                     Veranstaltung, Wahlergebnis)


def _aufgabe_zeile_klasse(a):
    stufe = a.faelligkeits_stufe
    return "table-danger" if stufe == "rot" else ("table-warning" if stufe == "gelb" else "")

urlpatterns = [
    path("veranstaltungen/kalender.ics", views.veranstaltungen_ics, name="veranstaltungen_ics"),
    path("veranstaltungen/<int:pk>/standard-tagesordnung/", views.tagesordnung_standard, name="tagesordnung_standard"),
    path("veranstaltungen/rueckmeldung/<uuid:code>/", views.rueckmeldung, name="veranstaltung_rueckmeldung"),
]
urlpatterns += crud("veranstaltungen", Veranstaltung, "veranstaltungen",
                    list_display=("beginn", "titel", "art", "ort", "status", ("verantwortlich", "Verantwortlich")),
                    suche=("titel", "ort"), filter=("status", "art"), select_related=("verantwortlich",),
                    kontext=views.veranstaltung_kontext, listen_aktionen=views.listen_aktionen, ordering=("-beginn",))
urlpatterns += crud("aufgaben", Aufgabe, "veranstaltungen", form=AufgabeForm, list_display=("titel", "veranstaltung",
                    ("wer_zustaendig", "Zuständig"), "faellig", "status"),
                    select_related=("veranstaltung", "zustaendig", "zustaendig_benutzer"),
                    filter=("veranstaltung", "status", "zustaendig"), kontext=views.aufgabe_kontext,
                    ordering=("titel",), zeile_klasse=_aufgabe_zeile_klasse)
urlpatterns += crud("aufgabenotizen", AufgabeNotiz, "veranstaltungen", list_display=("aufgabe", "erstellt",
                    "erstellt_von", "text"), select_related=("aufgabe",), filter=("aufgabe",), edit=False,
                    nach_speichern=views.notiz_nach_speichern)
urlpatterns += crud("schichten", Schicht, "veranstaltungen", list_display=("veranstaltung", "bezeichnung", "beginn",
                    "ende", ("besetzung", "Besetzung")), select_related=("veranstaltung",), filter=("veranstaltung",),
                    kontext=views.schicht_kontext)
urlpatterns += crud("schichteinsaetze", Schichteinsatz, "veranstaltungen", list_display=("schicht", "mitglied"),
                    select_related=("schicht", "mitglied", "schicht__veranstaltung"), filter=("schicht",))
urlpatterns += crud("anmeldungen", Anmeldung, "teilnehmer", list_display=("veranstaltung", ("wer", "Name"),
                    "personen", "status"), select_related=("veranstaltung", "mitglied"), filter=("veranstaltung",
                    "status"))
urlpatterns += crud("kostenpositionen", Kostenposition, "veranstaltungen", list_display=("veranstaltung", "art",
                    "bezeichnung", "plan_betrag", "ist_betrag"), select_related=("veranstaltung",),
                    filter=("veranstaltung",))
urlpatterns += crud("tagesordnung", Tagesordnungspunkt, "veranstaltungen", list_display=("veranstaltung", "position", "titel",
                    "openslides_topic_id"), select_related=("veranstaltung",), filter=("veranstaltung",),
                    ordering=("veranstaltung", "position"))
urlpatterns += crud("wahlergebnisse", Wahlergebnis, "veranstaltungen", list_display=("veranstaltung", "amt", "wahlgang"),
                    select_related=("veranstaltung",), filter=("veranstaltung",), add=False, edit=False)
