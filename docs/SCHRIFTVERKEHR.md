# Anleitung: Briefe, Serienbriefe, Protokolle, Vorlagen und Ablage

> Teil des [Handbuchs](HANDBUCH.md) – siehe dort Kapitel 11 für den Gesamtüberblick inkl. Corporate Design.

## Vereinslogo

*Verwaltung › Verein / Einstellungen / Logo* → Feld **Vereinslogo** (PNG oder JPG). Das Logo steht danach oben rechts auf
allen PDF-Dokumenten (Briefe, Serienbriefe, Rechnungen, Mahnungen, Leihscheine, Spendenquittungen) und im Word-Export und
neben dem Vereinsnamen in der Kopfzeile. Wechsel: neue Datei hochladen. Entfernen: „Löschen“ ankreuzen.
Für den Verein gibt es ein eigenes Logo. Die Zeilen **Unterschrift 1/2** füllen die Platzhalter `{unterschrift_1}` / `{unterschrift_2}`.

## Vorlagen (frei bearbeitbar)

*Schriftverkehr › Vorlagen*. Mitgeliefert sind u. a.: Einladung Mitgliederversammlung / Vorstandssitzung / Veranstaltung,
Protokoll Mitgliederversammlung / Vorstandssitzung, Mitgliederinformation, Information zum Mitgliedsbeitrag, Glückwunsch zum
Jubiläum, Zugangsdaten OpenSlides, Brief allgemein. Jede Vorlage kann geändert, kopiert (neuer Name) oder neu angelegt werden.

* **Art** bestimmt, wofür sie angeboten wird; **Standardvorlage** wird bei „Einladung/Protokoll erstellen“ in einer
  Veranstaltung verwendet.
* Absätze durch eine **Leerzeile** trennen; einfache Zeilenumbrüche bleiben erhalten.
* Platzhalter wie `{briefanrede}`, `{name}`, `{veranstaltung_datum}`, `{tagesordnung}` siehe **Platzhalter-Hilfe**.
* „Standardvorlagen nachladen“ ergänzt fehlende Mustervorlagen, ohne geänderte zu überschreiben.
* Bitte Einladungsfristen und Formvorschriften mit der **Satzung** abgleichen – die Mustertexte sind nur Vorschläge.

## Einzelne Schriftstücke (Einladung, Protokoll, Brief)

* Aus einer **Veranstaltung**: Buttons „Einladung erstellen“ / „Protokoll erstellen“ – der Entwurf entsteht aus der
  Standardvorlage mit den Daten der Veranstaltung und der Tagesordnung.
* Oder frei: *Schriftverkehr › Schriftstücke › Neu*, Vorlage wählen (Text wird übernommen und ist danach frei änderbar).
* Auf der Detailseite: **PDF ansehen**, **Word (.docx)** zum Weiterbearbeiten, **Als PDF in Ablage speichern**.
* Nicht ersetzbare Platzhalter werden als Hinweis angezeigt.

## Empfängeranschrift

Jedes Schriftstück (Anschreiben) hat das Feld **„Empfängeranschrift (manuell)“**: eine Zeile je Adresszeile (Name, Straße, PLZ Ort). Ist
es ausgefüllt, steht dieser Text als Anschrift im Brief (PDF und Word) – **auch ohne Mitglied** (z. B. für Behörden, Firmen, Gäste) – und hat
Vorrang vor der Anschrift eines gewählten Mitglieds. Ohne Mitglied lautet die Anrede-Platzhalter `{briefanrede}` dann „Sehr geehrte Damen
und Herren,“. Protokolle haben keine Anschrift. Bei Rechnungen und Spendenquittungen lässt sich der Empfänger ebenfalls manuell eintragen
(„Empfänger/Anschrift“ bzw. „Anschrift falls kein Mitglied“).

## Formatierter Text (Editor)

Der Text von Vorlagen, Schriftstücken und Serienbriefen wird in einem **Editor** (TinyMCE) bearbeitet – wie in einem Textprogramm:
Absatz/Überschrift 1–3, **fett**, *kursiv*, unterstrichen, links/zentriert/rechts/Blocksatz, Aufzählungen und nummerierte Listen,
Einrücken, **Tabellen**, Links, Sonderzeichen und „Formatierung entfernen“. Über **„{ } Platzhalter“** in der Leiste lassen sich
Platzhalter wie `{vorname}` aus einer nach Themen gegliederten Liste einfügen (siehe Seite *Platzhalter-Hilfe*).

- Es werden nur Formatierungen angeboten, die auch im **PDF**, im **Word-Export** und in der **E-Mail** ankommen (Serienbrief-E-Mails
  enthalten den Text als Klartext und zusätzlich formatiert als HTML-Teil). Schriftart und -größe bestimmt das Layout der Vorlage.
- **Alte Vorlagen und Texte** (reiner Text mit Leerzeilen) funktionieren unverändert; beim Öffnen im Editor werden sie in Absätze
  umgewandelt und erst beim Speichern in der neuen Form abgelegt.
- Der eingegebene Text wird beim Speichern **bereinigt** (nur die genannten Formatierungen und sichere Links bleiben).
- Der Editor ist lokal eingebunden (kein Cloud-Dienst); TinyMCE steht unter der GPL (siehe README).

