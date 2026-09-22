from django.urls import path

from apps.core.crud import crud

from . import views
from .forms import BuchungForm, KassenberichtForm
from .models import Buchung, Buchungskategorie, Kassenbericht, Konto

urlpatterns = [
    path("kassenbuch/uebernehmen/", views.buchungen_uebernehmen, name="buchungen_uebernehmen"),
    path("kassenbuch/e-rechnung/", views.erechnung_importieren, name="erechnung_importieren"),
    path("kassenberichte/<int:pk>/pdf/", views.kassenbericht_pdf_view, name="kassenbericht_pdf"),
    path("kassenberichte/<int:pk>/excel/", views.kassenbericht_xlsx_view, name="kassenbericht_xlsx"),
    path("kassenberichte/<int:pk>/abschliessen/", views.kassenbericht_abschliessen, name="kassenbericht_abschliessen"),
    path("kassenberichte/<int:pk>/oeffnen/", views.kassenbericht_oeffnen, name="kassenbericht_oeffnen"),
    path("kassenbuch/<int:pk>/beleg-ablegen/", views.buchung_beleg_ablegen, name="buchung_beleg_ablegen"),
]
urlpatterns += crud("kassenbuch", Buchung, "kassenbuch", form=BuchungForm,
                    list_display=("datum", "belegnummer", "typ", "kategorie", "text", "betrag", "konto"),
                    select_related=("kategorie", "konto"), suche=("text", "belegnummer"),
                    filter=("typ", "konto", "kategorie", "veranstaltung", "quelle"), ordering=("-datum", "-id"),
                    listen_aktionen=views.buchung_listen_aktionen, kontext=views.buchung_kontext,
                    bearbeitbar=lambda b: not b.gesperrt,
                    loeschbar=lambda b: b.quelle == "manuell" and not b.gesperrt)
urlpatterns += crud("kassenberichte", Kassenbericht, "kassenbuch", form=KassenberichtForm,
                    list_display=("titel", "von", "bis", "status", "kassenwart"), kontext=views.kassenbericht_kontext,
                    ordering=("-bis",), bearbeitbar=lambda b: b.status == "entwurf",
                    loeschbar=lambda b: b.status == "entwurf")
urlpatterns += crud("konten", Konto, "kassenbuch", list_display=("name", "typ", "eroeffnungsbestand", "eroeffnungsdatum", "aktiv"))
urlpatterns += crud("buchungskategorien", Buchungskategorie, "kassenbuch",
                    list_display=("name", "typ", "sphaere", "sortierung", "aktiv"), filter=("typ", "sphaere"),
                    ordering=("typ", "sphaere", "sortierung"))
