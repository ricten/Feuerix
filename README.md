# Feuerix – Vereinsverwaltung für Feuerwehr-Fördervereine (Django · PostgreSQL · Docker)

"Feuerix" ist die Softwaremarke (`PRODUCT_NAME` in `config/settings.py`) – getrennt vom Namen/Logo des einzelnen
Vereins, das jede Feuerwehr selbst hochlädt und das auf der eigenen Instanz die Hauptmarke bleibt.

Mandantenfähige Vereinsverwaltung: Mitglieder, Ehrungen/Jubiläen, Beiträge, Rechnungen, Zahlungen, Bankumsätze,
Inventar mit Verleih und Inventur, Spendenquittungen, Aufwandsentschädigungen, Veranstaltungsplanung,
Rechte/Rollen, vollständiges Änderungsprotokoll, Auswertungen mit CSV/Excel-Export.

> **Stand:** Eine automatisierte Testsuite (`python manage.py test`, ~218 Tests) und eine GitHub-Actions-CI prüfen
> bei jeder Änderung gegen eine echte PostgreSQL-Datenbank. Nicht gegen eine produktive Instanz bzw. eine echte Bank
> verifiziert sind die OpenSlides- und die Paperless-ngx-Anbindung (beide nach offizieller Dokumentation umgesetzt)
> sowie der FinTS-Abruf (nach der `python-fints`-Dokumentation umgesetzt, TAN-Ablauf mit simulierten Antworten
> getestet) – dafür vor dem Verlass darauf eine Testphase einplanen.

**Handbuch:** Eine ausführliche Bedienungsanleitung für Vorstand, Kassenwart, Schriftführer & Co. steht in
**[docs/HANDBUCH.md](docs/HANDBUCH.md)**.

**Entwicklung mit KI-Unterstützung:** Ein erheblicher Teil des Codes in diesem Repository wurde mit Unterstützung
von KI-Coding-Werkzeugen (Claude Code) geschrieben – Anforderungen, Architekturentscheidungen, Code-Review und
die fachliche Verantwortung liegen beim menschlichen Autor. Die Software selbst enthält zur Laufzeit keine
KI-Funktionen; dieser Hinweis dient der Transparenz, nicht einer gesetzlichen Kennzeichnungspflicht.

**Version:** Die Datei `VERSION` enthält die aktuelle Versionsnummer nach Semantic Versioning (`MAJOR.MINOR.PATCH`)
und wird bei jedem nennenswerten Deploy erhöht: **PATCH** für Bugfixes (`1.0.0` → `1.0.1`), **MINOR** für neue
Funktionen (`1.0.0` → `1.1.0`), **MAJOR** für große strukturelle Änderungen (`1.0.0` → `2.0.0`). Sie erscheint im
Footer jeder Seite und hilft bei der Fehlersuche/Support, den laufenden Stand zu identifizieren.

## Start

Ausführliche Schritt-für-Schritt-Anleitung für Server, HTTPS und die optionalen Anbindungen (OpenSlides,
Paperless-ngx): **[INSTALL.md](INSTALL.md)**. Kurzfassung:

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

* Die Datentrennung ist mandantenfähig angelegt: Jede Datenzeile gehört zu genau einem Verein; alle Listen,
  Detailseiten, Formularauswahlen, Datei-Downloads und Exporte sind auf den aktiven Verein beschränkt.
* **Aktuell gesperrt:** Über `/admin/` lässt sich vorerst kein zweiter Verein anlegen, solange bereits einer
  existiert (`VereinAdmin.has_add_permission`) – das Mehrmandanten-Setup ist für den produktiven Einsatz mit
  mehreren Vereinen derzeit nicht freigegeben. Bereits bestehende Installationen mit mehreren Vereinen sind davon
  nicht betroffen; die Sperre verhindert nur das Neuanlegen.
* Vereins-Administratoren verwalten ihre Benutzer selbst (*Verwaltung › Benutzer*). Ein Benutzer kann Zugang zu
  mehreren Vereinen haben (Umschalter in der Kopfzeile) und sieht nur diese.
* Rechte: Rolle je Verein + individuelle Einzelrechte je Modul (Anzeigen/Erstellen/Bearbeiten/Löschen).

## Design der Weboberfläche

