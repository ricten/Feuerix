"""Sicherheitstest gegen die laufende TESTINSTANZ (92 Pruefungen zu den Punkten aus docs/SICHERHEITSTEST.md: Mandantentrennung, Rechte, CSRF,
XSS, Dateizugriff, Weiterleitung, Sitzung, Header, Eingaben, Django-Admin, Brute-Force-Schutz). Nur fuer die Testinstanz mit den Konten aus
`manage.py sicherheitstest_vorbereiten`; legt kurzzeitig eigene Testbenutzer/-mitglieder an und entfernt sie wieder.

Aufruf (auf dem Server, im Feuerix-Ordner):
    docker compose exec -T web python manage.py sicherheitstest_vorbereiten --testinstanz | tee /tmp/pt_out.txt
    docker compose cp /tmp/pt_out.txt web:/tmp/pt_out.txt
    docker compose exec -T web python manage.py shell < scripts/sicherheitstest_pruefen.py
Die Ausgabe nennt je Pruefung PASS/FAIL und am Ende die Zusammenfassung."""
import io
from apps.core.models import Verein as _Verein

if _Verein.objects.exclude(kuerzel__in=("pentest-a", "pentest-b")).exists():
    raise SystemExit("Abbruch: Es gibt Vereine ausserhalb des Sicherheitstests - dieses Skript gehoert nur auf eine leere Testinstanz.")
import re
import traceback

import requests
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.urls import reverse

BASE = "http://127.0.0.1:8000"
erg = []


def check(name, ok, detail=""):
    erg.append((name, ok, detail))
    print(("PASS" if ok else "FAIL"), "-", name, ("| " + str(detail)) if detail else "")


def sicher(name, fn):
    try:
        fn()
    except Exception as e:
        check(name + " (Testfehler)", False, f"{type(e).__name__}: {e}")
        traceback.print_exc()


zug, ids = {}, {"A": [], "B": []}
for zeile in open("/tmp/pt_out.txt", encoding="utf-8"):
    t = zeile.split()
    if len(t) > 2 and t[0].startswith("pt_"):
        zug[t[0]] = t[1]
    m = re.match(r"\s+Verein ([AB]): (.*)", zeile)
    if m:
        ids[m.group(1)] = [int(x) for x in re.findall(r"(\d+)", m.group(2).replace("(mit IBAN)", ""))]
A, B = ids["A"], ids["B"]
print("Konten:", sorted(zug), "| Mitglieder A:", A, "B:", B)
U = get_user_model()


def login(user, pw=None, next_=None):
    s = requests.Session()
    s.get(BASE + "/login/")
    data = {"username": user, "password": pw if pw is not None else zug[user], "csrfmiddlewaretoken": s.cookies["csrftoken"]}
    if next_:
        data["next"] = next_
    r = s.post(BASE + "/login/", data=data, allow_redirects=False, headers={"Referer": BASE + "/login/"})
    return s, r


def post(s, url, data=None, **kw):
    d = {"csrfmiddlewaretoken": s.cookies.get("csrftoken", "")}
    d.update(data or {})
    return s.post(BASE + url, data=d, allow_redirects=False, headers={"Referer": BASE + url}, **kw)


def get(s, url, **kw):
    return s.get(BASE + url, allow_redirects=False, **kw)


# --------------------------------------------------------------------------------------------- Anmeldung der Konten
from apps.members.models import Mitglied as _M
_M.objects.filter(nachname__contains="<script>").delete()      # Rest eines frueheren, abgebrochenen Laufs
sessions = {}
for u in zug:
    s, r = login(u)
    ok = r.status_code == 302 and "/login" not in r.headers.get("Location", "")
    check(f"Anmeldung {u}", ok, f"{r.status_code} -> {r.headers.get('Location')}")
    sessions[u] = s


