from django.urls import path

from apps.core.crud import crud

from . import views
from .models import Aufwandsentschaedigung

urlpatterns = [
    path("aufwand/uebersicht/", views.aufwand_uebersicht, name="aufwand_uebersicht"),
    path("aufwand/<int:pk>/status/", views.aufwand_status, name="aufwand_status"),
    path("aufwand/<int:pk>/verzicht/", views.aufwand_verzicht, name="aufwand_verzicht"),
]
urlpatterns += crud("aufwand", Aufwandsentschaedigung, "aufwand", list_display=("datum", "empfaenger", "art", "betrag",
                    "status"), select_related=("empfaenger",), filter=("art", "status", "empfaenger"),
                    suche=("empfaenger__nachname", "taetigkeit"), kontext=views.aufwand_kontext,
                    nach_speichern=views.nach_speichern, listen_aktionen=views.listen_aktionen,
                    bearbeitbar=lambda a: a.status in ("beantragt", "genehmigt"),
                    loeschbar=lambda a: a.status in ("beantragt", "abgelehnt"), ordering=("-datum", "-id"))
