# Vereinsverwaltung (Django · PostgreSQL · Docker)

Mandantenfähige Vereinsverwaltung: Mitglieder, Ehrungen/Jubiläen, Beiträge, Rechnungen, Zahlungen, Bankumsätze,
Inventar mit Verleih und Inventur, Spendenquittungen, Aufwandsentschädigungen, Veranstaltungsplanung,
Rechte/Rollen, vollständiges Änderungsprotokoll, Auswertungen mit CSV/Excel-Export.

> **Stand:** Der Code wurde ohne Testlauf geschrieben (keine Möglichkeit, Django/Postgres in der Entwicklungsumgebung
> zu starten). Rechnen Sie beim ersten Start mit kleineren Fehlern und testen Sie vor dem Produktiveinsatz
> gründlich – insbesondere Rechnungslauf, Bankzuordnung und Spendenquittungen.

## Start

Ausführliche Schritt-für-Schritt-Anleitung für Server, HTTPS und OpenSlides: **[INSTALL.md](INSTALL.md)**. Kurzfassung:

```bash
cp .env.example .env          # SECRET_KEY, FIELD_ENCRYPTION_KEY, POSTGRES_PASSWORD, ADMIN_* ausfüllen
# Migrationen einmalig erzeugen und im Projekt ablegen (wichtig für spätere Updates):
docker compose build
docker compose run --rm --no-deps --user root -v "$PWD/apps:/app/apps" web python manage.py makemigrations
docker compose up -d
```

Danach: http://localhost:8000 – Anmeldung mit `ADMIN_USER` / `ADMIN_PASSWORD`. Beim allerersten Start wird der
Verein aus `VEREIN_NAME` samt Standardrollen, Mitgliedsarten (Beispielbeträge!), Ehrungsarten und Jubiläumsregeln
angelegt. Die Beträge unter *Verwaltung › Mitgliedsarten / Beiträge* bitte anpassen.

## Mehrere Vereine (Mandanten)

* Jede Datenzeile gehört zu genau einem Verein; alle Listen, Detailseiten, Formularauswahlen, Datei-Downloads und
  Exporte sind auf den aktiven Verein beschränkt.
* Weitere Vereine legt der Plattform-Administrator (Django-Superuser) unter `/admin/` › Vereine an – Standardrollen und
  Stammdaten entstehen automatisch.
* Vereins-Administratoren verwalten ihre Benutzer selbst (*Verwaltung › Benutzer*). Ein Benutzer kann Zugang zu
  mehreren Vereinen haben (Umschalter in der Kopfzeile) und sieht nur diese.
* Rechte: Rolle je Verein + individuelle Einzelrechte je Modul (Anzeigen/Erstellen/Bearbeiten/Löschen).

## Module