# --------------------------------------------------------------------------------------------- 1. Mandantentrennung
def mandanten():
    for wer, fremd, eigener_marker, fremder_marker in (("pt_admin_b", A, "-B", "-A"), ("pt_admin_a", B, "-A", "-B")):
        s = sessions[wer]
        pk = fremd[1]
        r = post(s, reverse("mitglied_anonymisieren", args=[pk]))
        check(f"Mandant: {wer} POST mitglied_anonymisieren({pk}) fremd", r.status_code in (403, 404), r.status_code)
        for name in ("mitglied_detail", "mitglied_edit", "mitglied_delete", "mitglied_export"):
            r = get(s, reverse(name, args=[pk]))
            ok = r.status_code in (403, 404) and fremder_marker not in r.text
            check(f"Mandant: {wer} ruft {name}({pk}) eines fremden Vereins auf", ok, r.status_code)
        for name in ("mitglied_edit", "mitglied_delete"):
            r = post(s, reverse(name, args=[pk]), {"vorname": "X", "nachname": "Gehackt"})
            check(f"Mandant: {wer} POST {name}({pk}) fremd", r.status_code in (403, 404), r.status_code)
        r = get(s, reverse("mitglied_list"))
        check(f"Mandant: Liste von {wer} zeigt nur eigene Mitglieder", eigener_marker in r.text and fremder_marker not in r.text, r.status_code)
        r = get(s, reverse("mitglieder_export"))
        inhalt = r.content
        gefunden = False
        try:
            import openpyxl
            wb = openpyxl.load_workbook(io.BytesIO(inhalt))
            text = " ".join(str(c.value) for ws in wb for row in ws.iter_rows() for c in row if c.value is not None)
            gefunden = fremder_marker in text
        except Exception:
            gefunden = fremder_marker.encode() in inhalt
        check(f"Mandant: Export von {wer} enthaelt nichts Fremdes", not gefunden and r.status_code in (200, 302, 403), r.status_code)
        r = get(s, reverse("auditlog_list"))
        check(f"Mandant: Aenderungsprotokoll von {wer} ohne fremde Eintraege", fremder_marker not in r.text, r.status_code)


sicher("Mandantentrennung", mandanten)


# --------------------------------------------------------------------------------------------- 2. Rechte (nur lesen)
def rechte():
    s = sessions["pt_lesen_a"]
    check("Rechte: Nur-Lesen darf ansehen", get(s, reverse("mitglied_detail", args=[A[1]])).status_code == 200)
    check("Rechte: Nur-Lesen darf nicht bearbeiten (GET)", get(s, reverse("mitglied_edit", args=[A[1]])).status_code == 403)
    r = post(s, reverse("mitglied_edit", args=[A[1]]), {"vorname": "X", "nachname": "Gehackt"})
    check("Rechte: Nur-Lesen darf nicht speichern (POST)", r.status_code == 403, r.status_code)
    r = post(s, reverse("mitglied_delete", args=[A[1]]))
    check("Rechte: Nur-Lesen darf nicht loeschen (POST)", r.status_code == 403, r.status_code)
    r = post(s, reverse("mitglied_add"), {"vorname": "Neu", "nachname": "Angelegt"})
    check("Rechte: Nur-Lesen darf nichts anlegen", r.status_code == 403, r.status_code)
    from apps.members.models import Mitglied
    check("Rechte: Daten blieben unveraendert", Mitglied.objects.filter(pk=A[1]).exists() and not Mitglied.objects.filter(nachname="Gehackt").exists())
    for name in ("zugang_list", "auditlog_list", "datensicherung", "berechtigungsmatrix", "softwareupdate", "softwareupdate_status"):
        r = get(s, reverse(name))
        check(f"Rechte: Nur-Lesen sieht {name} nicht", r.status_code == 403, r.status_code)
    r = post(s, reverse("softwareupdate_starten"))
    check("Rechte: Nur-Lesen kann kein Update starten", r.status_code == 403, r.status_code)
    # Administrator (kein Superuser) darf keine Systemfunktionen
    sa = sessions["pt_admin_a"]
    for name in ("datensicherung", "softwareupdate", "softwareupdate_status"):
        r = get(sa, reverse(name))
        check(f"Rechte: Verein-Administrator (kein Superuser) sieht {name} nicht", r.status_code == 403, r.status_code)
    r = post(sa, reverse("softwareupdate_starten"))
    check("Rechte: Verein-Administrator kann kein Update starten", r.status_code == 403, r.status_code)
    r = post(sa, reverse("datensicherung_wiederherstellen"), {"db": "db-20990101-000000.sql.gz", "bestaetigung": "WIEDERHERSTELLEN"})
    check("Rechte: Verein-Administrator kann nichts wiederherstellen", r.status_code == 403, r.status_code)


sicher("Rechte", rechte)


# --------------------------------------------------------------------------------------------- 3. Modulgrenzen
def module():
    s = sessions["pt_kasse_a"]
    check("Module: Kassenkonto sieht das Kassenbuch", get(s, reverse("buchung_list")).status_code == 200)
    for name in ("mitglied_list", "auditlog_list", "zugang_list"):
        check(f"Module: Kassenkonto darf {name} nicht", get(s, reverse(name)).status_code == 403)


sicher("Module", module)


# --------------------------------------------------------------------------------------------- 4. CSRF
def csrf():
    from apps.members.models import Mitglied
    s = sessions["pt_admin_a"]
    r = s.post(BASE + reverse("mitglied_delete", args=[A[2]]), data={}, allow_redirects=False, headers={"Referer": BASE + "/"})
    check("CSRF: POST ohne Token wird abgelehnt", r.status_code == 403, r.status_code)
    r = s.post(BASE + reverse("mitglied_delete", args=[A[2]]), data={"csrfmiddlewaretoken": "falsch"}, allow_redirects=False)
    check("CSRF: POST mit falschem Token wird abgelehnt", r.status_code == 403, r.status_code)
    check("CSRF: Mitglied blieb erhalten", Mitglied.objects.filter(pk=A[2]).exists())


