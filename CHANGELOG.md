# Changelog

Alle nennenswerten Änderungen an Feuerix, neueste zuerst. Versionsnummern folgen Semantic Versioning
(siehe CLAUDE.md). Rein redaktionelle/interne Commits ohne Nutzerwirkung sind nicht einzeln aufgeführt.

## 1.49.0
- Neu: Öffentlicher Rückmeldungs-Link bei Veranstaltungen mit Anmeldepflicht - Zu-/Absage mit Namen und
  Personenzahl, ohne Login, über einen nicht erratbaren Link auf der Veranstaltungsseite.
- Fix: ZUGFeRD-Export (`erechnung.py`) an die ab `factur-x` 7.0 geänderte Datenstruktur angepasst (Verkäufer/
  Käufer jetzt als verschachtelte Objekte statt einzelner Felder) - keine Versionsobergrenze nötig.

## 1.48.2
- "Passwort" und "Abmelden" sitzen jetzt im Logo-Band neben der Sprachauswahl statt weiter unten im Menü-Band.

## 1.48.1
- Reserviert der Verein selbst Inventar für eine Veranstaltung (kein Entleiher), werden Leihgebühr und Kaution
  jetzt automatisch auf 0 gesetzt statt die am Gegenstand hinterlegten Werte zu übernehmen - der Verein muss
  sich selbst keine Gebühr/Kaution berechnen.

## 1.48.0
- Englische Übersetzung auf alle Modellfelder und Auswahllisten (Status, Kategorien, Zahlarten usw.) in
  sämtlichen 12 Modulen ausgeweitet - bisher blieben Spaltenüberschriften, Formularfeld-Bezeichnungen und
  Statuswerte auf Listen-/Detailseiten Deutsch, obwohl die übrige Oberfläche bereits ins Englische umschaltete.
  Zusätzlich wurden dabei mehrere veraltete ("fuzzy") Übersetzungen korrigiert, die durch spätere Textänderungen
  inhaltlich nicht mehr zum zugehörigen Text passten (z. B. "Vorstand abgleichen" zeigte "Sync members" statt
  "Sync board members").

## 1.47.0
- Englischen Übersetzungskatalog aufgefrischt: "Hilfe" fehlte komplett (übersetzte seit einiger Zeit nicht
  nach "Help"), weitere ~25 seit den letzten Funktionen neu hinzugekommene Oberflächentexte waren noch
  unübersetzt, und mehrere "fuzzy" markierte Einträge trugen versehentlich die Übersetzung eines anderen,
  inhaltlich unpassenden Textes (z. B. "Vorstand abgleichen" zeigte "Sync members" statt "Sync board members").

## 1.46.6
- Fix: Der Benutzername-Anzeige ("admin") neben den Menü-Icons fehlte die Bootstrap-Klasse `navbar-text` -
  dadurch bekam sie weder die automatisch berechnete Kontrastfarbe noch den Schriftschatten der übrigen
  Navigationselemente.

## 1.46.5
- Die versuchsweise pro Karte wechselnde Farbe (Kartenkopf, Icon-Badges, Kennzahlen-Karten im Dashboard)
  wieder entfernt - Karten und Tabellen sehen jetzt wieder überall einheitlich in der Hauptfarbe aus statt
  reihum zwischen den 3 Vorgabefarben zu wechseln.

## 1.46.4
- Fix: Tabellenköpfe wechselten durch die vorige Änderung je nach Karte die Farbe - mehrere Tabellen
  untereinander auf einer Seite wirkten dadurch uneinheitlich. Jetzt wieder bewusst immer dieselbe
  (Haupt-)Farbe für alle Tabellenköpfe, unabhängig von der (weiterhin dekorativ wechselnden) Kartenfarbe.

## 1.46.3
- Fix: Tabellenkopf nutzt wieder dieselbe Kartenfarbe wie der Kartenkopf darüber (statt immer die Hauptfarbe
  zu zeigen) - sonst wirkten Kartenkopf und Tabellenkopf innerhalb derselben Karte farblich inkonsistent.
- Fix: Tabellen ohne Kartenkopf davor (z. B. Listenansichten) hatten eckige obere Ecken, die über die
  abgerundete Karte hinausragten - übernehmen jetzt auch oben die Kartenrundung.

## 1.46.2
- Die kräftig vollflächig eingefärbten Tabellenköpfe aus der letzten Version wurden als zu grell empfunden -
  zurückgenommen auf die blasse Abtönung. Tabellenköpfe sind jetzt außerdem bewusst immer einheitlich in der
  Hauptfarbe statt pro Karte zwischen den 3 Vorgabefarben zu wechseln.