Navigation, Buttons und Links verwenden die pro Verein einstellbare **Akzentfarbe** (*Verwaltung ›
Verein/Einstellungen*, dieselbe Farbe wie auf Briefen/PDFs) – die Textfarbe in der Navigationsleiste wird
automatisch für Lesbarkeit berechnet, farbig unterlegte Hover-Effekte markieren den aktiven/angehovten Menüpunkt.
Icons stammen von [Bootstrap Icons](https://icons.getbootstrap.com/), lokal ausgeliefert wie Bootstrap/HTMX (kein
CDN, DSGVO-freundlich); nahezu jeder Button bekommt anhand seines Labels automatisch ein passendes Icon
(`apps/core/crud.py::_icon_fuer`), zusätzlich zeigt jede Unterseite oben rechts das Icon ihrer Navigationsgruppe.
Karten sind durchgehend abgerundet mit weichem Schatten und akzentfarbenen Details (Kennzahlen-Karten mit
farbiger Linie links, Tabellenköpfe leicht eingefärbt, Karten mit Link-Ziel heben sich beim Hover leicht an).
Detailseiten nutzen ab `xl`-Breite eine zweispaltige Ansicht (Stammdaten als Sidebar links, verknüpfte Listen
rechts) statt einer einzigen langen Spalte, um breite Bildschirme besser auszunutzen.

## Sprache und Cookie-Hinweis

Deutsch/Englisch umschaltbar über die Sprachauswahl oben in der Menüleiste (auch auf der Anmeldeseite) –
Standard-Django-i18n (`django.middleware.locale.LocaleMiddleware`, Auswahl per Cookie). Übersetzt: Navigation,
An-/Abmeldung, Dashboard, generische Listen-/Detail-/Formularseiten. Neue Übersetzungen ergänzen:
`django-admin makemessages -l en`, Texte in `locale/en/LC_MESSAGES/django.po` eintragen, dann
`django-admin compilemessages` (braucht GNU `gettext`, das `.mo`-Ergebnis wird mit eingecheckt). Da eine
Spracheinstellung als Cookie gespeichert wird, zeigt die Seite einmalig einen Cookie-Hinweis (nur technisch
notwendige Cookies: Anmeldung, CSRF-Schutz, Sprache – keine Tracking-Cookies).

## Module

