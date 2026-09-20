import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils.text import slugify

from apps.core.models import Rolle, Verein, Zugang


class Command(BaseCommand):
    help = "Legt beim ersten Start Administrator und ersten Verein aus den Umgebungsvariablen an."

    def handle(self, *args, **opts):
        User = get_user_model()
        name, pw = os.environ.get("ADMIN_USER"), os.environ.get("ADMIN_PASSWORD")
        if name and pw and not User.objects.exists():
            User.objects.create_superuser(name, os.environ.get("ADMIN_EMAIL", ""), pw)
            self.stdout.write(f"Administrator '{name}' angelegt.")
        # Nach Updates: fehlende Standardrollen und (nur bei leerem Bestand) Konten/Kategorien ergänzen
        from apps.accounting.models import Buchungskategorie, Konto
        from apps.accounting.services import standardkategorien_anlegen, standardkonten_anlegen
        from apps.core.rechte import STANDARDROLLEN
        for v in Verein.objects.all():
            for rname, cfg in STANDARDROLLEN.items():
                Rolle.objects.get_or_create(verein=v, name=rname, defaults={
                    "ist_superadmin": cfg["ist_superadmin"], "rechte": cfg["rechte"]})
            if not Konto.objects.filter(verein=v).exists():
                standardkonten_anlegen(v)
            if not Buchungskategorie.objects.filter(verein=v).exists():
                standardkategorien_anlegen(v)
        vn = os.environ.get("VEREIN_NAME")
        if vn and not Verein.objects.exists():
            v = Verein.objects.create(name=vn, kuerzel=slugify(vn)[:50] or "verein")
            admin = User.objects.filter(is_superuser=True).first()
            if admin:
                Zugang.objects.create(verein=v, user=admin, rolle=Rolle.objects.get(verein=v, name="Superadministrator"))
            self.stdout.write(f"Verein '{vn}' angelegt.")
