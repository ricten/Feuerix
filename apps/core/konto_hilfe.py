"""Hilfe für Benutzer, die nicht mehr in ihr Konto kommen: Passwort vergessen (Link per E-Mail) und die Anfrage an die
Administration, die Zwei-Faktor-Anmeldung zurückzusetzen. Beides ist ohne Anmeldung erreichbar und verrät nie, ob ein Konto
existiert."""
import logging

from django import forms
from axes.helpers import get_client_ip_address
from django.contrib.auth import get_user_model
from django.contrib.auth import views as auth_views
from django.core.cache import cache
from django.core.mail import EmailMessage
from django.conf import settings
from django.shortcuts import redirect, render
from django.urls import reverse, reverse_lazy
from django.utils.translation import gettext, gettext_lazy as _
from django.views.decorators.http import require_http_methods

from . import passwortabgleich, zweifaktor
from .models import Zugang, ZweiFaktorAnfrage

log = logging.getLogger(__name__)

# Beide Seiten sind ohne Anmeldung erreichbar und loesen Mails aus (an Benutzer bzw. Administration): je IP-Adresse
# nur wenige Anfragen pro Stunde, damit sie nicht zum Mail-Fluten oder Abtasten von Benutzernamen taugen.
ANFRAGEN_JE_STUNDE = 5


def zu_viele_anfragen(request, bereich):
    """Zaehlt eine POST-Anfrage je IP und Bereich; True, wenn das Limit ueberschritten ist (dann nichts tun, aber
    genauso antworten wie sonst - der Aufrufer verraet nichts)."""
    schluessel = f"konto_hilfe:{bereich}:{get_client_ip_address(request)}"
    try:
        cache.add(schluessel, 0, 3600)
        return cache.incr(schluessel) > ANFRAGEN_JE_STUNDE
    except ValueError:      # Eintrag zwischenzeitlich abgelaufen
        cache.set(schluessel, 1, 3600)
        return False
    except Exception:       # Cache (Redis) nicht erreichbar: die Seite bleibt benutzbar, nur ohne Ratenlimit
        log.warning("Ratenlimit der Anmeldehilfe nicht pruefbar (Cache nicht erreichbar)", exc_info=True)
        return False


class PasswortVergessenView(auth_views.PasswordResetView):
    """Formular für die E-Mail-Adresse; Django verschickt den Link nur an aktive Konten mit passender Adresse."""
    template_name = "registration/passwort_vergessen.html"
    email_template_name = "registration/passwort_reset_email.txt"
    subject_template_name = "registration/passwort_reset_betreff.txt"
    success_url = reverse_lazy("passwort_vergessen_gesendet")

    def form_valid(self, form):
        if zu_viele_anfragen(self.request, "passwort"):
            return redirect(self.success_url)      # wie erfolgreich, aber ohne Mail
        return super().form_valid(form)


class PasswortNeuView(auth_views.PasswordResetConfirmView):
    """Neues Passwort über den Link aus der E-Mail; bei eingeschaltetem Passwort-Abgleich auch in Paperless/OpenSlides."""
    template_name = "registration/passwort_neu.html"
    success_url = reverse_lazy("passwort_neu_fertig")

    def form_valid(self, form):
        antwort = super().form_valid(form)
        zweifaktor.entsperren(form.user)      # Fehlversuchszähler zurücksetzen (gesperrte Konten bekommen gar keinen Link)
        passwortabgleich.melden(self.request, passwortabgleich.abgleichen(form.user, form.cleaned_data["new_password1"]))
        return antwort


class ZfAnfrageForm(forms.Form):
    benutzername = forms.CharField(label=_("Benutzername"), max_length=150)
    nachricht = forms.CharField(label=_("Nachricht an die Administration (optional)"), max_length=300, required=False,
                                widget=forms.Textarea(attrs={"rows": 3}),
                                help_text=_("Z. B. wie die Administration Sie erreicht oder woran sie Sie erkennt."))


def _admins_benachrichtigen(anfrage):
    """Mail an alle aktiven Superadministratoren mit E-Mail-Adresse; Fehler beim Versand dürfen die Anfrage nie verhindern."""
    empfaenger = list(get_user_model().objects.filter(is_superuser=True, is_active=True).exclude(email="")
                      .values_list("email", flat=True))
    if not empfaenger:
        return
    z = Zugang.objects.filter(user=anfrage.user).first()
    link = reverse("zugang_detail", args=[z.pk]) if z else reverse("zugang_list")
    text = (f"Für das Konto \"{anfrage.user.get_username()}\" wurde angefragt, die Zwei-Faktor-Anmeldung zurückzusetzen.\n\n"
            f"Nachricht: {anfrage.nachricht or '-'}\n\n"
            "Bitte vor dem Zurücksetzen sicherstellen, dass wirklich diese Person fragt (z. B. Rückruf unter bekannter Nummer). "
            "Zurücksetzen: Einstellungen › Benutzer › Konto › \"2FA zurücksetzen\"\n"
            f"{link}\n")
    try:
        EmailMessage(subject=f"Feuerix: Anfrage 2FA zurücksetzen ({anfrage.user.get_username()})", body=text,
                     from_email=settings.DEFAULT_FROM_EMAIL, to=empfaenger).send()
    except Exception:
        log.warning("Benachrichtigung zur 2FA-Anfrage nicht gesendet", exc_info=True)


def anfragen(benutzername, nachricht=""):
    """Legt eine offene Anfrage an (höchstens eine je Konto). None, wenn es das Konto nicht gibt, es keine aktive 2FA hat oder
    schon eine Anfrage offen ist - der Aufrufer verrät das nicht."""
    U = get_user_model()
    user = U.objects.filter(**{U.USERNAME_FIELD: (benutzername or "").strip()}).first()
    if user is None or not zweifaktor.ist_aktiv(user):
        return None
    if ZweiFaktorAnfrage.objects.filter(user=user, erledigt_am__isnull=True).exists():
        return None
    anfrage = ZweiFaktorAnfrage.objects.create(user=user, nachricht=(nachricht or "").strip()[:300])
    _admins_benachrichtigen(anfrage)
    return anfrage


@require_http_methods(["GET", "POST"])
def zf_anfrage(request):
    form = ZfAnfrageForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        if not zu_viele_anfragen(request, "zf"):
            anfragen(form.cleaned_data["benutzername"], form.cleaned_data["nachricht"])
        return redirect("zf_anfrage_fertig")
    return render(request, "registration/zf_anfrage.html", {"form": form, "titel": gettext("2FA zurücksetzen anfragen")})


def zf_anfrage_fertig(request):
    return render(request, "registration/zf_anfrage_fertig.html")
