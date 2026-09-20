from celery import shared_task
from django.conf import settings
from django.core.mail import EmailMessage
from django.utils import timezone

from .models import Serienbrief
from .pdf import absaetze, serienbrief_einzel
from .platzhalter import ersetzen, kontext


@shared_task
def serienbrief_mailen_task(serienbrief_id):
    sb = Serienbrief.objects.select_related("verein", "veranstaltung").get(pk=serienbrief_id)
    ok = fehler = ohne = 0
    for m in sb.empfaenger():
        if not m.email:
            ohne += 1
            continue
        ctx = kontext(sb.verein, mitglied=m, veranstaltung=sb.veranstaltung, datum=sb.datum)
        try:
            mail = EmailMessage(subject=ersetzen(sb.betreff or sb.titel, ctx),
                                body=ersetzen(sb.text, ctx), from_email=settings.DEFAULT_FROM_EMAIL, to=[m.email],
                                reply_to=[sb.verein.email] if sb.verein.email else None)
            mail.attach(f"{sb.titel[:40]}.pdf", serienbrief_einzel(sb, m), "application/pdf")
            mail.send()
            ok += 1
        except Exception:
            fehler += 1
    sb.versendet_am = timezone.now()
    sb.versand_info = f"{ok} versendet, {fehler} Fehler, {ohne} ohne E-Mail-Adresse (nur Brief)"
    sb.save(update_fields=["versendet_am", "versand_info", "geaendert"])
