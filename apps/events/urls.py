from django.urls import path

from apps.core.crud import crud

from . import views
from .models import Anmeldung, Aufgabe, Kostenposition, Schicht, Schichteinsatz, Tagesordnungspunkt, Veranstaltung

urlpatterns = [
    path("veranstaltungen/kalender.ics", views.veranstaltungen_ics, name="veranstaltungen_ics"),
    path("veranstaltungen/<int:pk>/standard-tagesordnung/", views.tagesordnung_standard, name="tagesordnung_standard"),
]
urlpatterns += crud("veranstaltungen", Veranstaltung, "veranstaltungen",
                    list_display=("beginn", "titel", "art", "ort", "status", ("verantwortlich", "Verantwortlich")),
                    suche=("titel", "ort"), filter=("status", "art"), select_related=("verantwortlich",),
                    kontext=views.veranstaltung_kontext, listen_aktionen=views.listen_aktionen, ordering=("-beginn",))
urlpatterns += crud("aufgaben", Aufgabe, "veranstaltungen", list_display=("veranstaltung", "titel", "zustaendig",
                    "faellig", "status"), select_related=("veranstaltung", "zustaendig"),
                    filter=("veranstaltung", "status", "zustaendig"))
urlpatterns += crud("schichten", Schicht, "veranstaltungen", list_display=("veranstaltung", "bezeichnung", "beginn",
                    "ende", ("besetzung", "Besetzung")), select_related=("veranstaltung",), filter=("veranstaltung",),
                    kontext=views.schicht_kontext)
urlpatterns += crud("schichteinsaetze", Schichteinsatz, "veranstaltungen", list_display=("schicht", "mitglied"),
                    select_related=("schicht", "mitglied", "schicht__veranstaltung"), filter=("schicht",))
urlpatterns += crud("anmeldungen", Anmeldung, "veranstaltungen", list_display=("veranstaltung", ("wer", "Name"),
                    "personen", "status"), select_related=("veranstaltung", "mitglied"), filter=("veranstaltung",
                    "status"))
urlpatterns += crud("kostenpositionen", Kostenposition, "veranstaltungen", list_display=("veranstaltung", "art",
                    "bezeichnung", "plan_betrag", "ist_betrag"), select_related=("veranstaltung",),
                    filter=("veranstaltung",))
urlpatterns += crud("tagesordnung", Tagesordnungspunkt, "veranstaltungen", list_display=("veranstaltung", "position", "titel",
                    "openslides_topic_id"), select_related=("veranstaltung",), filter=("veranstaltung",),
                    ordering=("veranstaltung", "position"))