sicher("CSRF", csrf)


# --------------------------------------------------------------------------------------------- 5. XSS
def xss():
    from apps.core.models import Verein
    from apps.members.models import Mitglied
    va = Verein.objects.get(kuerzel="pentest-a")
    m = Mitglied.objects.create(verein=va, vorname="<img src=x onerror=alert(1)>", nachname='"><script>alert(1)</script>-A',
                                notizen="<script>alert('notiz')</script>")
    s = sessions["pt_admin_a"]
    for name, args in (("mitglied_list", []), ("mitglied_detail", [m.pk]), ("mitglied_edit", [m.pk]), ("auditlog_list", [])):
        r = get(s, reverse(name, args=args))
        roh = "<script>alert(1)</script>" in r.text or "<img src=x onerror=" in r.text or "<script>alert('notiz')" in r.text
        check(f"XSS: {name} gibt Eingaben maskiert aus", r.status_code == 200 and not roh and "&lt;" in r.text, r.status_code)
    r = get(s, reverse("mitglied_list") + "?q=%3Cscript%3Ealert(1)%3C/script%3E")
    check("XSS: Suchbegriff wird maskiert gespiegelt", "<script>alert(1)</script>" not in r.text, r.status_code)
    m.delete()


sicher("XSS", xss)


# --------------------------------------------------------------------------------------------- 6. Dateien und Pfade
def dateien():
    anon = requests.Session()
    for pfad in ("/datei/members/mitglied/1/foto/", "/mitglieder/", "/verwaltung/datensicherung/"):
        r = anon.get(BASE + pfad, allow_redirects=False)
        check(f"Zugriff: {pfad} ohne Anmeldung -> Login", r.status_code in (301, 302) and "login" in r.headers.get("Location", ""), r.status_code)
    for pfad in ("/media/", "/media/x", "/.env", "/manage.py", "/config/settings.py", "/update/status.json", "/.git/config"):
        r = anon.get(BASE + pfad, allow_redirects=False)
        check(f"Zugriff: {pfad} nicht abrufbar", r.status_code in (301, 302, 403, 404) and "SECRET_KEY" not in r.text, r.status_code)
    s = sessions["pt_admin_a"]
    r = get(s, "/datei/members/mitglied/%d/foto/" % B[0])
    check("Zugriff: fremde Datei ueber /datei/ nicht abrufbar", r.status_code in (403, 404), r.status_code)
    r = get(s, "/datei/members/mitglied/%d/iban/" % A[0])
    check("Zugriff: Nicht-Datei-Feld (IBAN) ueber /datei/ nicht abrufbar", r.status_code in (403, 404), r.status_code)


sicher("Dateien", dateien)


# --------------------------------------------------------------------------------------------- 7. Weiterleitung nach Anmeldung
def weiterleitung():
    for ziel in ("https://example.org/", "//example.org/", "https:example.org", "/\\example.org"):
        s, r = login("pt_admin_a", next_=ziel)
        loc = r.headers.get("Location", "")
        extern = "example.org" in loc
        check(f"Open Redirect: next={ziel!r} wird nicht extern verfolgt", r.status_code == 302 and not extern, loc)


sicher("Weiterleitung", weiterleitung)


# --------------------------------------------------------------------------------------------- 8. Sitzung
def sitzung():
    s, r = login("pt_admin_a")
    alt = s.cookies.get("sessionid")
    r = post(s, "/logout/")
    check("Sitzung: Abmelden per POST", r.status_code in (200, 302), r.status_code)
    neu = requests.Session()
    neu.cookies.set("sessionid", alt)
    r = get(neu, reverse("mitglied_list"))
    check("Sitzung: alte Sitzung nach Abmeldung ungueltig", r.status_code in (301, 302) and "login" in r.headers.get("Location", ""), r.status_code)
    r = requests.get(BASE + "/logout/", allow_redirects=False)
    check("Sitzung: Abmelden per GET nicht moeglich/ohne Wirkung", r.status_code in (302, 405), r.status_code)


sicher("Sitzung", sitzung)


