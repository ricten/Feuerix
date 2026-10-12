from django.apps import apps as django_apps
from django.contrib.auth.signals import user_logged_in, user_login_failed
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Rolle, Verein
from .rechte import STANDARDROLLEN

MITGLIEDSARTEN = [  # Beispielwerte - im Verein anpassen!
    ("Aktiv", 60), ("Passiv", 60), ("Jugend", 30), ("Kind", 20), ("Familie", 90),
    ("Ehrenmitglied", 0), ("Fördermitglied", 60),
]
EHRUNGSARTEN = ["Vereinsnadel Bronze", "Vereinsnadel Silber", "Vereinsnadel Gold", "25 Jahre", "40 Jahre",
                "50 Jahre", "Ehrenmitglied", "Sonderauszeichnung"]
JUBILAEEN = [10, 20, 25, 30, 40, 50, 60]


@receiver(post_save, sender=Verein)
def verein_angelegt(sender, instance, created, raw=False, **kw):
    """Neuer Mandant: Standardrollen und Beispiel-Stammdaten anlegen."""
    if not created or raw:
        return
    for name, cfg in STANDARDROLLEN.items():
        Rolle.objects.get_or_create(verein=instance, name=name, defaults={
            "ist_superadmin": cfg["ist_superadmin"], "rechte": cfg["rechte"]})
    from .matrix import dso_anlegen
    dso_anlegen(instance)
    Mitgliedsart = django_apps.get_model("members", "Mitgliedsart")
    Ehrungsart = django_apps.get_model("honors", "Ehrungsart")
    Regel = django_apps.get_model("honors", "Jubilaeumsregel")
    for n, betrag in MITGLIEDSARTEN:
        Mitgliedsart.objects.get_or_create(verein=instance, name=n, defaults={"jahresbeitrag": betrag})
    for n in EHRUNGSARTEN:
        Ehrungsart.objects.get_or_create(verein=instance, name=n)
    for j in JUBILAEEN:
        Regel.objects.get_or_create(verein=instance, jahre=j)
    from apps.documents.services import standardordner_anlegen, standardvorlagen_anlegen
    standardordner_anlegen(instance)
    standardvorlagen_anlegen(instance)
    from apps.accounting.services import standardkategorien_anlegen, standardkonten_anlegen
    standardkonten_anlegen(instance)
    standardkategorien_anlegen(instance)


@receiver(user_login_failed)
def login_fehlgeschlagen(sender, credentials=None, **kw):
    """Falsches Passwort: Konto ohne aktive 2FA wird nach 5 Versuchen gesperrt (siehe zweifaktor.py)."""
    from . import zweifaktor
    zweifaktor.passwort_fehlversuch((credentials or {}).get("username"))


@receiver(user_logged_in)
def login_erfolgreich(sender, request=None, user=None, **kw):
    """Fehlversuchszaehler zuruecksetzen; die 2FA-Pruefung der neuen Sitzung steht noch aus."""
    from .models import ZweiFaktor
    ZweiFaktor.objects.filter(user=user).update(fehlversuche=0)
    if request is not None and hasattr(request, "session"):
        request.session["zf_ok"] = False
