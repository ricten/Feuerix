# Changelog

Alle nennenswerten Änderungen an Feuerix, neueste zuerst. Versionsnummern folgen Semantic Versioning
(siehe CLAUDE.md). Rein redaktionelle/interne Commits ohne Nutzerwirkung sind nicht einzeln aufgeführt.

## 1.36.3
- Testsuite deutlich beschleunigt: `manage.py test` nutzt jetzt automatisch einen schnellen Passwort-Hasher
  (nur im Testlauf, nie produktiv) und CI/Doku empfehlen `--parallel`. Zusammen 442 Tests von ca. 350 s auf
  ca. 20 s.

## 1.36.2
- INSTALL.md/INSTALL.en.md: Hardware-Mindestanforderung praezisiert (2 GB RAM ist eine knappe Untergrenze,
  4 GB fuer komfortablen Betrieb empfohlen) statt eines reinen Minimalwerts ohne Einordnung.

## 1.36.1
- README.md, INSTALL.md und docs/GITHUB.md jetzt auch auf Englisch (README.en.md, INSTALL.en.md,
  docs/GITHUB.en.md), gegenseitig verlinkt. Vorher auf Aktualität geprüft: veraltete Testanzahl, Hinweise
  zum alten Standardrollen-System und ein inzwischen überholter "Paperless-ngx ungetestet"-Absatz korrigiert.

## 1.36.0
- Alle vier Hilfe-Dokumente (Handbuch, Kasse & Mitglieder-Import, Schriftverkehr & Vorlagen,
  Selbstdatenpflege) liegen jetzt auch auf Englisch vor (`*.en.md`); die Hilfe-Seite in der Anwendung zeigt
  automatisch die zur gewählten Oberflächensprache passende Fassung.
- Dabei zwei weitere Altlasten der alten Standardrollen in SELBSTDATENPFLEGE.md/SCHRIFTVERKEHR.md korrigiert.

## 1.35.2
- Diese Datei (CHANGELOG.md) eingeführt, rückwirkend bis zur ersten Version befüllt.

## 1.35.1
- `KASSE_UND_IMPORT.md` korrigiert: Kassenprüfer ist keine Standardrolle mehr, sondern ein Tag; E-Rechnung-Import
  und „Beleg in Ablage übernehmen“ ergänzt; Familie-Import-Verhalten (immer automatisch angelegt) beschrieben.

## 1.35.0
- Selbstdatenpflege: Mitglieder können jetzt auch ihre Zahlungsart selbst ändern (mit Hinweis, dass ein
  SEPA-Mandat weiterhin vom Vorstand/Kassenwart eingerichtet werden muss).

## 1.34.5
- Online-Banking-Kennung (FinTS) wird jetzt verschlüsselt gespeichert statt im Klartext.
- Handbuch-Abschnitt „Zugriff über Tags“ von Kapitel 13 (Paperless) nach Kapitel 2 (Rollen und Rechte) verschoben;
  Speicherung von FinTS-Zugangsdaten/-Produkt-ID dokumentiert.

## 1.34.4
- Handbuch: Familien-Anlage und Familienstaffelung bei Beiträgen beschrieben.

## 1.34.3
- Handbuch: Upload externer Dokumente in die Ablage beschrieben.

## 1.34.2
- Ablage-Liste zeigt einen Hinweis, dass sich externe Dokumente über „Neu“ hochladen lassen.

## 1.34.1
- Paperless-/OpenSlides-Konto eines Superadmins wird beim Löschen des Benutzerzugangs sofort deaktiviert statt
  erst beim nächsten Abgleich.

## 1.34.0
- Superadministratoren bekommen automatisch Paperless- und OpenSlides-Zugang – auch ohne eigene Mitgliedsakte.

## 1.33.2
- „Familien“ im Menü von Verwaltung nach Mitglieder verschoben.

## 1.33.1
- FinTS- und Paperless-Anbindung als erfolgreich getestet dokumentiert (vorher als experimentell markiert).

## 1.33.0
- Bankumsätze (auch aus dem FinTS-Abruf) können jetzt gelöscht werden.

## 1.32.3
- Rollen-Seite als „fortgeschritten“ gekennzeichnet, Hinweis auf Tags/Berechtigungsmatrix.