| Modul | Kernfunktionen |
|---|---|
| Mitglieder | **Import** aus Excel/CSV (Testlauf, Aktualisierung bestehender Mitglieder, Fehlerbericht, Vorlagendatei) und **Vollexport** (Excel/CSV, Bankdaten nur mit Beitragsrecht, protokolliert); Akte inkl. verschlüsselter IBAN, SEPA-Mandat, Familie/Familienzahler, Abteilungen, Funktionen, versionierte Dokumente, Datenauskunft (JSON), Anonymisierung |
| Ehrungen | Ehrungsarten, Ehrungen, konfigurierbare Jubiläumsregeln, Jubiläumsliste mit Direktanlage |
| Beiträge | Mitgliedsarten, Regeln (Alter, Familie, Gültigkeitsjahre, Priorität), individuelle Beiträge, Beitragsjahre mit Rechnungslauf; Beträge werden in der Rechnung eingefroren |
| Rechnungen | Nummernkreis `RE-JJJJ-000001`, Entwurf → Ausstellen (danach unveränderbar), PDF, E-Mail, Storno, Gutschrift, Mahnstufen mit PDF |
| Zahlungen/Bank | Zahlungen je Rechnung inkl. Rücklastschrift, CSV-Import mit Dublettenerkennung, automatische Zuordnung (Rechnungsnr. → Mitgliedsnr. → IBAN), Liste „manuelle Zuordnung erforderlich“ |
| Kassenbuch | Konten (Bank/Bar), Buchungskategorien mit steuerlicher Sphäre, Buchungen mit Belegnummer und Belegupload, Übernahme aus Zahlungen/Spenden/Aufwandsentschädigungen/Veranstaltungen (idempotent) |
| Kassenbericht | Zeitraumbericht mit Kontenübersicht, Einnahmen/Ausgaben je Kategorie und Sphäre, Vorjahresvergleich, Soll/Ist-Abgleich, Prüfungsbemerkung, Unterschriftszeilen, Kassenbuch-Anlage; PDF + Excel; Abschluss sperrt den Zeitraum und legt das PDF in der Ablage ab |
| Inventar | Inventarnummern `INV-000001`, Kategorien, Standorte, Zustand, Garantie, Fotos/Dokumente |
| Verleih | Reservierung → Ausgabe → Rückgabe, Konfliktprüfung (Überschneidungen, defekt, überfällig), Kaution/Gebühr, Zustand bei Ausgabe/Rückgabe, Leihschein-PDF, Bezug zu Veranstaltungen |
| Inventur | Momentaufnahme des Bestands, Positionen abhaken (gefunden / nicht gefunden / beschädigt), Abschluss, Historie bleibt erhalten |
| Spenden | Spenden (Geld/Sach/Aufwandsverzicht/Beitrag), Einzel- und Sammelbestätigungen, Ausstellen mit Nummernkreis `ZB-JJJJ-000001`, Storno, PDF, Prüfung der Vereinsdaten |
| Aufwandsentschädigungen | Ehrenamts-/Übungsleiterpauschale, Aufwandsersatz, Genehmigungsworkflow, Freibetragsübersicht je Person/Jahr, Aufwandsverzicht → Spende |
| Veranstaltungen | Planung, Aufgaben, Schichtplan mit Besetzung, Anmeldungen, Budget (Plan/Ist), Inventarreservierung, iCal-Export |
| Schriftverkehr | Vereinslogo (auf allen PDFs), bearbeitbare Vorlagen (Einladung, Protokoll, Serienbrief …) mit Platzhaltern, Einzelschriftstücke mit PDF- und Word-Export, Serienbriefe mit Empfängerfilter (PDF-Sammeldatei oder E-Mail mit PDF-Anhang) – siehe [docs/SCHRIFTVERKEHR.md](docs/SCHRIFTVERKEHR.md) |
| Ablage | Ordnerstruktur (Kategorie/Jahr), versionierte Dokumente, Zuordnung zu Veranstaltungen, geschützter Dateizugriff; erzeugte PDFs werden automatisch abgelegt |
| OpenSlides | Anbindung an OpenSlides 4: Konten der Mitglieder anlegen/abgleichen, Versammlung + Tagesordnung aus der Veranstaltung anlegen (nach Dokumentation umgesetzt, ungetestet) |
| Protokoll | Jede Änderung: wer, wann, IP, Feld alt → neu, optionaler Grund; sensible Felder maskiert |

## Wichtige Hinweise

* **FIELD_ENCRYPTION_KEY sichern!** Ohne ihn sind verschlüsselte IBANs nicht lesbar. Backup: `docker compose exec web /app/scripts/backup.sh`.
* **Spendenquittungen:** Die PDF-Textbausteine folgen dem Aufbau des amtlichen Musters, ersetzen aber nicht dessen
  Prüfung. Vor dem ersten Einsatz mit dem aktuellen BMF-Muster bzw. Steuerberater/Finanzamt abgleichen. Vereinsdaten
  (Finanzamt, Steuernummer, Bescheiddatum, Zwecke) müssen unter *Verwaltung › Verein* gepflegt sein.
* **Freibeträge** (Standard: 3.300 € Übungsleiter, 960 € Ehrenamt) sind pro Verein einstellbar – bitte auf Aktualität prüfen.
  Die Übersicht kennt nur Zahlungen dieses Vereins.
* **Beitragslauf:** Berechnet den vollen Jahresbeitrag für alle im Jahr zeitweise aktiven Mitglieder (keine anteilige Berechnung).
* **Betrieb:** Hinter einen Reverse Proxy mit HTTPS setzen und `HTTPS=1` in der `.env` aktivieren.
  Bootstrap/HTMX werden beim Build lokal eingebunden (keine externen CDNs).

## Entwicklung

Tests: `python manage.py test` (benötigt PostgreSQL-Zugang wie in `.env`). GitHub-Ablage und CI: [docs/GITHUB.md](docs/GITHUB.md).

## Noch nicht enthalten

FinTS-Live-Abruf (nur experimentelles Kommando `fints_abruf`, ungetestet, ohne TAN-Verfahren), SEPA-Lastschrift-XML-Export,
Abstimmungsergebnisse aus OpenSlides zurück ins Protokoll, REST-API (DRF), anteilige Beiträge, Update-/Restore-Oberfläche.

## Lizenz

[GNU Affero General Public License v3.0](LICENSE). Wird der Code (auch verändert) als Netzwerkdienst betrieben, muss der
Quellcode dieser Version den Nutzern zugänglich gemacht werden (§ 13 AGPL).
