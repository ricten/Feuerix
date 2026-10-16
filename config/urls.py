from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from django.views.generic import TemplateView

from apps.core import konto_hilfe
from apps.core.views import PasswortAendernView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("i18n/", include("django.conf.urls.i18n")),
    path("login/", auth_views.LoginView.as_view(), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("passwort/", PasswortAendernView.as_view(success_url="/nach-anmeldung/"), name="password_change"),
    path("passwort-vergessen/", konto_hilfe.PasswortVergessenView.as_view(), name="passwort_vergessen"),
    path("passwort-vergessen/gesendet/", TemplateView.as_view(template_name="registration/passwort_vergessen_gesendet.html"),
         name="passwort_vergessen_gesendet"),
    path("passwort-neu/<uidb64>/<token>/", konto_hilfe.PasswortNeuView.as_view(), name="passwort_neu"),
    path("passwort-neu/fertig/", TemplateView.as_view(template_name="registration/passwort_neu_fertig.html"),
         name="passwort_neu_fertig"),
    path("zwei-faktor/anfrage/", konto_hilfe.zf_anfrage, name="zf_anfrage"),
    path("zwei-faktor/anfrage/gesendet/", konto_hilfe.zf_anfrage_fertig, name="zf_anfrage_fertig"),
    path("", include("apps.core.urls")),
    path("", include("apps.members.urls")),
    path("", include("apps.honors.urls")),
    path("", include("apps.finance.urls")),
    path("", include("apps.inventory.urls")),
    path("", include("apps.donations.urls")),
    path("", include("apps.allowances.urls")),
    path("", include("apps.events.urls")),
    path("", include("apps.documents.urls")),
    path("", include("apps.openslides.urls")),
    path("", include("apps.paperless.urls")),
    path("", include("apps.accounting.urls")),
]