## 1.46.1
- Fix: Die Kontrastberechnung (welche Schrift-/Icon-Farbe zu einer gewählten Akzentfarbe passt) nutzte eine
  einfache RGB-Helligkeitsformel, die bei gesättigten Farben (v. a. Blau-/Rottönen) öfter die schlechter
  lesbare Variante wählte. Jetzt die genauere WCAG-Leuchtdichteformel. Navigationstext bekommt zusätzlich
  einen dezenten Schriftschatten für mehr Kontur bei mittelhellen Farben.

## 1.46.0
- Fix: sichtbare Kante zwischen Logo- und Menü-Band der Navigationsleiste entfernt (Schatten sitzt jetzt am
  gesamten Leisten-Block statt an beiden Bändern einzeln).
- Die Text-/Icon-Kontrastfarbe im Menü-Band wird jetzt eigens anhand von Akzentfarbe 1 berechnet statt die
  des Logo-Bands (Hauptfarbe) zu übernehmen - beide Bänder bleiben so unabhängig voneinander gut lesbar.
- Tabellenköpfe nutzen jetzt denselben kompakten Label-Stil (klein, Großbuchstaben, dezent) wie die
  Stammdaten-Sidebar auf Detailseiten, eingefärbt mit der jeweiligen Kartenfarbe - einheitlichere Typografie
  statt unterschiedlich wirkender Überschriften je nach Stelle in der Oberfläche.

## 1.45.3
- Werte in der Stammdaten-Sidebar (Detailseiten) wirkten neben den gut lesbaren, dezenten Labels zu generisch -
  jetzt kräftiger/dunkler statt normalem Fließtext, für mehr Kontrast zum Label darüber.

## 1.45.2
- Logo-Band der Navigationsleiste hat wieder den Farbverlauf (war nach dem Umbruch-Fix versehentlich auf eine
  flache Farbe reduziert worden).
- Kartenköpfe, ihre Icon-Badges und die Tabellenköpfe darin wechseln sich jetzt reihum zwischen den 3
  Vorgabefarben (Haupt-/Akzentfarbe 1/Akzentfarbe 2) ab statt überall nahezu gleich auszusehen - bewusst hell
  gehalten.
- Fix: Tabellen am unteren Ende einer Karte (ohne Fußzeile danach) hatten eckige Ecken, die über die
  abgerundete Karte hinausragten - übernehmen jetzt die Kartenrundung, horizontales Scrollen bleibt erhalten.

## 1.45.1
- Fix: Das Menü-Band der zweigeteilten Navigationsleiste saß ab Desktop-Breite fälschlich neben statt unter dem
  Logo-Band (`navbar-expand-lg` erzwingt dort sonst `flex-wrap: nowrap` für die klassische einzeilige Navbar).
  Außerdem war der Farbverlauf im oberen Band nicht sauber, dort jetzt eine einfache Flächenfarbe statt Verlauf.

## 1.45.0
- Navigationsleiste in zwei Bändern: oben Logo/Vereinsname mit Farbverlauf von der Haupt- zur ersten
  Akzentfarbe, darunter das Menü in der unteren Verlauffarbe weitergeführt und mit einer Akzentlinie
  (Akzentfarbe 2) abgeschlossen.

## 1.44.2
- "Feuerix"-Schriftzug (Produktname-Badge) aus der Navigationsleiste entfernt - dort steht jetzt nur noch
  Logo und Vereinsname. Logo in der Navigationsleiste weiter vergrößert (44px → 56px).

## 1.44.1
- Nachbesserungen am Weboberflächen-Design nach Feedback: Farbverlauf in Buttons wieder entfernt (wirkte dort
  unruhig, die Navigationsleiste behält ihren Verlauf), dafür spürbarer Tiefeneffekt für alle Buttons
  (Schatten + dezentes Hochglanz-Highlight statt reiner Flat-Optik). Fließtext-Links nutzen jetzt die
  dunklere, kontrastsichere Farbvariante statt der rohen Akzentfarbe (vermeidet grelle/schwer lesbare
  Linktexte z. B. bei hellen Akzentfarben). Dashboard bekommt einen Begrüßungsbereich mit Farbverlauf,
  Datum und dekorativem Icon statt einer nackten Überschrift; Kennzahlen-Karten wechseln sich jetzt farblich
  ab statt überall dieselbe Akzentfarbe zu zeigen; dezentes Punktraster im Seitenhintergrund und farbige
  Icon-Badges in allen Kartenköpfen sorgen für mehr visuelle Tiefe.

## 1.44.0
- Weboberfläche optisch aufgewertet: Farbverläufe statt flacher Farben (Navigation, Schaltflächen,
  Kennzahlen-Karten, Kartenköpfe), tiefere Schatten und ein deutlicherer Hover-Effekt auf Karten. Neues Modell
  mit einer Hauptfarbe und zwei Akzentfarben (Akzentfarbe 1 für Farbverläufe, Akzentfarbe 2 für
  Icon-Hervorhebungen/Überschriften, Standard: Leuchtgelb) - alle serverseitig berechnet, damit die jeweilige
  Text-/Icon-Farbe darauf auch bei sehr hellen Akzentfarben automatisch kontrastreich bleibt. Logo und
  Vereinsname in der Navigationsleiste sind jetzt größer.