| Modul | Kernfunktionen |
|---|---|
| Mitglieder | **Import** aus Excel/CSV (Testlauf, Aktualisierung bestehender Mitglieder, Fehlerbericht, Vorlagendatei) und **Vollexport** (Excel/CSV, Bankdaten nur mit Beitragsrecht, protokolliert); Akte inkl. verschlüsselter IBAN, SEPA-Mandat, Familie/Familienzahler, Abteilungen, Funktionen, versionierte Dokumente, Datenauskunft (JSON), Anonymisierung; **Selbstdatenpflege** – Mitglieder pflegen Adresse/Telefon/E-Mail/Bankverbindung selbst online, siehe [docs/SELBSTDATENPFLEGE.md](docs/SELBSTDATENPFLEGE.md) |
| Ehrungen | Ehrungsarten, Ehrungen, konfigurierbare Jubiläumsregeln, Jubiläumsliste mit Direktanlage |
| Beiträge | Mitgliedsarten, Regeln (Alter, Familie, Gültigkeitsjahre, Priorität), individuelle Beiträge, Beitragsjahre mit Rechnungslauf; Beträge werden in der Rechnung eingefroren |
| Rechnungen | Nummernkreis `RE-JJJJ-000001`, Entwurf → Ausstellen (danach unveränderbar), PDF, **E-Rechnung (ZUGFeRD/Factur-X-PDF, EN16931, XSD-validiert)**, E-Mail, Storno (mit buchbarer **Rückzahlung** bei bereits bezahlten Rechnungen), Gutschrift, Mahnstufen mit PDF; **Umsatzsteuer je Position** (0 % Standard, auch gemischt auf einer Rechnung) für nicht gemeinnützige Vereine/den wirtschaftlichen Geschäftsbetrieb, mit Netto/Steuer/Brutto-Aufschlüsselung auf PDF und E-Rechnung |
| Zahlungen/Bank | Zahlungen je Rechnung inkl. Rücklastschrift, Kontoauszug-Import in **CSV, MT940 und CAMT.053** (Format wird automatisch erkannt) mit Dublettenerkennung, automatische Zuordnung (Rechnungsnr. → Mitgliedsnr. → IBAN), Liste „manuelle Zuordnung erforderlich“; **SEPA-Sammellastschrift-Export** (pain.008/CORE) für offene Rechnungen mit SEPA-Mandat, automatische Erst-/Folgelastschrift-Erkennung; **FinTS-Abruf** direkt aus der Weboberfläche inkl. TAN-Abfrage (experimentell, siehe unten) als Alternative zum manuellen Kontoauszug-Import |
| Kassenbuch | Konten (Bank/Bar), Buchungskategorien mit steuerlicher Sphäre, Buchungen mit Belegnummer und Belegupload, Übernahme aus Zahlungen/Spenden/Aufwandsentschädigungen/Veranstaltungen (idempotent), **E-Rechnung importieren** (XRechnung/ZUGFeRD einlesen und als vorausgefüllte Ausgabe mit Beleg ablegen), **Beleg in Ablage übernehmen** (zusätzlich im allgemeinen Dokumentenarchiv einordnen) |
| Kassenbericht | Zeitraumbericht mit Kontenübersicht, Einnahmen/Ausgaben je Kategorie und Sphäre, Vorjahresvergleich, Soll/Ist-Abgleich, Prüfungsbemerkung, Unterschriftszeilen, Kassenbuch-Anlage; PDF + Excel; Abschluss sperrt den Zeitraum und legt das PDF in der Ablage ab |
| Inventar | Inventarnummern `INV-000001`, Kategorien, Standorte, Zustand, Garantie, Fotos/Dokumente, **Import** aus Excel/CSV (wie Mitglieder), Etikettendruck mit **QR-Code** je Gegenstand |
| Verleih | Reservierung → Ausgabe → Rückgabe, Konfliktprüfung (Überschneidungen, defekt, überfällig), Kaution/Gebühr, Zustand bei Ausgabe/Rückgabe, Leihschein-PDF, Bezug zu Veranstaltungen; **Verleih-Warenkorb** (QR-Etiketten mit dem Handy scannen) und Sammelverleih für mehrere Gegenstände als ein **Vorgang** (gemeinsame Ausgabe/Rückgabe/Rechnung/Leihschein); bei Rückgabe wählbar, ob eine Kaution zurückgezahlt oder einbehalten (→ Rechnung) wird |
| Inventur | Momentaufnahme des Bestands, Positionen abhaken (gefunden / nicht gefunden / beschädigt), Abschluss, Historie bleibt erhalten |
| Spenden | Spenden (Geld/Sach/Aufwandsverzicht/Beitrag), Einzel- und Sammelbestätigungen, Ausstellen mit Nummernkreis `ZB-JJJJ-000001`, Storno, PDF, Prüfung der Vereinsdaten |
| Aufwandsentschädigungen | Ehrenamts-/Übungsleiterpauschale, Aufwandsersatz, Genehmigungsworkflow, Freibetragsübersicht je Person/Jahr, Aufwandsverzicht → Spende |
| Veranstaltungen | Planung, Aufgaben, Schichtplan mit Besetzung, Anmeldungen, Budget (Plan/Ist), Inventarreservierung, iCal-Export |
| Schriftverkehr | Vereinslogo (auf allen PDFs), bearbeitbare Vorlagen (Einladung, Protokoll, Serienbrief …) mit Platzhaltern, Einzelschriftstücke mit PDF- und Word-Export, Serienbriefe mit Empfängerfilter (PDF-Sammeldatei oder E-Mail mit PDF-Anhang) – siehe [docs/SCHRIFTVERKEHR.md](docs/SCHRIFTVERKEHR.md) |
| Ablage | Ordnerstruktur (Kategorie/Jahr), versionierte Dokumente, Zuordnung zu Veranstaltungen, geschützter Dateizugriff; erzeugte PDFs werden automatisch abgelegt; optionaler Versand an **Paperless-ngx** (einzeln oder gesammelt); einzelne Dokumente als **öffentlich** markierbar (Datenschutzerklärung, Aufnahmeformular u. Ä.) – erscheinen dann ohne Anmeldung auf einer öffentlichen Downloads-Seite |
| OpenSlides | Anbindung an OpenSlides 4: Konten der Mitglieder anlegen/abgleichen, Versammlung + Tagesordnung aus der Veranstaltung anlegen (nach Dokumentation umgesetzt, ungetestet) |
| Paperless-ngx | Verbindung je Verein (Adresse, API-Token verschlüsselt gespeichert, Verbindungstest); Ablage-Dokumente per Knopf oder gesammelt an eine bestehende Paperless-Instanz senden (Korrespondent/Dokumenttyp/Tags werden dort bei Bedarf automatisch angelegt) |
| Protokoll | Jede Änderung: wer, wann, IP, Feld alt → neu, optionaler Grund; sensible Felder maskiert |