## Layout einer Vorlage

Jede Vorlage hat im Formular zwei Abschnitte **„Layout“**, die bestimmen, wie die daraus erzeugten PDFs aussehen (Schriftstücke und
Serienbriefe, die mit dieser Vorlage angelegt wurden; Rechnungen, Mahnungen usw. behalten ihr festes Aussehen):

- **Briefkopf:** Name und Logo mit Trennlinie (Standard), nur Name, nur Logo oder **kein Briefkopf** für vorgedrucktes Briefpapier –
  dann bleibt auf der ersten Seite der Rand oben (Standard 45 mm) frei. **Logo links oder rechts.**
- **Absenderzeile** (kleine Rücksendeangabe über der Anschrift, für Fensterumschläge) an/aus, **Datum** links oder rechts, **Fußzeile**
  mit Vereinsangaben, nur Seitenzahl oder keine.
- **Schrift:** Helvetica, Times oder Courier, Größe 8 bis 14 pt. **Ränder** links, rechts, unten (und oben bei „kein Briefkopf“) in mm.

Auf der Vorlagen-Detailseite zeigt **„Layout-Vorschau (PDF)“** ein Beispiel-PDF mit Beispielempfänger. Die Standardwerte entsprechen dem
bisherigen Aussehen. Der Word-Export (.docx) übernimmt das Layout nicht.

## Serienbriefe

1. *Schriftverkehr › Serienbriefe › Neu* (oder in einer Veranstaltung „Einladung an Mitglieder (Serienbrief)“).
2. Vorlage wählen, Text anpassen, **Empfängerkreis** festlegen (Status, Mitgliedsart, Abteilung, Funktion, nur mit E-Mail).
3. **Versand** wählen: *E-Mail an Mitglieder mit E-Mail-Adresse, alle übrigen per Post* (Standard bei Einladungen aus einer
   Veranstaltung), *Alle per Post*, *Nur per E-Mail* oder *Brief für alle, E-Mail zusätzlich möglich* (bisheriges Verhalten).
4. Detailseite: Empfängerzahl kontrollieren (Zähler „Per E-Mail / Per Post“, Spalte „Versand“ in der Empfängerliste), **Vorschau** ansehen
   (erster Empfänger).
5. **Briefe erzeugen & in Ablage speichern** bzw. **Briefe für den Postversand als PDF** – ein PDF, ein Brief je Mitglied (jeder mit Logo
   und persönlicher Anrede) → zum Druck; bei „E-Mail … übrige per Post“ nur für die Mitglieder **ohne** E-Mail-Adresseen.
6. **Per E-Mail senden** – Text im Mailtext, Brief als PDF-Anhang, an alle Empfänger mit E-Mail-Adresse (im Hintergrund).
   Das Ergebnis (Anzahl versendet/Fehler/ohne Adresse) steht auf der Detailseite.

## Ablage

*Schriftverkehr › Ablage* und *Ablage-Ordner*. Ordner-Struktur wird beim Anlegen des Vereins erzeugt
(Protokolle, Einladungen, Serienbriefe, Satzung & Verträge, Belege, Sonstiges) und automatisch nach **Jahr** unterteilt.

* Aus dem System erzeugte PDFs landen automatisch im passenden Ordner (Kategorie/Jahr).
* **Externe Dokumente hochladen:** Die Ablage ist nicht auf in dieser Software erzeugte Dokumente beschränkt –
  über *Schriftverkehr › Ablage › „Neu“* lässt sich eine beliebige, extern erstellte Datei hochladen (PDF, Word,
  eingescannte Satzung/Protokolle, Fotos …) und mit Titel, Kategorie, Ordner, Datum, Beschreibung und Tags
  versehen; optional der Veranstaltung zuordnen.
* **Versionierung:** gleicher Titel im gleichen Ordner → neue Version; frühere Versionen bleiben erhalten und sichtbar.
* Der Zugriff auf Dateien läuft nur über die Anwendung (Anmeldung + Vereinszugehörigkeit + Recht „Ablage“).
* Rechte: Module „Ablage“ und „Schriftverkehr“ – über die Berechtigungsmatrix bzw. Tags vergeben (Schriftführer
  hat laut Datenschutzordnung Bearbeitungsrechte, siehe Handbuch Kapitel 2).

## Empfohlener Ablauf einer Mitgliederversammlung

1. Veranstaltung anlegen (Art „Versammlung“), Tagesordnung erfassen (oder „Standard-Tagesordnung“).
2. „Einladung erstellen“ → prüfen → PDF; „Einladung an Mitglieder (Serienbrief)“ → drucken/mailen. Fristen der Satzung beachten!
3. Optional online/hybrid: „In OpenSlides anlegen“, Konten abgleichen, Zugangsdaten per Serienbrief verteilen.
4. Nach der Versammlung: „Protokoll erstellen“, ausfüllen (Word-Export möglich), unterschriebenes Protokoll als Scan in die Ablage.
5. Beschlüsse/Ehrungen weiterverarbeiten (Ehrungen, Beitragsänderungen).