# --------------------------------------------------------------------------------------------- 9. Header und Cookies
def header():
    r = requests.get(BASE + "/login/")
    h = r.headers
    check("Header: X-Frame-Options", h.get("X-Frame-Options", "").upper() in ("DENY", "SAMEORIGIN"), h.get("X-Frame-Options"))
    check("Header: X-Content-Type-Options nosniff", h.get("X-Content-Type-Options") == "nosniff", h.get("X-Content-Type-Options"))
    print("INFO - Referrer-Policy:", h.get("Referrer-Policy"), "| Content-Security-Policy:", h.get("Content-Security-Policy"),
          "| Cross-Origin-Opener-Policy:", h.get("Cross-Origin-Opener-Policy"), "| Server:", h.get("Server"))
    for c in r.raw.headers.getlist("Set-Cookie"):
        print("INFO - Cookie:", re.sub(r"=[^;]+", "=<wert>", c, count=1))
    r = requests.get(BASE + "/gibt-es-nicht-xyz/")
    check("Fehlerseite verraet keine Debug-Informationen", r.status_code == 404 and "URLconf" not in r.text and "DEBUG" not in r.text, r.status_code)


sicher("Header", header)


# --------------------------------------------------------------------------------------------- 10. Eingaben (SQL-Injection u. a.)
def eingaben():
    s = sessions["pt_admin_a"]
    for q in ("'", "' OR 1=1 --", '"; DROP TABLE members_mitglied; --', "%00", "a" * 5000, "\\"):
        r = get(s, reverse("mitglied_list"), params={"q": q})
        check(f"Eingabe: Suche mit {q[:20]!r} fuehrt nicht zu 5xx", r.status_code < 500, r.status_code)
    for p in ({"o": "__import__"}, {"o": "-999"}, {"page": "abc"}, {"page": "-1"}, {"status": "' or 1=1"}):
        r = get(s, reverse("mitglied_list"), params=p)
        check(f"Eingabe: Parameter {p} fuehrt nicht zu 5xx", r.status_code < 500, r.status_code)
    from apps.members.models import Mitglied
    check("Eingabe: Tabelle noch vorhanden", Mitglied.objects.count() >= 6)


sicher("Eingaben", eingaben)


# --------------------------------------------------------------------------------------------- 11. Django-Admin
def djadmin():
    r = requests.get(BASE + "/admin/", allow_redirects=False)
    check("Django-Admin: ohne Anmeldung nur Login", r.status_code in (301, 302) and "login" in r.headers.get("Location", ""), r.status_code)
    s = sessions["pt_admin_a"]
    r = get(s, "/admin/")
    check("Django-Admin: normaler Benutzer ohne Zugriff", r.status_code in (301, 302, 403, 404) and "Site administration" not in r.text and "Verwaltung" != r.text[:0], r.status_code)


sicher("DjangoAdmin", djadmin)


# --------------------------------------------------------------------------------------------- 12. Brute-Force-Schutz (zuletzt, entsperrt danach)
def brute():
    call_command("axes_reset")
    for kuerzel in ("pt_opfer1", "pt_opfer2"):
        U.objects.filter(username=kuerzel).delete()
        U.objects.create_user(kuerzel, f"{kuerzel}@example.invalid", "Richtig-Passwort-12345")
    # a) Anmeldeseite
    status = []
    for i in range(8):
        s, r = login("pt_opfer1", pw="falsch-%d" % i)
        status.append(r.status_code)
    s, r = login("pt_opfer1", pw="Richtig-Passwort-12345")
    gesperrt = not (r.status_code == 302 and "/login" not in r.headers.get("Location", ""))
    check("Brute-Force: Anmeldeseite sperrt nach Fehlversuchen (auch das richtige Passwort wird dann abgelehnt)", gesperrt,
          f"Statuscodes {status}, danach richtiges Passwort -> {r.status_code}")
    # b) Django-Admin-Anmeldung
    status = []
    for i in range(8):
        sx = requests.Session()
        sx.get(BASE + "/admin/login/")
        r = sx.post(BASE + "/admin/login/", data={"username": "pt_opfer2", "password": "falsch-%d" % i, "csrfmiddlewaretoken": sx.cookies.get("csrftoken", ""),
                                                   "next": "/admin/"}, allow_redirects=False, headers={"Referer": BASE + "/admin/login/"})
        status.append(r.status_code)
    sx = requests.Session()
    sx.get(BASE + "/login/")
    s2, r2 = login("pt_opfer2", pw="Richtig-Passwort-12345")
    check("Brute-Force: auch /admin/login/ zaehlt Fehlversuche (Konto danach gesperrt)", not (r2.status_code == 302 and "/login" not in r2.headers.get("Location", "")),
          f"Statuscodes {status}, danach richtiges Passwort -> {r2.status_code}")
    # Aufraeumen: entsperren
    call_command("axes_reset")
    for kuerzel in ("pt_opfer1", "pt_opfer2"):
        U.objects.filter(username=kuerzel).delete()


sicher("BruteForce", brute)

fehler = [e for e in erg if not e[1]]
print()
print(f"=== {len(erg)} Pruefungen, {len(erg) - len(fehler)} bestanden, {len(fehler)} fehlgeschlagen ===")
for n, ok, d in fehler:
    print("FEHLGESCHLAGEN:", n, "|", d)
