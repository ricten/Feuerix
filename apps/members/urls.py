from django.urls import path

from apps.core.crud import crud, knopf

from . import views
from .models import Abteilung, Dokument, Familie, Funktion, Mitglied, MitgliedFunktion, Mitgliedsart

urlpatterns = [
    path("mitglieder/import/", views.mitglieder_import, name="mitglieder_import"),
    path("mitglieder/import/vorlage/", views.mitglieder_import_vorlage, name="mitglieder_import_vorlage"),
    path("mitglieder/export/", views.mitglieder_export, name="mitglieder_export"),
    path("mitglieder/<int:pk>/auskunft/", views.mitglied_export, name="mitglied_export"),
    path("mitglieder/<int:pk>/anonymisieren/", views.mitglied_anonymisieren, name="mitglied_anonymisieren"),
]
def mitglieder_listen_aktionen(request):
    from django.urls import reverse
    a = []
    if request.rechte.darf("mitglieder", "add"):
        a.append(knopf("Import (Excel/CSV)", reverse("mitglieder_import"), stil="outline-primary"))
    a.append(knopf("Vollexport (Excel)", reverse("mitglieder_export")))
    if request.rechte.darf("beitraege", "view"):
        a.append(knopf("Vollexport mit Bankdaten", reverse("mitglieder_export") + "?bank=1"))
    return a


urlpatterns += crud(
    "mitglieder", Mitglied, "mitglieder", listen_aktionen=mitglieder_listen_aktionen,
    list_display=("mitgliedsnummer", "nachname", "vorname", "mitgliedsart", "status", "eintrittsdatum", "ort"),
    suche=("nachname", "vorname", "email", "ort", "mitgliedsnummer"), filter=("status", "mitgliedsart", "familie"),
    select_related=("mitgliedsart",), ordering=("nachname", "vorname"), kontext=views.mitglied_kontext,
    detail_ausblenden=("openslides_initialpasswort",))
urlpatterns += crud("mitgliedsarten", Mitgliedsart, "beitraege", list_display=("name", "jahresbeitrag", "beschreibung"))
urlpatterns += crud("familien", Familie, "mitglieder", list_display=("name",))
urlpatterns += crud("abteilungen", Abteilung, "mitglieder", list_display=("name",))
urlpatterns += crud("funktionen", Funktion, "mitglieder", list_display=("name",))
urlpatterns += crud("mitglied-funktionen", MitgliedFunktion, "mitglieder",
                    list_display=("mitglied", "funktion", "von", "bis"), select_related=("mitglied", "funktion"))
urlpatterns += crud("dokumente", Dokument, "dokumente", edit=False,
                    list_display=("mitglied", "titel", "version", "kategorie", "erstellt"),
                    select_related=("mitglied",), suche=("titel", "mitglied__nachname"), filter=("mitglied", "kategorie"))
