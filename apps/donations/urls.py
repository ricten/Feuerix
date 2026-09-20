from django.urls import path

from apps.core.crud import crud

from . import views
from .models import Spende, Zuwendungsbestaetigung

urlpatterns = [
    path("spenden/sammelbestaetigungen/", views.quittung_sammel, name="quittung_sammel"),
    path("spenden/<int:pk>/einzelbestaetigung/", views.spende_einzelbestaetigung, name="spende_einzelbestaetigung"),
    path("spendenquittungen/<int:pk>/pdf/", views.bestaetigung_pdf, name="zuwendungsbestaetigung_pdf"),
    path("spendenquittungen/<int:pk>/ausstellen/", views.bestaetigung_ausstellen, name="zuwendungsbestaetigung_ausstellen"),
    path("spendenquittungen/<int:pk>/stornieren/", views.bestaetigung_stornieren, name="zuwendungsbestaetigung_stornieren"),
]
urlpatterns += crud("spenden", Spende, "spenden", list_display=("datum", ("name_des_spenders", "Spender"), "art",
                    "betrag", "bestaetigung"), suche=("spender_name", "spender__nachname", "zweck"),
                    filter=("art", "spender"), select_related=("spender", "bestaetigung"), kontext=views.spende_kontext,
                    listen_aktionen=views.spenden_listen_aktionen, ordering=("-datum", "-id"),
                    loeschbar=lambda s: s.bestaetigung_id is None)
urlpatterns += crud("spendenquittungen", Zuwendungsbestaetigung, "spenden", list_display=("nummer", "spender_name",
                    "art", "betrag", "datum_bis", "status"), filter=("status", "typ"), suche=("nummer", "spender_name"),
                    kontext=views.bestaetigung_kontext, bearbeitbar=lambda b: b.status == "entwurf",
                    loeschbar=lambda b: b.status == "entwurf", ordering=("-datum_bis", "-id"))
