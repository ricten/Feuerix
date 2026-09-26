from django.urls import path, reverse

from apps.core.crud import abschnitt, crud, knopf

from . import views
from .forms import AblageForm, SchriftstueckForm, SerienbriefForm, VorlageForm
from .models import Ablagedokument, Ordner, Schriftstueck, Serienbrief, Vorlage


def ablage_kontext(request, d):
    from apps.paperless.models import PaperlessVerbindung
    a = []
    if d.datei:
        a.append(knopf("Herunterladen", reverse("datei", args=["documents", "ablagedokument", d.pk, "datei"]), stil="primary"))
    if request.rechte.darf("ablage", "add"):
        a.append(knopf("Neue Version hochladen", reverse("ablagedokument_add") + f"?titel={d.titel}&kategorie={d.kategorie}"
                       + (f"&ordner={d.ordner_id}" if d.ordner_id else "")))
    verbindung = PaperlessVerbindung.objects.filter(verein=request.verein, aktiv=True).first()
    if d.datei and verbindung and request.rechte.darf("ablage", "change"):
        if d.paperless_status in ("wartet", "sendet", "uebergeben"):
            pass  # Übergabe läuft - keine Doppelklicks; der Status wird live angezeigt
        elif not d.paperless_uebergeben:
            a.append(knopf("An Paperless senden", reverse("ablagedokument_paperless_senden", args=[d.pk]), post=True))
        else:
            a.append(knopf("Erneut an Paperless senden", reverse("ablagedokument_paperless_senden", args=[d.pk]),
                           post=True, felder={"erneut": "1"},
                           bestaetigung="Diese Datei wurde bereits übergeben. Wirklich erneut senden? "
                                        "Paperless kann Duplikate ablehnen."))
    frueher = Ablagedokument.objects.filter(verein=request.verein, ordner=d.ordner, titel=d.titel).exclude(pk=d.pk)
    live = reverse("ablagedokument_paperless_status", args=[d.pk]) if d.paperless_status else ""
    return {"aktionen": a, "live_status_url": live, "abschnitte": [abschnitt(request, "Weitere Versionen", frueher.order_by("-version"),
                                                    ("titel", "version", "datum"))] if frueher.exists() else []}


def ablage_listen_aktionen(request):
    from apps.paperless.models import PaperlessVerbindung
    a = []
    if request.rechte.darf("ablage", "change") and PaperlessVerbindung.objects.filter(
            verein=request.verein, aktiv=True).exists():
        a.append(knopf("Sammelversand an Paperless", reverse("ablage_paperless_sammelversand")))
    return a


urlpatterns = [
    path("vorlagen/standard/", views.vorlagen_standard, name="vorlagen_standard"),
    path("platzhalter/", views.platzhalter_hilfe, name="platzhalter_hilfe"),
    path("schriftstuecke/<int:pk>/pdf/", views.schriftstueck_pdf_view, name="schriftstueck_pdf"),
    path("schriftstuecke/<int:pk>/word/", views.schriftstueck_docx_view, name="schriftstueck_docx"),
    path("schriftstuecke/<int:pk>/ablegen/", views.schriftstueck_ablegen, name="schriftstueck_ablegen"),
    path("serienbriefe/<int:pk>/pdf/", views.serienbrief_pdf_view, name="serienbrief_pdf"),
    path("serienbriefe/<int:pk>/ablegen/", views.serienbrief_ablegen, name="serienbrief_ablegen"),
    path("serienbriefe/<int:pk>/mailen/", views.serienbrief_mailen, name="serienbrief_mailen"),
    path("veranstaltungen/<int:pk>/schriftstueck/<str:art>/", views.aus_veranstaltung, name="veranstaltung_schriftstueck"),
]
urlpatterns += crud("schriftstuecke", Schriftstueck, "schriftverkehr", form=SchriftstueckForm,
                    list_display=("datum", "titel", "art", "veranstaltung", "status"), select_related=("veranstaltung",),
                    suche=("titel", "betreff"), filter=("art", "status", "veranstaltung"), kontext=views.schriftstueck_kontext,
                    ordering=("-datum", "-id"), detail_ausblenden=())
urlpatterns += crud("serienbriefe", Serienbrief, "schriftverkehr", form=SerienbriefForm,
                    list_display=("datum", "titel", "status_filter", "veranstaltung", "versendet_am"),
                    select_related=("veranstaltung",), suche=("titel",), kontext=views.serienbrief_kontext,
                    ordering=("-datum", "-id"))
urlpatterns += crud("vorlagen", Vorlage, "schriftverkehr", form=VorlageForm,
                    list_display=("name", "art", "ist_standard", "aktiv"), suche=("name", "betreff"), filter=("art",),
                    listen_aktionen=views.vorlagen_listen_aktionen, ordering=("art", "name"))
urlpatterns += crud("ablage", Ablagedokument, "ablage", form=AblageForm,
                    list_display=("datum", "titel", "kategorie", "tags", "ordner", "version", ("dateiname", "Datei"),
                                 ("paperless_uebergeben", "Paperless")),
                    select_related=("ordner",), suche=("titel", "beschreibung"), filter=("kategorie", "ordner", "veranstaltung"),
                    kontext=ablage_kontext, listen_aktionen=ablage_listen_aktionen, ordering=("-datum", "-id"),
                    detail_ausblenden=("paperless_task_id", "paperless_pruefsumme", "paperless_status"))
urlpatterns += crud("ablage-ordner", Ordner, "ablage", list_display=(("pfad", "Ordner"),), select_related=("uebergeordnet",),
                    ordering=("name",))
