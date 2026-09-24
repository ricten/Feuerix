from datetime import date

from django.urls import path

from apps.core.crud import crud

from . import views
from .forms import RechnungForm, RechnungspositionForm
from .models import (Bankumsatz, Beitragsjahr, Beitragsregel, Mahnung, Rechnung, Rechnungsposition, SepaEinzug,
                     SepaEinzugPosition, Zahlung)


def _rechnung_nach_speichern(request, obj, neu):
    obj.neu_berechnen()


def _bearbeitbar_entwurf(o):
    return o.status == "entwurf"


def _position_bearbeitbar(o):
    return o.rechnung.status == "entwurf"


urlpatterns = [
    path("rechnungen/<int:pk>/pdf/", views.rechnung_pdf_view, name="rechnung_pdf"),
    path("rechnungen/<int:pk>/e-rechnung/", views.rechnung_erechnung_view, name="rechnung_erechnung"),
    path("rechnungen/<int:pk>/ausstellen/", views.rechnung_ausstellen, name="rechnung_ausstellen"),
    path("rechnungen/<int:pk>/storno/", views.rechnung_storno, name="rechnung_storno"),
    path("rechnungen/<int:pk>/mail/", views.rechnung_mail, name="rechnung_mail"),
    path("rechnungen/<int:pk>/mahnung/", views.rechnung_mahnung, name="rechnung_mahnung"),
    path("mahnungen/<int:pk>/pdf/", views.mahnung_pdf_view, name="mahnung_pdf"),
    path("beitragsjahre/<int:pk>/abrechnen/", views.beitragsjahr_abrechnen, name="beitragsjahr_abrechnen"),
    path("beitragsjahre/<int:pk>/mailen/", views.beitragsjahr_mailen, name="beitragsjahr_mailen"),
    path("bank/import/", views.bank_import, name="bank_import"),
    path("bank/zuordnen/", views.bank_zuordnen, name="bank_zuordnen"),
    path("bank/<int:pk>/zuweisen/", views.bankumsatz_zuweisen, name="bankumsatz_zuweisen"),
    path("bank/<int:pk>/ignorieren/", views.bankumsatz_ignorieren, name="bankumsatz_ignorieren"),
    path("fints/", views.fints_einstellungen, name="fints_einstellungen"),
    path("fints/abrufen/", views.fints_abrufen, name="fints_abrufen"),
    path("sepa-einzuege/neu/", views.sepa_einzug_neu, name="sepa_einzug_neu"),
]
urlpatterns += crud("beitragsjahre", Beitragsjahr, "beitraege", list_display=("jahr", "faelligkeit", "alters_stichtag",
                    "abgerechnet_am"), kontext=views.beitragsjahr_kontext, ordering=("-jahr",))
urlpatterns += crud("beitragsregeln", Beitragsregel, "beitraege", list_display=("name", "mitgliedsart", "nur_familie",
                    "alter_von", "alter_bis", "betrag", "prioritaet", "aktiv"), select_related=("mitgliedsart",))
urlpatterns += crud("rechnungen", Rechnung, "rechnungen", form=RechnungForm, list_display=("nummer", "typ", "empfaenger_name", "datum",
                    "betrag", "status", "jahr"), suche=("nummer", "empfaenger_name"),
                    filter=("jahr", "status", "typ", "mitglied"), ordering=("-datum", "-id"),
                    kontext=views.rechnung_kontext, nach_speichern=_rechnung_nach_speichern,
                    bearbeitbar=_bearbeitbar_entwurf, loeschbar=_bearbeitbar_entwurf, select_related=("mitglied",),
                    )
urlpatterns += crud("rechnungspositionen", Rechnungsposition, "rechnungen", form=RechnungspositionForm,
                    list_display=("rechnung", "text", "menge", "einzelpreis", "steuersatz"),
                    bearbeitbar=_position_bearbeitbar, loeschbar=_position_bearbeitbar, select_related=("rechnung",))
urlpatterns += crud("zahlungen", Zahlung, "zahlungen", list_display=("datum", "rechnung", "betrag", "art",
                    "ruecklastschrift", "referenz"), select_related=("rechnung",), suche=("rechnung__nummer", "referenz"),
                    filter=("rechnung",), ordering=("-datum", "-id"))
urlpatterns += crud("mahnungen", Mahnung, "rechnungen", list_display=("rechnung", "stufe", "datum", "frist", "gebuehr"),
                    select_related=("rechnung",), kontext=views.mahnung_kontext, add=False)
urlpatterns += crud("bankumsaetze", Bankumsatz, "bank", list_display=("buchungsdatum", "betrag", "gegenkonto_name",
                    "verwendungszweck", "status"), suche=("gegenkonto_name", "verwendungszweck"), filter=("status",),
                    kontext=views.bankumsatz_kontext, listen_aktionen=views.bank_listen_aktionen, delete=False,
                    ordering=("-buchungsdatum", "-id"))
urlpatterns += crud("sepa-einzuege", SepaEinzug, "zahlungen", list_display=("nummer", "faelligkeitsdatum", "anzahl",
                    "summe", "erstellt"), kontext=views.sepa_einzug_kontext,
                    listen_aktionen=views.sepa_einzuege_listen_aktionen, add=False, edit=False, delete=False,
                    ordering=("-erstellt",))
urlpatterns += crud("sepa-einzugspositionen", SepaEinzugPosition, "zahlungen", list_display=("einzug", "mitglied",
                    "rechnung", "betrag", "sequenztyp"), select_related=("einzug", "mitglied", "rechnung"),
                    add=False, edit=False, delete=False)