## Wichtige Hinweise

* **FIELD_ENCRYPTION_KEY sichern!** Ohne ihn sind verschlüsselte IBANs nicht lesbar. Backup: `docker compose exec web /app/scripts/backup.sh`.
* **Spendenquittungen:** Die PDF-Textbausteine folgen dem Aufbau des amtlichen Musters, ersetzen aber nicht dessen
  Prüfung. Vor dem ersten Einsatz mit dem aktuellen BMF-Muster bzw. Steuerberater/Finanzamt abgleichen. Vereinsdaten
  (Finanzamt, Steuernummer, Bescheiddatum, Zwecke) müssen unter *Verwaltung › Verein* gepflegt sein.
* **Freibeträge** (Standard: 3.300 € Übungsleiter, 960 € Ehrenamt) sind pro Verein einstellbar – bitte auf Aktualität prüfen.
  Die Übersicht kennt nur Zahlungen dieses Vereins.
* **Impressum:** Das Textfeld unter *Verwaltung › Verein* wird ungeprüft auf einer öffentlichen, nicht
  anmeldungspflichtigen Seite angezeigt (Pflicht nach § 5 TMG) – der Inhalt muss selbst korrekt und vollständig
  eingetragen werden.
* **Beitragslauf:** Berechnet den vollen Jahresbeitrag für alle im Jahr zeitweise aktiven Mitglieder (keine anteilige Berechnung).
* **E-Rechnungen:** Empfang (Einlesen bekannter Kernfelder aus XRechnung/ZUGFeRD, Ablage als Beleg) und Ausstellen
  eigener Rechnungen als **ZUGFeRD/Factur-X-PDF** (Profil EN16931 – die normale PDF-Rechnung mit eingebetteter
  XML) sind enthalten. Die eingebettete XML wird über die Bibliothek [`factur-x`](https://github.com/akretion/factur-x)
  erzeugt und dabei automatisch gegen das amtliche XML-Schema (XSD) geprüft – eine echte strukturelle
  Validierung, kein handgeschriebenes XML. **Nicht geprüft** werden die vollständigen EN16931-Geschäftsregeln
  (Schematron; dafür wäre ein Java-Prüfwerkzeug bzw. Saxon-Server nötig, bewusst nicht eingebunden) und die
  PDF/A-3-Konformität der Trägerdatei selbst (kein veraPDF-Check). Mangels je Position geführter
  Umsatzsteuersätze wird pauschal Steuerbefreiung nach § 4 UStG (ideeller Bereich) angenommen; bei tatsächlich
  umsatzsteuerpflichtigen Vorgängen (wirtschaftlicher Geschäftsbetrieb) unbedingt vor dem Versand prüfen
  (lassen) und die erzeugte Datei gegen ein offizielles Prüfwerkzeug (z. B. den KoSIT-Validator) laufen lassen.
  Für die üblichen Mitgliedsrechnungen ohnehin meist irrelevant, da Mitglieder keine Unternehmer sind und damit
  keine B2B-E-Rechnungspflicht besteht.
* **Paperless-ngx:** Entweder eine bereits laufende, separate Instanz verwenden (nur Adresse und API-Token unter
  *Verwaltung › Paperless-Anbindung* eintragen), oder optional über [paperless/](paperless/) als eigenen
  Docker-Compose-Stack auf diesem Server mitbetreiben (siehe INSTALL.md Abschnitt 9). Der Versand ist in jedem
  Fall reines Hochladen (Einweg); es gibt keinen Rücksync von Status/Metadaten aus Paperless in Feuerix.
* **Kontoauszug-Import:** CSV, MT940 und CAMT.053 werden anhand Dateiendung/Inhalt automatisch erkannt; bei MT940
  wird der Verwendungszweck nur nach den gängigen deutschen SEPA-Feldkennungen (`SVWZ+` u. a.) durchsucht – weicht
  eine Bank davon ab, landet der komplette Text unstrukturiert im Verwendungszweck.
* **FinTS-Abruf** (*Verwaltung › FinTS-Zugänge*): Kontoumsätze direkt aus der Weboberfläche abrufen, inkl.
  TAN-Abfrage (App-/SMS-/chipTAN, mit Grafikanzeige bei chipTAN) – als Alternative zum manuellen
  Kontoauszug-Import. Ein Verein kann **mehrere FinTS-Zugänge** anlegen (z. B. bei verschiedenen Banken); jedes
  Kassenbuch-Konto (*Verwaltung › Konten*) kann optional einem davon zugeordnet werden – Konten ohne Zuordnung
  laufen unverändert über den manuellen Kontoauszug-Import. „Kontodaten abrufen“ auf der Detailseite eines Zugangs
  zeigt nur IBAN/BIC der beim Kreditinstitut hinterlegten Konten (Verbindungstest/Zuordnungshilfe, ohne
  Transaktions-Import). Die Bank-PIN wird **nie gespeichert**, sondern bei jedem Abruf neu abgefragt und liegt nur
  kurzzeitig (bis der TAN-Vorgang abgeschlossen ist) serverseitig in der Sitzung.
  Erfordert zusätzlich eine kostenlose, bei der Deutschen Kreditwirtschaft registrierte FinTS-Produkt-ID – wird
  **nicht** mit Feuerix mitgeliefert, jeder Betreiber registriert seine eigene und hinterlegt sie entweder als
  `FINTS_PRODUCT_ID` in der `.env` oder (bevorzugt, weil verschlüsselt in der Datenbank statt im Klartext in der
  Konfigurationsdatei) unter `/admin/` › Systemeinstellungen. Umgesetzt nach der Dokumentation von `python-fints`,
  aber **noch gegen keine echte Bank getestet** – vor
  dem produktiven Einsatz mit der eigenen Bank ausprobieren. Werden mehrere TANs hintereinander verlangt, wird das
  unterstützt; ein einzelner Abruf verarbeitet dabei alle beim jeweiligen Kreditinstitut hinterlegten Konten.
* **Betrieb:** Hinter einen Reverse Proxy mit HTTPS setzen und `HTTPS=1` in der `.env` aktivieren.
  Bootstrap/HTMX werden beim Build lokal eingebunden (keine externen CDNs).

## Entwicklung

Tests: `python manage.py test` (benötigt PostgreSQL-Zugang wie in `.env`). GitHub-Ablage und CI: [docs/GITHUB.md](docs/GITHUB.md).

**Testdaten:** `python manage.py beispieldaten --verein <kuerzel> [--anzahl 40] [--ohne-inventar]` legt für einen
bestehenden Verein fiktive Mitglieder sowie einen Beitragsjahr-Rechnungslauf mit realistischer Zahlungsverteilung an
(vollständig bezahlt / teilbezahlt mit Mahnung / offen und überfällig) und ein Beispiel-Inventar (Feuerwehrausrüstung
und Veranstaltungstechnik mit Kategorien/Standorten) – nur für Test-/Demoinstallationen, nicht für den
Produktivbetrieb gedacht.

## Noch nicht enthalten

Abstimmungsergebnisse aus OpenSlides zurück ins Protokoll, REST-API (DRF), anteilige Beiträge, Update-/Restore-Oberfläche.
Der SEPA-Einzug erzeugt nur die Einzugsdatei (pain.008) – der Rückkanal (eingegangen/zurückgebucht) läuft weiterhin
über den normalen Kontoauszug-Import.

## Lizenz

Copyright (C) 2026 Rico Tengler

[GNU Affero General Public License v3.0](LICENSE) ([inoffizielle deutsche Übersetzung](LICENSE.de.md) zum
besseren Verständnis – rechtlich verbindlich ist nur der englische Originaltext). Wird der Code (auch
verändert) als Netzwerkdienst betrieben, muss der Quellcode dieser Version den Nutzern zugänglich gemacht
werden (§ 13 AGPL).