## 1.32.2
- Historisierte Funktion trägt den Namen des jeweiligen Tags statt eines allgemeinen Platzhalters
  „Vorstandsmitglied“.

## 1.32.1
- Mitgliederakte zeigt Funktion samt Zeitraum (zwei Amtszeiten derselben Funktion waren bisher nicht
  unterscheidbar).

## 1.32.0
- Neues Tag „Beisitzer“ (Vorstandsmitglied ohne weitere Rechte).
- „Vorstandsmitglied“-Häkchen wird automatisch aus Tags abgeleitet statt manuell gesetzt.
- Abteilungen als Checkboxen statt Auswahlliste.
- Tags lassen sich neu anlegen, wahlweise mit oder ohne eigene Rechte.
- Handbuch direkt unter „Hilfe“ in der Anwendung verlinkt.

## 1.31.1
- Hinweis „bereits vergeben an …“ direkt im Formular bei den sechs DSO-Tags.

## 1.31.0
- Tags erscheinen jetzt unter „Funktionen“ in der Navigation, Mehrfachauswahl per Haken statt Auswahlliste.
- Restliche Standardrollen (Kassenprüfer, Inventarverwalter, Veranstaltungsplaner, Mitgliederverwaltung,
  Lesebenutzer) in Zusatzrollen/Tags umgewandelt.
- Hinweis in der Mitgliederakte, wenn ein Tag mit Rolle vergeben ist, aber kein Verwaltungszugang existiert.

## 1.30.0
- Altes, fest einprogrammiertes Standardrollen-Set vollständig abgelöst durch die Berechtigungsmatrix und das
  Tag „Administrator“ (auch für bestehende Installationen migriert).
- FinTS: abzurufende Konten lassen sich je Zugang einschränken.

## 1.28.0
- Berechtigungsmatrix nach dem Muster der Datenschutzordnung eingeführt.
- Tags verteilen Zugriffsrechte in dieser Software, Paperless und OpenSlides.
- Feldrechte für Geburtsdatum und Bankverbindung (unabhängig von den übrigen Mitgliederrechten).

## 1.27.0
- „Vorstandsmitglied“-Häkchen bekommt eine historisierte Funktion (Von/Bis).
- Paperless-Abgleich des Vorstands (Benutzerkonten anhand der Vorstandsmitgliedschaft).
- Marker für Alters-/Ehrenabteilung und aktive Einsatzabteilung.

## 1.26.0
- PDF-Vorschau auf den Detailseiten von Rechnung, Mahnung, Zuwendungsbestätigung, Kassenbericht, Schriftstück
  und Serienbrief.

## 1.25.0
- Paperless: Dokumenttyp wird mitgegeben; fertiggestellte Dokumente (Rechnungen, Zuwendungsbestätigungen,
  Kassenberichte, Schriftstücke, Serienbriefe, Belege) werden automatisch übergeben.

## 1.24.0
- Paperless: Bestätigung der Übergabe über die Datei-Prüfsumme (auch rückwirkend für Altbestand); Tags und
  Prüfsumme sichtbar; Vorschau für PDF und Bilder.

## 1.23.1
- Hinweise auf Mehrmandantenfähigkeit aus öffentlichen Texten entfernt (bleibt nur im Code dokumentiert).

## 1.23.0
- Paperless: Tags am Dokument (Art und Jahr automatisch vorbelegt), Live-Status der Übergabe, Sende-Knöpfe
  je nach Zustand.

## 1.22.1
- Ablage-Übersicht zeigt einen Haken bei bereits an Paperless übergebenen Dokumenten.

## 1.22.0
- Paperless: Duplikatschutz (Prüfsumme, lokal und in Paperless) und automatische Kategorie-Tags.

## 1.21.2
- Fix: Ersteinrichtung auf PostgreSQL (Vorlagen-Hinweistext war zu lang für das Feld) und fehlendes
  Paperless-DB-Passwort im Compose-Stack.

## 1.21.1
- Sicherheits-Audit: zusätzliche HTTPS-Hardening-Einstellungen.

## 1.21.0
- Update-Benachrichtigung für Administratoren, Lizenzhinweis im Footer.

