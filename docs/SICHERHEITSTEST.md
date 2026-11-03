# Anleitung: Sicherheitstest auf einer Test-VM

Diese Anleitung beschreibt, wie man Feuerix auf einer eigenen VM (Linux mit Docker) für einen Sicherheitstest aufsetzt und mit
OWASP ZAP und einem Intercepting-Proxy (ZAP-Desktop oder Burp) prüft. Getestet wird **nie die Produktivinstanz** und nie mit
echten Daten.

## 1. Regeln für die Test-VM

* Eigene VM, nur aus dem eigenen Netz erreichbar (nicht aus dem Internet).
* Keine Zugangsdaten zur Produktion: keine Datenbankkopie, kein FinTS-, SMTP-, Paperless- oder OpenSlides-Zugang. Ein aktiver
  Scan löst sonst echte Mails und Abrufe aus. `EMAIL_HOST` in der `.env` bleibt leer.
* Eigene, frisch erzeugte Schlüssel (`SECRET_KEY`, `FIELD_ENCRYPTION_KEY`, `POSTGRES_PASSWORD`).
* Nur Systeme testen, für die man die Erlaubnis hat.

## 2. Instanz aufsetzen

1. Repository klonen, `cp .env.example .env`.
2. In der `.env` setzen: `DEBUG=0`, eigene Schlüssel, `ALLOWED_HOSTS=localhost,127.0.0.1` (und den VM-Namen, falls nötig).
   `ADMIN_USER`/`ADMIN_PASSWORD`/`VEREIN_NAME` **leer lassen**, damit kein echter Verein angelegt wird.
3. Starten: `docker compose build && docker compose up -d`
4. Testvereine und Testkonten anlegen:

```bash
docker compose exec web python manage.py sicherheitstest_vorbereiten --testinstanz
```

Der Befehl legt zwei Vereine (A und B) an, je drei Mitglieder (eines mit IBAN) und vier Konten, **ohne** Superuser und damit
ohne Pflicht-2FA. Die zufälligen Passwörter erscheinen nur einmal in der Ausgabe. Neu erzeugen: `--zuruecksetzen`. Der Befehl
weigert sich, wenn andere Vereine existieren (also auf einer echten Instanz).

| Konto | Verein | Rechte |
| --- | --- | --- |
| `pt_admin_a` | A | Rolle „Administrator“ (alles, aber kein Superuser) |
| `pt_lesen_a` | A | nur Anzeigen, ohne Verwaltung und Änderungsprotokoll |
| `pt_kasse_a` | A | nur Kassenbuch (anzeigen, anlegen) |
| `pt_admin_b` | B | Rolle „Administrator“ im zweiten Mandanten |

Die Weboberfläche lauscht standardmäßig nur auf `127.0.0.1:8000`. Von einem anderen Rechner aus per SSH-Tunnel erreichbar:
`ssh -L 8000:127.0.0.1:8000 benutzer@vm`, danach im Browser `http://localhost:8000`.

## 3. Brute-Force-Schutz für den Test ausschalten

Nach 5 Fehlversuchen sperrt `django-axes` Benutzername und IP für eine Stunde, ein Scanner sperrt sich damit selbst aus.
Entsperren: `docker compose exec web python manage.py axes_reset`. Den Schutz selbst prüft man gesondert (Abschnitt 6).

## 4. Automatischer Scan mit OWASP ZAP

Baseline-Scan (passiv: Header, Cookies, offensichtliche Fehler, wenige Minuten, ungefährlich):

```bash
docker run --rm --network host -v "$PWD:/zap/wrk" -t zaproxy/zap-stable \
  zap-baseline.py -t http://127.0.0.1:8000 -r zap-baseline.html
```

Aktiver Scan mit Anmeldung (greift an: XSS, SQL-Injection, Pfadtraversal): Im ZAP-Desktop unter *Kontext* ein Formular-Login mit
`pt_admin_a` einrichten (Anmeldeseite `/login/`, Felder `username` und `password`), den Verein mit dem Spider durchlaufen
lassen und dann *Active Scan* starten. Nur gegen die Test-VM.

## 5. Manuelle Prüfung mit Proxy (der wichtigste Teil)

Scanner verstehen die Rechte- und Mandantenlogik nicht. Browser über den Proxy (ZAP/Burp) auf die VM zeigen lassen und
folgende Punkte durchgehen. Die ersten drei prüft schon `apps/core/test_sicherheitstest_vorbereiten.py` automatisch.

1. **Mandantentrennung:** als `pt_admin_b` die Mitglieds-IDs aus Verein A aufrufen und in Anfragen austauschen
   (`/mitglieder/<id>/`, `/mitglieder/<id>/bearbeiten/`, `/mitglieder/<id>/auskunft/`, `/datei/<app>/<modell>/<id>/<feld>/`). Erwartet: 404, nie Daten.
2. **Rechte:** als `pt_lesen_a` Bearbeiten-, Anlegen- und Löschen-URLs per GET und POST aufrufen. Erwartet: 403 und keine Änderung.
3. **Modulgrenzen:** als `pt_kasse_a` Mitglieder, Spenden, Verwaltung aufrufen. Erwartet: 403.
4. **CSRF:** bei einem POST das Token entfernen oder ändern. Erwartet: 403.
5. **Eingaben:** in Textfeldern `"><script>alert(1)</script>` und `' OR 1=1 --` eintragen und die Ausgabe in Listen, Detailseiten, PDF
   und E-Mail-Vorschau ansehen. Erwartet: maskiert, kein Fehler.
6. **Uploads:** Datei mit falscher Endung, sehr große Datei, Dateiname mit `../`, SVG als Bild. Erwartet: abgelehnt oder harmlos als Download.
7. **Offene Weiterleitung:** `/login/?next=https://example.org` – nach dem Login darf es nicht extern weitergehen.
8. **Sitzung:** nach „Abmelden“ die alte Sitzungs-Cookie-Datei erneut senden. Erwartet: abgewiesen.

## 6. Anmeldung und Konto-Hilfe

* Brute-Force: sechsmal falsches Passwort für ein Testkonto. Erwartet: Sperre (nur mit eingeschaltetem axes, nicht in `manage.py test`).
* Hinter dem Proxy (Caddy) muss `USE_X_FORWARDED_FOR` zur Konfiguration passen, sonst sieht axes (und das Limit der Konto-Hilfe)
  nur die Proxy-Adresse.
* „Passwort vergessen“ und „2FA zurücksetzen anfragen“: mit bekanntem und unbekanntem Namen anfragen. Die Antwort muss gleich
  aussehen. Nach 5 Anfragen je IP und Stunde wird nichts mehr verschickt, die Antwort bleibt aber gleich.

## 7. TLS und Header der echten Adresse (nur lesend)

Für die produktive Domain genügt ein reiner Lesezugriff: `testssl.sh <domain>` oder SSL Labs für TLS, securityheaders.com für die
Antwort-Header. Das verändert nichts und löst nichts aus.

## 8. Aufräumen

`docker compose down -v` entfernt die Testinstanz samt Datenbank und Medien. Berichte (`zap-baseline.html` und Co.) enthalten
nur Testdaten, gehören aber trotzdem nicht ins Repository.

## 9. Funde auswerten

Pro Fund notieren: Konto, URL, Anfrage, erwartetes und tatsächliches Verhalten. Sicherheitsrelevantes zuerst beheben und mit
einem Test in der passenden `tests.py` absichern (Muster: `apps/core/test_sicherheitstest_vorbereiten.py`).
