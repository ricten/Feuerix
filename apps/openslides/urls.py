from django.urls import path

from . import views

urlpatterns = [
    path("openslides/", views.einstellungen, name="openslides_einstellungen"),
    path("openslides/test/", views.test, name="openslides_test"),
    path("openslides/abgleich/", views.abgleich, name="openslides_abgleich"),
    path("openslides/passwoerter-loeschen/", views.passwoerter_loeschen, name="openslides_passwoerter_loeschen"),
    path("veranstaltungen/<int:pk>/openslides/", views.veranstaltung_meeting, name="veranstaltung_openslides"),
    path("veranstaltungen/<int:pk>/openslides/wahlergebnisse/", views.veranstaltung_wahlergebnisse,
        name="veranstaltung_wahlergebnisse"),
]