## 1.20.1
- Fix: Konten blieben nicht mehr unter „Kasse“ in der Navigation.

## 1.20.0
- OpenSlides: Rückfluss der Wahlergebnisse abgeschlossener Personenwahlen in die Veranstaltung.

## 1.19.0
- FinTS: Kontodaten-Vorschau, Direkt-Abruf aus den Bankumsätzen, Konten im Verwaltungsmenü.

## 1.18.0
- FinTS: mehrere Zugänge je Verein, Konto-Zuordnung, verschlüsselte Produkt-ID.

## 1.17.0
- FinTS-Abruf mit echter TAN-Unterstützung umgesetzt.

## 1.16.0
- Optisches Redesign: Karten mit Schatten/Radius, Dashboard mit Icons, zweispaltige Detailseiten (inkl.
  Nachbesserungen: Zurück-Link, Überschriftgröße, Feuerix-Sichtbarkeit).

## 1.15.1
- Englische Übersetzung auf die eigenständigen Unterseiten ausgeweitet.

## 1.15.0
- Englische Übersetzung mit Sprachauswahl und Cookie-Hinweis.
- Transparenzhinweis zu KI-gestützter Entwicklung im README.

## 1.14.0
- Feuerix als eigene Softwaremarke eingeführt (getrennt vom Namen/Logo des einzelnen Vereins).
- Copyright-Zeile und inoffizielle deutsche AGPL-3.0-Übersetzung ergänzt.

## 1.13.0
- Umsatzsteuer-Ausweisung im Finanzmodul für nicht gemeinnützige Vereine (je Rechnungsposition, auch gemischt).

## 1.12.1
- Mitglieder- und Inventar-Import unter Verwaltung statt als Button in der jeweiligen Liste.

## 1.12.0
- Automatische Icons für alle Buttons, farbiger Menü-Hover, Sektions-Icon auf Unterseiten.

## 1.11.0
- Weboberfläche mit vereinseigener Akzentfarbe und Icons gestaltet.
- Regeln zur Semantic-Versionierung dokumentiert (Beginn dieser Versionierungsdisziplin).

## 1.10.0
- Impressum und öffentliche Downloads-Seite eingebaut; Mehrmandantenfähigkeit vorerst gesperrt.

## 1.8.0
- E-Rechnung von selbstgebautem XRechnung-XML auf ZUGFeRD-PDF umgestellt.

## 1.7.0
- Belege aus dem Kassenbuch lassen sich in die Ablage übernehmen.

## 1.6.0
- OpenSlides und Paperless-ngx als vollständig optionale Bausteine; DSGVO-Anonymisierung auf das verknüpfte
  OpenSlides-Konto ausgeweitet.

## 1.5.0
- E-Rechnungen ausstellen (XRechnung/UBL); INSTALL/README um Paperless ergänzt.

## 1.4.0
- Kontoauszug-Import um MT940 und CAMT.053 erweitert.

## 1.3.0
- Paperless-ngx-Anbindung und SEPA-Sammellastschrift-Export eingeführt.

## 1.1.0
- E-Rechnungsimport, sortierbare Listen-Spalten.

## 1.0.0 (Grundlage)
Erste Version mit Versionsnummer – alles bis hierhin war bereits vorhandene Grundfunktionalität:
- Mitglieder-, Beitrags-, Rechnungs- und Zahlungsverwaltung; Kassenbuch und Kassenbericht.
- Inventarverwaltung mit Verleih (inkl. Warenkorb-Sammelverleih per QR-Scan) und Inventur.
- Vereinslogo/Akzentfarbe im Briefkopf (PDF und Word), Spendenquittungen, Aufwandsentschädigungen.
- Selbstdatenpflege für Mitglieder, Verwaltungszugang direkt aus der Mitgliederakte einrichten.
- Diverse frühe Fixes (Import-Robustheit, Many-to-Many-Detailseiten, OpenSlides-Tagesordnung, Checkbox-Layout).

---
*Hinweis für Claude Code: Bei jeder nennenswerten Änderung (siehe CLAUDE.md, Abschnitt „Versionierung“) einen
neuen Abschnitt ganz oben ergänzen – kurzer Stichpunkt pro Änderung, keine Testläufe nur für diese Datei nötig.*
