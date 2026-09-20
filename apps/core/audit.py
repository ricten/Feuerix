"""Automatische, vollstaendige Aenderungshistorie (wer, wann, alt -> neu, IP, Grund)."""
from contextvars import ContextVar

from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from .models import AuditLog, Verein

kontext_var = ContextVar("audit_kontext", default=None)


def kontext_setzen(**kw):
    k = kontext_var.get()
    if k is not None:
        k.update(kw)


def _verein_id(o):
    return o.pk if isinstance(o, Verein) else getattr(o, "verein_id", None)


def _snapshot(o):
    out = {}
    maske = getattr(o, "AUDIT_MASK", ())
    for f in o._meta.concrete_fields:
        if f.name in ("erstellt", "geaendert"):
            continue
        v = getattr(o, f.attname)
        if v is None or v == "":
            out[str(f.verbose_name)] = None
        elif f.name in maske:
            out[str(f.verbose_name)] = "***"
        else:
            out[str(f.verbose_name)] = str(v)
    return out


def _schreiben(instance, aktion, diff):
    k = kontext_var.get() or {}
    user = k.get("user")
    ist_user = user is not None and getattr(user, "is_authenticated", False)
    AuditLog.objects.create(
        verein_id=_verein_id(instance),
        user_id=user.pk if ist_user else None,
        user_name=user.get_username() if ist_user else "System",
        ip=k.get("ip"),
        modell=str(instance._meta.verbose_name),
        objekt_id=str(instance.pk),
        objekt_repr=str(instance)[:200],
        aktion=aktion,
        aenderungen=diff,
        grund=(k.get("grund") or "")[:200],
    )


@receiver(pre_save)
def _vor_speichern(sender, instance, raw=False, **kw):
    if raw or not getattr(instance, "AUDIT", False):
        return
    instance._audit_alt = None
    if instance.pk:
        alt = sender._base_manager.filter(pk=instance.pk).first()
        if alt is not None:
            instance._audit_alt = _snapshot(alt)


@receiver(post_save)
def _nach_speichern(sender, instance, created, raw=False, **kw):
    if raw or not getattr(instance, "AUDIT", False):
        return
    neu = _snapshot(instance)
    if created:
        _schreiben(instance, "angelegt", {k: [None, v] for k, v in neu.items() if v is not None})
        return
    alt = getattr(instance, "_audit_alt", None) or {}
    diff = {k: [alt.get(k), v] for k, v in neu.items() if alt.get(k) != v}
    if diff:
        _schreiben(instance, "geaendert", diff)


@receiver(post_delete)
def _nach_loeschen(sender, instance, **kw):
    if not getattr(instance, "AUDIT", False):
        return
    _schreiben(instance, "geloescht", {k: [v, None] for k, v in _snapshot(instance).items() if v is not None})
