from django.urls import path

from . import views

urlpatterns = [
    path("paperless/", views.einstellungen, name="paperless_einstellungen"),
    path("paperless/test/", views.test, name="paperless_test"),
    path("ablage/paperless/sammelversand/", views.sammelversand, name="ablage_paperless_sammelversand"),
    path("ablage/<int:pk>/paperless/status/", views.dokument_status, name="ablagedokument_paperless_status"),
    path("ablage/<int:pk>/paperless/", views.dokument_senden, name="ablagedokument_paperless_senden"),
]
