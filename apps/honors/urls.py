from django.urls import path

from apps.core.crud import crud

from . import views
from .models import Ehrung, Ehrungsart, Jubilaeumsregel

urlpatterns = [path("jubilaeen/", views.jubilaeen, name="jubilaeen")]
urlpatterns += crud("ehrungen", Ehrung, "ehrungen", list_display=("mitglied", "art", "datum", "anlass", "verliehen_durch"),
                    select_related=("mitglied", "art"), suche=("mitglied__nachname", "anlass", "art__name"),
                    filter=("mitglied", "art"), ordering=("-datum",))
urlpatterns += crud("ehrungsarten", Ehrungsart, "ehrungen", list_display=("name", "beschreibung"))
urlpatterns += crud("jubilaeumsregeln", Jubilaeumsregel, "ehrungen", list_display=("jahre", "bezeichnung", "aktiv"),
                    ordering=("jahre",))