## 1.43.0
- Neues Feld "Akzentfarbe (Weboberfläche)": Dokumente (Briefe/PDFs/Word) und die Weboberfläche lassen sich
  jetzt unabhängig voneinander einfärben, statt zwingend dieselbe Akzentfarbe zu teilen. Bleibt das neue Feld
  leer, gilt weiterhin die Farbe der Dokumente - bestehendes Verhalten ändert sich also nicht automatisch.

## 1.42.0
- Standard-Akzentfarbe (Weboberfläche, Briefe, PDFs) ist jetzt ein Feuerwehrrot (#AF2B1E) statt Blau. Unter den
  Farbfeldern in den Vereinseinstellungen steht zusätzlich eine Klick-Vorauswahl gängiger Feuerwehr-Farben
  (zwei Rottöne, Schwarz, Anthrazit, Leuchtgelb, Dunkelblau) zur Verfügung - jede Farbe bleibt frei editierbar.

## 1.41.2
- Fix: Auswahlfeld und Buttons für "Lagerort (Ist)" bei der Inventur hingen am rechten Rand einer sehr breiten
  Spalte, mit großer Lücke zur Spaltenüberschrift - jetzt linksbündig direkt neben "Ergebnis".

## 1.41.1
- Inventur: "Lagerort (Ist)" ist jetzt ein Auswahlfeld mit den angelegten Lagerorten statt eines Freitextfelds
  (konsistent mit der Lagerort-Auswahl beim Gegenstand selbst).

## 1.41.0
- Inventur: je Position lässt sich jetzt zusätzlich der tatsächlich vorgefundene "Lagerort (Ist)" erfassen
  (eigenes Feld neben "Lagerort (Soll)"); ein Speichern-Knopf sichert den Lagerort auch ohne Änderung des
  Ergebnisses.
- Fix: Klick auf ✓/✗/⚠ bei der Inventur sprang bisher immer an den Seitenanfang zurück - die Seite springt
  jetzt wieder zur jeweils bearbeiteten Position.

## 1.40.0
- Inventar-Reservierung für Veranstaltungen: „Inventar reservieren“ auf der Veranstaltungsseite öffnet jetzt
  die Mehrfachauswahl (Sammelverleih) statt eines Formulars pro Gegenstand - mehrere Gegenstände lassen sich
  auf einmal ankreuzen. Ein Entleiher ist dabei nicht mehr nötig, da der Verein selbst reserviert.

## 1.39.2
- Schriftgröße von Bezeichnung und Lagerort auf dem Etikett erhöht (7/6 pt → 9/8 pt) - wirkten im Vergleich
  zur Inventarnummer unnötig klein.

## 1.39.1
- Sehr flache/breite Etiketten (z. B. nach dem automatischen Drehen schmaler, hoher Etiketten) zeigen QR-Code
  und Text jetzt nebeneinander statt untereinander - sonst wäre der QR-Code durch die geringe Höhe unnötig
  klein geraten.

## 1.39.0
- "Standort" im Inventar in "Lagerort" umbenannt (Modell, Feld, Navigation, Import-Spalte, Etikettendruck,
  Beispieldaten, Handbuch) - per Migration (RenameModel/RenameField), bestehende Daten/Zuordnungen bleiben
  erhalten. Der Inventar-Import erkennt weiterhin auch die alte Spaltenüberschrift „Standort“.

## 1.38.1
- Fix: bei schmalen, hohen Etiketten blieb eine grosse ungenutzte Luecke zwischen QR-Code und Text (Textblock
  wurde prozentual zur Etikettenhoehe statt absolut berechnet). QR-Code + Text werden jetzt als Einheit
  zentriert, bei deutlich hoeheren als breiten Etiketten wird der Inhalt zusaetzlich automatisch um 90°
  gedreht. Ausserdem wird jetzt - sofern gepflegt - der Standort mit aufs Etikett gedruckt.

## 1.38.0
- Etikettengröße und -raster für den Inventar-Etikettendruck sind jetzt unter Vereinseinstellungen frei
  konfigurierbar (Breite/Höhe, Spalten/Zeilen). Bei 1 Spalte × 1 Zeile wird die PDF-Seite exakt auf die
  Etikettengröße zugeschnitten statt auf A4 - damit lässt sich z. B. ein Dymo LabelWriter 450 mit
  Endlosrolle direkt bedrucken.

## 1.37.0
- Familien-Detailseite zeigt jetzt direkt die Mitglieder der Familie und bietet ein Auswahlfenster, um
  bestehende aktive Mitglieder per Mehrfachauswahl zuzuordnen (zusaetzlich zum bisherigen Weg ueber die
  einzelne Mitgliederakte bzw. das Anlegeformular mit vorbelegter Familie).

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
