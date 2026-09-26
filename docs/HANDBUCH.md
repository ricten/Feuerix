# Handbuch – Feuerix (Version 1.23.0)

Dieses Handbuch beschreibt die Bedienung von Feuerix, der Vereinsverwaltung für Feuerwehr-Fördervereine, für
Vorstand, Kassenwart, Schriftführer und alle anderen Nutzer:innen im Verein. Es ergänzt die technischen Dokumente
[README.md](../README.md) (Überblick, Installation) und [INSTALL.md](../INSTALL.md)
(Schritt-für-Schritt-Einrichtung auf dem Server) um die tägliche Arbeit mit der Software.

Für einzelne Themen gibt es vertiefende Dokumente, auf die im jeweiligen Kapitel verwiesen wird:
[Selbstdatenpflege](SELBSTDATENPFLEGE.md), [Kasse & Mitglieder-Import](KASSE_UND_IMPORT.md),
[Schriftverkehr & Vorlagen](SCHRIFTVERKEHR.md).

Die aktuell laufende Version steht im Footer jeder Seite (z. B. „Version 1.0.0“) – praktisch, wenn Sie beim
Support eine Fehlermeldung schildern.

## Inhalt

1. [Anmeldung, Oberfläche, mehrere Vereine](#1-anmeldung-oberfläche-mehrere-vereine)
2. [Rollen und Rechte](#2-rollen-und-rechte)
3. [Mitgliederverwaltung](#3-mitgliederverwaltung)
4. [Beiträge, Rechnungen und Zahlungen](#4-beiträge-rechnungen-und-zahlungen)
5. [Kassenbuch und Kassenbericht](#5-kassenbuch-und-kassenbericht)
6. [Inventar und Verleih](#6-inventar-und-verleih)
7. [Spenden und Spendenquittungen](#7-spenden-und-spendenquittungen)
8. [Aufwandsentschädigungen](#8-aufwandsentschädigungen)
9. [Veranstaltungen](#9-veranstaltungen)
10. [Ehrungen und Jubiläen](#10-ehrungen-und-jubiläen)
11. [Schriftverkehr, Vorlagen, Ablage und Corporate Design](#11-schriftverkehr-vorlagen-ablage-und-corporate-design)
12. [OpenSlides-Anbindung](#12-openslides-anbindung)
13. [Paperless-ngx-Anbindung](#13-paperless-ngx-anbindung)
14. [Auswertungen und Änderungsprotokoll](#14-auswertungen-und-änderungsprotokoll)
15. [Vereinseinstellungen](#15-vereinseinstellungen)
16. [Datenschutz und Sicherheit](#16-datenschutz-und-sicherheit)
17. [Bekannte Grenzen](#17-bekannte-grenzen)

---

## 1. Anmeldung, Oberfläche, mehrere Vereine

Nach der Anmeldung landen Mitarbeiter:innen mit einem Verwaltungszugang auf dem **Dashboard** (Mitgliederzahlen,
Beitragsstand des laufenden Jahres, anstehende Jubiläen/Ehrungen, überfällige Ausleihen, nächste Termine, offene
Aufgaben und Aufwandsanträge). Mitglieder, die nur einen Selbstdatenpflege-Zugang haben (siehe Kapitel 3), landen
stattdessen direkt auf „Mein Konto“.

Hat ein Benutzer Zugang zu **mehreren Vereinen**, erscheint oben rechts eine Auswahlliste, mit der zwischen den
Vereinen gewechselt wird. Jede Ansicht, jede Liste und jeder Export zeigt ausschließlich Daten des gerade
ausgewählten Vereins – die Vereine sind vollständig getrennt (Mandantenfähigkeit).

**Hinweis:** Das Anlegen eines *weiteren* Vereins über `/admin/` ist aktuell gesperrt, solange bereits einer
existiert – das Mehrmandanten-Setup ist für den produktiven Einsatz derzeit nicht freigegeben. Bereits bestehende
Installationen mit mehreren Vereinen sind davon nicht betroffen.

Die Navigation oben ist nach Themen gruppiert (Mitglieder, Schriftverkehr, Finanzen, Kasse, Inventar,
Veranstaltungen, Auswertung, Verwaltung) und zeigt nur die Punkte, für die die eigene Rolle mindestens Lesezugriff
hat.

**Sprache:** Oben rechts in der Menüleiste (auch auf der Anmeldeseite, vor dem Einloggen) lässt sich zwischen
**Deutsch** und **Englisch** wechseln. Die Auswahl wird in einem Cookie gespeichert und gilt browserweit, bis sie
erneut geändert wird. Übersetzt sind aktuell die Navigation, An-/Abmeldung, das Dashboard, die
Listen-/Detail-/Formularseiten (Buttons, Filter, Meldungen) sowie alle eigenständigen Spezialseiten (z. B.
Jubiläen, Auswertungen, Import-Assistenten, OpenSlides-/Paperless-Einstellungen); die fachlichen Feldnamen der
einzelnen Module (z. B. Formularfelder eines Mitglieds) folgen nach und nach.

**Listen sortieren:** In jeder Tabelle lässt sich auf eine Spaltenüberschrift klicken, um danach zu sortieren
(Pfeil zeigt die Richtung); ein zweiter Klick kehrt die Richtung um. Das funktioniert für alle Spalten, die ein
echtes Datenfeld abbilden (nicht für rein berechnete Spalten wie z. B. „Entleiher“ in der Verleih-Liste).

## 2. Rollen und Rechte

Jeder Benutzerzugang (*Verwaltung › Benutzer*) bekommt pro Verein eine **Rolle** zugewiesen (*Verwaltung › Rollen*).
Eine Rolle legt fest, welche Module ein Zugang **anzeigen**, **erstellen**, **bearbeiten** oder **löschen** darf.
Bei Bedarf können einem einzelnen Zugang zusätzlich individuelle Extra-Rechte gegeben werden.

Mitgelieferte Standardrollen:

| Rolle | Typischer Einsatz | Volle Rechte (inkl. Anlegen/Bearbeiten) | Nur Lesen |
|---|---|---|---|
| **Superadministrator** | Technische Betreuung | Alles, inkl. Benutzer/Rollen/Vereinseinstellungen | – |
| **Vorstand** | Vorsitz | Mitglieder, Ehrungen, Dokumente, Beiträge, Rechnungen, Veranstaltungen, Schriftverkehr, Ablage, Selbstdatenpflege-Verwaltung; darf zusätzlich Aufwandsanträge genehmigen | Zahlungen, Spenden, Aufwand, Inventar, Verleih, Inventuren, Auswertungen, OpenSlides, Kassenbuch |
| **Kassenwart** | Kassenführung | Beiträge, Rechnungen, Zahlungen, Bankumsätze, Spenden, Aufwand, Kassenbuch (inkl. Löschen/Wiedereröffnen) | Mitglieder, Auswertungen, Ablage |
| **Kassenprüfer** | Jährliche Prüfung | – | Kassenbuch, Rechnungen, Zahlungen, Bankumsätze, Spenden, Aufwand, Beiträge, Ablage, Auswertungen |
| **Schriftführer** | Protokolle/Schriftverkehr | Mitglieder, Ehrungen, Dokumente, Veranstaltungen, Schriftverkehr, Ablage | – |
| **Inventarverwalter** | Gerätewart | Inventar, Verleih, Inventuren | Mitglieder, Veranstaltungen |
| **Veranstaltungsplaner** | Eventorganisation | Veranstaltungen, Verleih | Mitglieder, Inventar |
| **Mitgliederverwaltung** | Selbstdatenpflege-Betreuung | Selbstdatenpflege-Zugänge (inkl. Löschen) | Mitglieder |
| **Lesebenutzer** | z. B. Beisitzer:in | – | breiter Lesezugriff, aber **ohne** Verwaltung, Änderungsprotokoll, Bankumsätze, Aufwand, Spenden, OpenSlides, Kassenbuch, Selbstdatenpflege |

Wichtig: **Nur der Superadministrator** hat standardmäßig Rechte auf das Modul „Verwaltung“ (Benutzer, Rollen,
Vereinseinstellungen, „Verwaltungszugang einrichten“ bei einem Mitglied). Wer weiteren Personen diese Aufgabe
übertragen möchte, muss ihnen eine eigene Rolle mit dem Recht `verwaltung` geben oder sie zum Superadministrator
machen.

## 3. Mitgliederverwaltung

Unter *Mitglieder* werden Personendaten, Anschrift, Bankverbindung (SEPA), Mitgliedsart, Familienzugehörigkeit,
Abteilungen und ausgeübte Funktionen (z. B. „1. Vorsitzender“, mit Zeitraum) gepflegt. Die Mitgliedsnummer wird
automatisch vergeben, kann aber auch manuell gesetzt werden.

**Import/Export**: Über *Verwaltung › Mitglieder-Import* (nicht auf der Mitgliederliste selbst, da meist nur einmalig
beim Einrichten des Vereins benötigt) lässt sich eine Tabelle einlesen – mit **Testlauf** (nichts wird gespeichert,
nur geprüft), Abgleich bestehender Mitglieder über Mitgliedsnummer bzw. Vorname+Nachname+Geburtsdatum, und der
Option, unbekannte Mitgliedsarten/Abteilungen automatisch anzulegen. Eine Vorlage mit Beispielzeile und Hinweisen
steht zum Download bereit. „Vollexport (Excel)“ auf der Mitgliederliste exportiert alle Mitglieder, optional inkl.
Bankdaten (nur mit Beitragsrecht).

**Auf der Mitglieder-Detailseite** (je nach eigenen Rechten):
- „Datenauskunft (JSON)“ – vollständige DSGVO-Auskunft inkl. Rechnungen, Zahlungen, Spenden, Aufwand, Ehrungen,
  Dokumenten.
- „Anonymisieren“ – löscht personenbezogene Daten, Foto und Dokumente unwiderruflich; Rechnungen bleiben aus
  steuerlichen Aufbewahrungsgründen bestehen. Nur möglich mit Löschrecht auf Mitglieder. Hat das Mitglied ein
  verknüpftes **OpenSlides-Konto**, wird es dabei ebenfalls angepasst (Name/Benutzername/E-Mail überschrieben,
  Konto deaktiviert) – nicht nur lokal deaktiviert. Ist die OpenSlides-Anbindung nicht erreichbar oder nicht
  eingerichtet, erscheint eine Warnung mit der Bitte, das Konto dort manuell zu prüfen; die lokale Anonymisierung
  wird davon unabhängig trotzdem durchgeführt.
- „Zugangsdaten für Selbstdatenpflege senden“ / „Zugang sperren“ / „Startpasswort löschen“ – siehe
  [Selbstdatenpflege](SELBSTDATENPFLEGE.md).
- „Verwaltungszugang einrichten“ – richtet direkt aus dem Mitglied heraus einen vollwertigen
  Verwaltungszugang mit Rolle ein (statt über *Verwaltung › Benutzer*), siehe ebenfalls
  [Selbstdatenpflege](SELBSTDATENPFLEGE.md). Braucht das Recht `verwaltung`.

Auf der Detailseite erscheinen außerdem – abhängig von den eigenen Rechten – Unterlisten mit Beiträgen/Rechnungen,
Funktionen, Ehrungen, Dokumenten, Verleihvorgängen, Spenden und Aufwandsentschädigungen des Mitglieds.

## 4. Beiträge, Rechnungen und Zahlungen

**Beitragslauf**: Unter *Finanzen › Beitragsjahre* wird einmal pro Jahr ein **Beitragsjahr** angelegt (Fälligkeit,
Stichtag für Altersregeln). Der Button „Beitragsrechnungen erzeugen“ erstellt für alle beitragspflichtigen
Mitglieder (aktiv/ruhend im betreffenden Zeitraum) automatisch eine Rechnung – Betrag nach Priorität: individueller
Beitrag des Mitglieds > erste passende Beitragsregel (*Verwaltung › Beitragsregeln*, z. B. Alters- oder
Familienstaffelungen) > Standardbeitrag der Mitgliedsart. Mitglieder ohne Beitrag/Regel werden namentlich als
übersprungen gemeldet. Der Beitragslauf lässt sich gefahrlos mehrfach anstoßen – wer schon eine Rechnung für das
Jahr hat, wird nicht doppelt berechnet. **Hinweis:** Es wird immer der volle Jahresbeitrag berechnet, keine
anteilige Berechnung bei unterjährigem Eintritt.

**Rechnungen** (auch einzeln/individuell oder als Sammelrechnung anlegbar) durchlaufen die Stationen *Entwurf* →
*Ausstellen* (vergibt die endgültige Nummer `RE-JJJJ-000001`, danach unveränderbar) → *Offen* → *Teilbezahlt/
Bezahlt*. Auf der Rechnung stehen je nach Status und Recht: „PDF“, „E-Rechnung (ZUGFeRD-PDF)“ (nur bei
ausgestellten Rechnungen), „Ausstellen“, „Per E-Mail senden“, „Storno“, „Mahnung erzeugen“, „Zahlung erfassen“
(Betrag ist mit dem offenen Betrag vorbelegt).

**Umsatzsteuer** (für nicht gemeinnützige Vereine bzw. den wirtschaftlichen Geschäftsbetrieb): Unter *Verwaltung ›
Verein/Einstellungen* lässt sich „Umsatzsteuerpflichtig“ aktivieren – neue Rechnungspositionen schlagen dann 19 %
als Steuersatz vor, jede Position hat aber weiterhin ihren **eigenen** Umsatzsteuersatz (0 % für z. B. den
ideellen Bereich, 19 %/7 % für den wirtschaftlichen Geschäftsbetrieb) und kann so auch gemischt auf einer
Rechnung stehen. Sobald eine Rechnung Umsatzsteuer enthält, zeigen PDF und E-Rechnung automatisch die
Aufschlüsselung Netto/Steuer/Brutto; ohne Umsatzsteuerpflicht und ohne gesetzten Steuersatz bleibt die Rechnung
unverändert wie bisher eine einfache Betragsspalte. Ein eigener **Steuerhinweis** (z. B. „Gemäß § 19 UStG wird
keine Umsatzsteuer berechnet“) lässt sich ebenfalls in den Vereinseinstellungen hinterlegen; ohne eigenen Text
erscheint bei 0 % weiterhin der Standardhinweis „Steuerbefreiung nach § 4 UStG (ideeller Bereich)“. Eine
**USt-IdNr.** kann dort ebenfalls gepflegt werden (erscheint dann in der E-Rechnung). Das ersetzt keine steuerliche
Beratung – insbesondere die Frage, welche Vereinstätigkeiten tatsächlich umsatzsteuerpflichtig sind, bitte mit
Steuerberater/Finanzamt klären.

**E-Rechnung (ZUGFeRD-PDF)**: erzeugt aus der Rechnung eine ZUGFeRD/Factur-X-Datei (Profil EN16931) zum Download –
das ist die normale PDF-Rechnung mit einer zusätzlich eingebetteten, maschinenlesbaren XML-Datei. Gedacht für den
seltenen Fall, dass eine Rechnung an eine Stelle mit E-Rechnungspflicht (z. B. eine Behörde oder ein Unternehmen)
geht; das PDF lässt sich wie gewohnt öffnen und ausdrucken, E-Rechnungs-fähige Buchhaltungssysteme lesen zusätzlich
die eingebettete XML aus. Die eingebettete XML wird beim Erzeugen automatisch gegen das amtliche EN16931/CII-Schema
(XSD) geprüft – eine echte strukturelle Validierung. **Nicht geprüft** werden die vollständigen
EN16931-Geschäftsregeln (Schematron – dafür wäre zusätzlich ein Java-Prüfwerkzeug bzw. Saxon-Server nötig, bewusst
nicht eingebunden) und die PDF/A-3-Konformität der Trägerdatei selbst (kein veraPDF-Check). Umsatzsteuersätze je
Position (s. o.) werden korrekt als eigene Steuergruppen (auch gemischt) in die E-Rechnung übernommen. Vor dem
Versand an eine Stelle mit E-Rechnungspflicht bitte trotzdem gegen ein offizielles Prüfwerkzeug (z. B. den
KoSIT-Validator) laufen lassen bzw. einen Steuerberater hinzuziehen.

**Storno und Rückzahlung**: „Storno“ erzeugt eine Stornorechnung mit umgekehrtem Vorzeichen; die Originalrechnung
wird als *storniert* markiert. War die Rechnung bereits (teil-)bezahlt, zeigt die Stornorechnung einen Hinweis
„Rückzahlung an den Zahler noch offen“ und einen Button **„Rückzahlung buchen“** – damit wird die tatsächliche
Erstattung an das Mitglied/den externen Zahler als eigene Zahlungsart „Rückzahlung“ erfasst. Diese Buchung landet
später korrekt als **Ausgabe** (nicht als negative Einnahme) im Kassenbuch.

**Bankumsätze**: Kontoauszug importieren – erkannt werden automatisch **CSV** (übliche deutsche
Bank-Exportformate), **MT940** (SWIFT-Kontoauszug, meist `.sta`) und **CAMT.053** (ISO-20022-XML); Duplikate werden
anhand Datum/Betrag/IBAN/Verwendungszweck erkannt und übersprungen. Danach „Automatisch zuordnen“ – die Zuordnung
erfolgt über Rechnungsnummer im Verwendungszweck, sonst über Mitgliedsnummer, sonst über eine eindeutige
IBAN-Übereinstimmung. Rücklastschriften (negative Beträge) werden nur automatisch zugeordnet, wenn der Text
erkennbar danach klingt; sonst „manuell“ zur Nachbearbeitung markiert. **Hinweis:** Bei MT940 wird der
Verwendungszweck (Feld `:86:`) nach den seit der SEPA-Umstellung üblichen deutschen Feldkennungen durchsucht
(`SVWZ+`, `ABWA+`/`ABWE+`, `IBAN+`); weicht eine Bank davon ab, landet der komplette Text unverändert im
Verwendungszweck statt in Einzelfeldern. Ist mindestens ein FinTS-Zugang eingerichtet, erscheint auf dieser Seite
zusätzlich je Zugang ein „Umsätze abrufen“-Knopf als Abkürzung zum FinTS-Abruf (siehe unten).

**FinTS-Abruf** (experimentell, siehe Kapitel 17): Alternative zum manuellen Kontoauszug-Import – unter
*Verwaltung › FinTS-Zugänge* einen oder mehrere Zugänge anlegen (Bezeichnung, Bankleitzahl, Online-Banking-Kennung
und FinTS-Adresse der Bank; diese Angaben stehen in den Unterlagen zum Online-Banking bzw. lassen sich beim
Kreditinstitut erfragen) – ein Verein kann **mehrere Zugänge** führen, z. B. wenn Konten bei verschiedenen Banken
bestehen. Voraussetzung ist außerdem eine kostenlose FinTS-Produkt-ID, die der Betreiber der Instanz einmalig bei
der Deutschen Kreditwirtschaft registriert (wird nicht mit der Software mitgeliefert) und entweder als
Umgebungsvariable oder – verschlüsselt und ohne Serverzugriff änderbar – unter `/admin/` › Systemeinstellungen
hinterlegt (nur für technische Administratoren, nicht Teil der normalen Vereinsverwaltung). Jedes Kassenbuch-Konto
(*Kasse › Konten*) kann optional einem dieser Zugänge zugeordnet werden – Konten ohne Zuordnung laufen
unverändert über den manuellen Kontoauszug-Import weiter.
Auf der Detailseite eines Zugangs steht „Kontodaten abrufen“ (zeigt nur IBAN/BIC der beim Kreditinstitut
hinterlegten Konten – nützlich, um die Verbindung zu prüfen und die richtige Zuordnung zum Kassenbuch-Konto zu
finden, ohne gleich Umsätze zu importieren) sowie „Jetzt abrufen“ für den eigentlichen Umsatz-Abruf. Beides fragt
die PIN ab – verlangt die Bank eine TAN (üblich), erscheint im nächsten Schritt die Bank-Aufforderung (Text, oder
bei chipTAN eine zu scannende Grafik) mitsamt Eingabefeld. Nach Bestätigung werden bei „Jetzt abrufen“ neue
Kontobewegungen genauso wie beim Datei-Import als Bankumsätze angelegt (Duplikate werden übersprungen) und können
anschließend wie gewohnt zugeordnet werden. Die Bank-PIN wird **nie gespeichert**.

**SEPA-Einzüge**: Unter *Finanzen › SEPA-Einzüge* → „Neuen Einzug erstellen“ werden alle offenen/teilbezahlten
Rechnungen von Mitgliedern mit Zahlungsart „SEPA-Lastschrift“ und vollständigem Mandat (IBAN, Mandatsreferenz,
Mandatsdatum) zur Auswahl angezeigt (Betrag = jeweils offener Restbetrag). Nach Angabe des Fälligkeitsdatums
erzeugt die Software eine SEPA-Sammellastschriftdatei (`pain.008`, Format CORE) zum Hochladen ins Online-Banking
der Vereinsbank – dafür müssen IBAN und Gläubiger-ID des Vereins unter *Verwaltung › Verein* hinterlegt sein. Ob
ein Mitglied als Erst- (FRST) oder Folgelastschrift (RCUR) eingezogen wird, ermittelt die Software automatisch
danach, ob es bereits in einem früheren Einzug enthalten war. **Wichtig:** Die Datei enthält nur den Einzugsauftrag
– ob das Geld tatsächlich eingegangen ist (oder als Rücklastschrift zurückkommt), zeigt erst der spätere
Kontoauszug-Import; die Software bucht keine Zahlung automatisch, nur weil ein Einzug erstellt wurde.

## 5. Kassenbuch und Kassenbericht

Ausführlich in [Kasse & Mitglieder-Import](KASSE_UND_IMPORT.md) beschrieben. Kurzfassung: Buchungen werden entweder
manuell erfasst oder per „Aus Zahlungen/Spenden/Veranstaltungen übernehmen“ automatisch aus den anderen Modulen
gezogen (mehrfach anstoßbar, bereits übernommene Vorgänge werden nicht doppelt gebucht). Jede Buchung gehört zu
einem **Konto** (Bank/Bar) und einer **Buchungskategorie**, die wiederum einer der vier steuerlichen **Sphären**
zugeordnet ist (Ideeller Bereich, Vermögensverwaltung, Zweckbetrieb, wirtschaftlicher Geschäftsbetrieb – bitte mit
Steuerberater/Finanzamt abstimmen).

**E-Rechnung importieren**: Über den gleichnamigen Button auf der Kassenbuch-Liste lässt sich eine empfangene
elektronische Rechnung einlesen – als reine XML-Datei (XRechnung) oder als PDF mit eingebetteter XML
(ZUGFeRD/Faktur-X). Rechnungsnummer, Datum, Betrag und Aussteller werden automatisch erkannt und als Ausgabe im
Kassenbuch vorausgefüllt, die Originaldatei wird direkt als Beleg angehängt. Konto und Kategorie danach bitte
prüfen (Standard: erstes Bankkonto, Kategorie „Sonstige Ausgaben“). Wird kein bekanntes Format erkannt, wird die
Datei trotzdem als Beleg abgelegt – die übrigen Angaben dann bitte manuell eintragen.

**Beleg in Ablage übernehmen**: Ein an einer Buchung hochgeladener Beleg (Scan/Foto) liegt zunächst nur an dieser
Buchung selbst und taucht nicht automatisch im allgemeinen Dokumentenarchiv (*Schriftverkehr › Ablage*) auf. Über
den Knopf „Beleg in Ablage übernehmen“ auf der Buchungs-Detailseite lässt er sich bei Bedarf zusätzlich dort
einordnen (Ordner „Belege“/Jahr) – z. B. um ihn zusammen mit anderen Unterlagen wiederzufinden oder an Paperless-ngx
weiterzuleiten. Der Knopf verschwindet danach und ein Hinweis zeigt, wo der Beleg abgelegt wurde.

Ein **Kassenbericht** über einen Zeitraum zeigt Kontenübersicht, Einnahmen/
Ausgaben je Sphäre mit Vorjahresvergleich und einen Soll/Ist-Abgleich mit gezähltem Bargeld-/Kontostand. „Abschließen“
sperrt alle Buchungen im Zeitraum endgültig gegen nachträgliche Änderung (Korrekturen danach nur per
Gegenbuchung) und legt das PDF automatisch in der Ablage ab.

## 6. Inventar und Verleih

**Gegenstände** (*Inventar*) bekommen automatisch eine Inventarnummer (`INV-000001`), einen Zustand
(neu/gut/gebrauchsspuren/defekt/ausgesondert), Kategorie und Standort, optional Kaution/Leihgebühr und ein Häkchen
„Verleihbar“.

**Import**: wie beim Mitglieder-Import – Testlauf, Abgleich über Inventarnummer, unbekannte Kategorien/Standorte
optional automatisch anlegen.

**Etiketten mit QR-Code**: „Etikett drucken“ (einzeln) oder „Etiketten drucken (alle)“ auf der Liste erzeugt ein
PDF mit Aufklebern (Inventarnummer + QR-Code je Gegenstand, mehrere pro A4-Seite). Der QR-Code verweist auf eine
Scan-Adresse im System.

**Verleih starten**:
- *Manuell* über „Verleih / Reservierung anlegen“ auf dem Gegenstand (voller Formular-Umfang, inkl. Kaution/
  Leihgebühr-Anpassung je Ausleihe).
- *Per Scan*: Aufkleber mit dem Handy scannen (angemeldet im System) – der Gegenstand landet im
  **Verleih-Warenkorb**. So lassen sich mehrere Gegenstände nacheinander scannen (z. B. Pavillon, Bänke, Beamer
  für eine Veranstaltung), bevor über „Verleih starten“ **ein gemeinsamer Vorgang** mit einem Formular
  (Entleiher, Zeitraum, Zweck einmal ausfüllen) angelegt wird.
- Über „Mehrere Gegenstände verleihen“ auf der Verleih-Liste lässt sich derselbe Sammel-Vorgang auch ohne Scannen
  per Checkbox-Auswahl starten.

Mehrere gleichzeitig verliehene Gegenstände werden als **Vorgang** verknüpft: von der Vorgangsseite aus lassen sich
alle Positionen gemeinsam ausgeben, gemeinsam zurücknehmen, ein gemeinsamer Leihschein drucken und – siehe unten –
landen auf **einer** gemeinsamen Rechnung statt vieler einzelner.

**Rückgabe erfassen** ist ein Formular (einzeln wie im Vorgang): pro Gegenstand wird der **Zustand bei Rückgabe**
gewählt (wirkt sich sofort auch auf den Gegenstand selbst aus, damit die Inventarübersicht stimmt) und – falls eine
Kaution hinterlegt ist – ob sie **zurückgezahlt** oder **einbehalten** wird. Das ist eine bewusste, unabhängige
Entscheidung und wird nicht automatisch aus „defekt“ abgeleitet. Ist die Kaution zurückzuzahlen, aber noch nicht
ausgezahlt, erscheint der Button „Kaution zurückgezahlt“ zum Abhaken.

**Abrechnung**: Hat ein zurückgegebener Gegenstand eine Leihgebühr, wird beim Zurücknehmen automatisch eine
Rechnung an den Entleiher erstellt (Mitglied oder externe Person). Einbehaltene Kautionen landen als zusätzliche
Position auf derselben Rechnung. Gehören mehrere Gegenstände zu einem Vorgang, landet am Ende **alles auf einer
gemeinsamen Rechnung** – auch wenn die Positionen nacheinander statt gemeinsam zurückgenommen werden.

**Inventuren**: „Inventur anlegen“ erstellt eine Momentaufnahme des aktuellen Bestands (alle nicht ausgesonderten
Gegenstände). Auf der Inventurseite werden Positionen per Klick als ✓ gefunden, ✗ nicht gefunden oder ⚠ beschädigt
markiert; „Inventur abschließen“ fixiert das Ergebnis endgültig.

## 7. Spenden und Spendenquittungen

Einzelne **Spenden** (Geld, Sachspende, Mitgliedsbeitrag als Spende, verzichtete Aufwandsentschädigung) werden
erfasst und können mit einer **Zuwendungsbestätigung** verknüpft werden: „Einzelbestätigung erstellen“ direkt an
einer Spende, oder über *Spenden › Sammelbestätigungen erstellen* – dort werden pro Jahr alle noch nicht
bestätigten Geldspenden nach Spender gruppiert und mit einem Klick als Sammelbestätigungen angelegt (Sachspenden
bekommen immer eine Einzelbestätigung). Vor dem „Ausstellen“ (vergibt die Nummer `ZB-JJJJ-000001` und friert die
steuerlichen Vereinsdaten zum Zeitpunkt der Ausstellung ein) warnt das System, falls Finanzamt/Steuernummer/
Bescheiddatum am Verein fehlen oder der Bescheid älter als drei Jahre ist.

> Die Formulierungen der Spendenquittung orientieren sich am amtlichen Muster, ersetzen aber keine rechtliche
> Prüfung – bitte vor dem ersten echten Einsatz mit dem aktuellen amtlichen Muster bzw. Steuerberater abgleichen.

## 8. Aufwandsentschädigungen

Anträge (Ehrenamtspauschale, Übungsleiterpauschale, Aufwandsersatz gegen Beleg, sonstige Vergütung) durchlaufen
*Beantragt* → *Genehmigt* → *Ausgezahlt* (oder *Abgelehnt*). Vorstand und Kassenwart können genehmigen/ablehnen/als
ausgezahlt markieren. „Jahresübersicht Freibeträge“ zeigt je Empfänger und Jahr die Summen gegen die im Verein
hinterlegten Freibeträge (Ehrenamts-/Übungsleiterpauschale) und warnt, wenn ein Freibetrag überschritten wird oder
noch keine Erklärung vorliegt, dass die Pauschale nicht anderweitig ausgeschöpft ist. Ein genehmigter
Aufwandsersatz kann per „Verzicht → Aufwandsspende“ in eine Spende umgewandelt werden.

## 9. Veranstaltungen

Die Veranstaltungs-Detailseite ist eine Zentrale: Tagesordnung (inkl. „Standard-Tagesordnung“ für
Mitgliederversammlungen mit zehn üblichen Punkten), Aufgaben, Schichtplan mit Besetzungsstand, Anmeldungen
(Mitglieder oder Gäste, mit Personenzahl), Budget (Plan/Ist je Position), reserviertes Inventar sowie erzeugte
Schriftstücke/Serienbriefe und Ablage-Dokumente zur Veranstaltung. Direkt von hier aus: „Inventar reservieren“
(vorausgefüllter Verleih mit den Terminen der Veranstaltung), „Einladung erstellen“/„Einladung an Mitglieder
(Serienbrief)“/„Protokoll erstellen“ (aus der jeweiligen Standard-Vorlage), sowie bei bestehender
OpenSlides-Anbindung „In OpenSlides anlegen“/„Tagesordnung übertragen“. Alle Termine lassen sich als Kalenderdatei
(.ics) exportieren.

## 10. Ehrungen und Jubiläen

Unter *Jubiläen* erscheinen alle Mitglieder, die dieses Jahr eine der konfigurierten Jubiläumsschwellen
(*Verwaltung › Jubiläumsregeln*, z. B. „25 Jahre“) erreichen, mit einem vorausgefüllten Link „Ehrung anlegen“ und
dem Hinweis, ob bereits geehrt wurde. Ehrungsarten sind frei unter *Verwaltung › Ehrungsarten* konfigurierbar.

## 11. Schriftverkehr, Vorlagen, Ablage und Corporate Design

Ausführlich in [Schriftverkehr & Vorlagen](SCHRIFTVERKEHR.md) beschrieben. Kurzfassung: **Vorlagen** enthalten
Platzhalter wie `{vorname}`, `{briefanrede}`, `{verein}`, `{veranstaltung_datum}` oder `{tagesordnung}` (vollständige
Liste unter *Schriftverkehr › Platzhalter-Hilfe*); ein Satz Standardvorlagen (Einladungen, Protokolle,
Mitgliederinformationen …) ist vorinstalliert und lässt sich über „Standardvorlagen nachladen“ ergänzen, ohne
eigene Anpassungen zu überschreiben. Aus einer Vorlage entsteht ein einzelnes **Schriftstück** oder ein
**Serienbrief** an eine gefilterte Empfängerliste (Status/Mitgliedsart/Abteilung/Funktion/nur mit E-Mail); beides
lässt sich als PDF oder Word (.docx) ausgeben, per E-Mail versenden und automatisch in der **Ablage** archivieren
(mit Versionierung: gleicher Titel im selben Ordner legt eine neue Version an, alte bleiben einsehbar).

**Corporate Design**: PDF- und Word-Ausgabe verwenden pro Verein automatisch dasselbe Layout – Vereinsname groß
oben links, Logo oben rechts (unter *Verwaltung › Verein/Einstellungen* hochladbar), eine Trennlinie in der
**Akzentfarbe**, und eine Fußzeile mit Registereintrag/E-Mail, Vertretungsberechtigtem/Anschrift sowie
Bankverbindung – getrennt durch eine zweite Trennlinie in der optionalen **zweiten Akzentfarbe** (fällt auf die
erste zurück, wenn nicht gesetzt). Kein Vorlagen-Code nötig: jeder Verein bekommt automatisch sein eigenes Design
aus den Vereinseinstellungen. Dieselbe Akzentfarbe wird auch in der **Weboberfläche** verwendet (Navigationsleiste,
Schaltflächen, Links, farbig unterlegter Hover-Effekt beim Überfahren der Menüpunkte) – Logo, Navigation und Icons
(Bootstrap Icons) ergeben ein einheitliches Erscheinungsbild zwischen Anwendung, Briefen und PDFs. Nahezu jeder
Button in der Anwendung bekommt automatisch anhand seines Textes ein passendes Icon; auf jeder Unterseite
erscheint zusätzlich oben rechts das Icon der zugehörigen Navigationsgruppe wieder.

**Öffentliche Dokumente**: Beim Anlegen/Bearbeiten eines Ablage-Dokuments lässt sich „Öffentlich auf der
Startseite sichtbar“ aktivieren (Standard: aus). Ein so markiertes Dokument – z. B. die Datenschutzerklärung
oder ein Aufnahmeformular für Interessierte – erscheint dann auf einer öffentlichen, **ohne Anmeldung**
erreichbaren Downloads-Seite, verlinkt in der Fußzeile jeder Seite (auch der Anmeldeseite). Alle anderen
Ablage-Dokumente bleiben wie gewohnt nur für angemeldete Benutzer mit Ablage-Recht sichtbar. Siehe auch Kapitel 15
(Impressum).

## 12. OpenSlides-Anbindung

Unter *Verwaltung › OpenSlides-Anbindung* wird einmal pro Verein die Verbindung zu einer OpenSlides-Instanz
hinterlegt (URL, technischer Zugang, Committee-ID, Sprache; optional eine Funktion, auf die der Mitgliederabgleich
eingeschränkt wird). „Verbindung testen“ prüft die Zugangsdaten. „Mitglieder abgleichen“ legt fehlende
OpenSlides-Benutzerkonten für aktive Mitglieder an (Zugangsdaten können per Vorlage „Zugangsdaten OpenSlides“
verschickt werden), aktualisiert bestehende und deaktiviert Konten von Mitgliedern, die nicht mehr im Geltungsbereich
sind. Bei einer verknüpften Veranstaltung überträgt „In OpenSlides anlegen“ eine neue Sitzung mit Tagesordnung,
„Tagesordnung übertragen“ danach nur noch neu hinzugekommene Punkte. „Startpasswörter löschen“ entfernt alle
gespeicherten OpenSlides-Anfangspasswörter (z. B. nachdem alle Zugangsdaten verteilt wurden).

Diese Anbindung ist praktisch nur für den Superadministrator nutzbar, da das Modul `openslides` standardmäßig
außer beim Vorstand (nur lesend) keiner Rolle zugewiesen ist.

**Wahlergebnisse zurückholen**: Ist eine Veranstaltung mit einer OpenSlides-Versammlung verknüpft, erscheint auf
ihrer Seite zusätzlich „Wahlergebnisse aus OpenSlides übernehmen“. Das holt die Stimmenverteilung aller in
OpenSlides bereits abgeschlossenen Personenwahlen (Wahlgang-Status „finished“ oder „published“ – noch laufende
Wahlen liefern naturgemäß kein Ergebnis) und legt sie je Amt/Wahlgang als „Wahlergebnis“ auf der Veranstaltung ab
(Abschnitt „Wahlergebnisse (aus OpenSlides)“). Angezeigt wird ausschließlich die reine Ja-/Nein-/Enthaltung-Verteilung
je Kandidat:in – wer tatsächlich gewählt ist, muss anhand der Satzung (Mehrheitserfordernis, Umgang mit Gleichstand)
selbst festgestellt und eingetragen werden, das entscheidet die Software bewusst nicht automatisch. Über den
Platzhalter `{wahlergebnisse}` lässt sich die Stimmenverteilung auch direkt in ein Protokoll übernehmen (die
mitgelieferte Vorlage „Protokoll Mitgliederversammlung“ nutzt ihn bereits). Ein erneuter Abruf ersetzt zuvor
übernommene Ergebnisse dieser Veranstaltung vollständig. **Nicht** enthalten sind Ergebnisse von Abstimmungen über
Anträge (Motions) sowie ein Rückfluss der Anwesenheit.

## 13. Paperless-ngx-Anbindung

Unter *Verwaltung › Paperless-Anbindung* wird einmal pro Verein die Verbindung zu einer bestehenden
Paperless-ngx-Instanz hinterlegt (Adresse, API-Token – wird verschlüsselt gespeichert; optional ein
Standard-Korrespondent, -Dokumenttyp und Tags). „Verbindung testen“ prüft Adresse und Token. Nach dem Aktivieren
erscheint bei jedem Dokument in der **Ablage** (Kapitel 11) der Knopf „An Paperless senden“; auf der Ablage-Liste
steht zusätzlich „Sammelversand an Paperless“ für mehrere Dokumente gleichzeitig zur Verfügung. Ein fehlender
Korrespondent/Dokumenttyp/Tag wird bei Paperless automatisch neu angelegt. Der Versand läuft im Hintergrund;
Ergebnis bzw. Fehlermeldung erscheinen am jeweiligen Dokument (Seite ggf. neu laden).

**Duplikatschutz:** Dieselbe Datei wird nicht zweimal übergeben. Vor dem Senden prüft die Vereinsverwaltung anhand
der Datei-Prüfsumme, ob genau diese Version schon übergeben wurde oder in Paperless bereits vorhanden ist; dann
wird nichts gesendet und am Dokument steht ein Hinweis. Eine geänderte Datei bzw. eine neue Version wird normal
übergeben. Über „Erneut an Paperless senden“ (Dokument) bzw. das Häkchen im Sammelversand lässt sich der Schutz
bewusst umgehen.

**Tags am Dokument:** Jedes Ablage-Dokument hat ein Feld „Tags“ (kommagetrennt). Neue Dokumente bekommen dort
automatisch die **Art des Dokuments und das Jahr** eingetragen (z. B. „Protokoll, 2026“) – frei änderbar. Bei der
Übergabe werden diese Tags zusammen mit den Standard-Tags der Anbindung in Paperless gesetzt. Dokumente ohne eigene
Tags erhalten Art und Jahr beim Senden automatisch (abschaltbar unter „Art und Jahr automatisch als Tag setzen“).

**Live-Status:** Nach „An Paperless senden“ (auch im Sammelversand) zeigt die Seite den Fortschritt ohne manuelles
Neuladen an: Warteschlange → wird gesendet → von Paperless verarbeitet → abgelegt bzw. Fehlermeldung. Während der
Übergabe sind die Sende-Knöpfe ausgeblendet. Nach erfolgreicher Übergabe verschwindet „An Paperless senden“; nur
dann erscheint „Erneut an Paperless senden“.

Diese Anbindung ist praktisch nur für den Superadministrator einrichtbar, da das Modul `paperless` standardmäßig
außer beim Vorstand (nur lesend) keiner Rolle zugewiesen ist; den Versandknopf selbst können alle Rollen mit
Ablage-Bearbeitungsrecht nutzen (z. B. Schriftführer).

## 14. Auswertungen und Änderungsprotokoll

*Auswertungen* zeigt Mitgliederentwicklung (Ein-/Austritte je Jahr, kumulierter Bestand), Altersstruktur,
Beitragsaufkommen je Jahr (Soll/Ist/Offen), Rücklastschriften je Jahr, Inventarwert, Spenden je Jahr und (mit
Aufwandsrecht) Aufwandsentschädigungen je Jahr. Das **Änderungsprotokoll** (*Auswertung › Änderungsprotokoll*,
nur mit eigenem Recht `audit` einsehbar) verzeichnet automatisch jede Anlage/Änderung/Löschung mit Benutzer,
Zeitpunkt, IP-Adresse und geänderten Feldern; sensible Felder wie IBAN oder Passwörter werden dabei maskiert.

## 15. Vereinseinstellungen

Unter *Verwaltung › Verein/Einstellungen* (nur mit Recht `verwaltung`, siehe Kapitel 2) werden gepflegt:
Vereinsname/-anschrift/-kontakt, Registereintrag, Bankverbindung inkl. Gläubiger-ID, Finanzamt/Steuernummer und
Angaben zum Gemeinnützigkeitsbescheid (für Spendenquittungen), Umsatzsteuerpflicht/USt-IdNr./Steuerhinweis
(Kapitel 4, für nicht gemeinnützige Vereine bzw. den wirtschaftlichen Geschäftsbetrieb), Zahlungsziel und
Rechnungstexte, die konfigurierbaren Freibeträge für Aufwandsentschädigungen, sowie Logo, Akzentfarbe(n) und die
Unterschriftszeilen für den Briefkopf (Kapitel 11).

**Impressum**: Das Feld „Impressum“ enthält den vollständigen Text nach § 5 TMG/§ 18 MStV (verantwortliche
Person, Anschrift, Kontakt, Vertretungsberechtigte, ggf. USt-IdNr.) und wird **ungeprüft** auf einer öffentlich
erreichbaren Seite angezeigt, verlinkt in der Fußzeile jeder Seite (auch vor der Anmeldung). Bitte den Text vorab
mit der Satzung/dem Vereinsregister abgleichen – die Software übernimmt keine rechtliche Prüfung. Läuft die
Installation für mehrere Vereine (Kapitel 1), erscheint pro Verein ein eigener Impressum-Link.

**Lizenzhinweis**: Ebenfalls in der Fußzeile jeder Seite steht ein Hinweis, dass Feuerix freie Software
(AGPL-3.0) ist, mit einem Link zum Quellcode. Das erfüllt die AGPL-Pflicht, Nutzern einer über das Netzwerk
angebotenen (auch veränderten) Version Zugriff auf den passenden Quellcode zu geben (§ 13 AGPL) - bei eigenen
Änderungen am Code muss der Betreiber die Adresse (`PRODUCT_SOURCE_URL` in der `.env`) auf seine eigene,
tatsächlich passende Quellcode-Ablage umstellen, siehe README.

## 16. Datenschutz und Sicherheit

- IBANs (Mitglieder wie Verein) werden verschlüsselt in der Datenbank gespeichert, nicht im Klartext.
- Jede Änderung wird im Änderungsprotokoll nachvollziehbar erfasst (siehe Kapitel 14).
- Mitgliederdaten lassen sich jederzeit als vollständige DSGVO-Auskunft exportieren oder anonymisieren
  (Kapitel 3).
- Jeder Verein sieht ausschließlich seine eigenen Daten; es gibt keine Möglichkeit, versehentlich Daten eines
  anderen Vereins einzusehen oder zu exportieren.
- Rechteprüfung erfolgt konsequent serverseitig je Modul und Aktion (Anzeigen/Erstellen/Bearbeiten/Löschen) –
  nicht nur durch Ausblenden von Menüpunkten.
- **Cookies:** Es werden ausschließlich technisch notwendige Cookies gesetzt (Anmeldung/Sitzung, CSRF-Schutz,
  Spracheinstellung) – keine Tracking- oder Marketing-Cookies. Ein entsprechender Hinweis erscheint einmalig am
  unteren Bildschirmrand (auch ohne Anmeldung), bis er bestätigt wird.
- **Update-Benachrichtigung:** Superadministratoren sehen einen abweisbaren Hinweisbanner, sobald eine neuere
  Feuerix-Version veröffentlicht wurde. Die Prüfung läuft im Hintergrund (Celery), höchstens einmal pro Tag,
  ausgelöst beim nächsten Seitenaufruf eines Superadministrators – kein automatisches Herunterladen oder
  Einspielen, nur ein Hinweis. Einstellbar bzw. abschaltbar über `UPDATE_CHECK_URL` und
  `UPDATE_CHECK_INTERVALL_STUNDEN` in der `.env` (leer lassen für Installationen ohne Internetzugang). Der zuletzt
  bekannte Stand lässt sich auch unter `/admin/` › Systemeinstellungen einsehen.

## 17. Bekannte Grenzen

Aktuell **nicht** enthalten: automatischer Rückfluss von Abstimmungsergebnissen zu Anträgen (Motions) aus
OpenSlides ins Protokoll (Wahlergebnisse von Personenwahlen fließen bereits zurück, siehe Kapitel 12), eine
REST-API, anteilige Beitragsberechnung bei unterjährigem Ein-/Austritt, sowie eine Oberfläche für
Datenbank-Wiederherstellung (Restore geschieht über die Kommandozeile, siehe INSTALL.md). Der SEPA-Einzug
(Kapitel 4) erzeugt nur die Einzugsdatei; ein Rückkanal, der eine tatsächlich eingegangene oder zurückgebuchte
Lastschrift automatisch erkennt, existiert nicht – das läuft weiterhin über den normalen Kontoauszug-Import. Die
OpenSlides-Anbindung folgt der offiziellen Dokumentation, wurde aber nicht gegen eine produktive Instanz
verifiziert – bitte im Testbetrieb prüfen, bevor Sie sich darauf verlassen. Die Paperless-ngx-Anbindung wurde nach
der offiziellen REST-API-Dokumentation umgesetzt, aber ebenfalls nicht gegen eine laufende Instanz getestet – vor
dem produktiven Einsatz mit „Verbindung testen“ und einem echten Testdokument prüfen. Der **FinTS-Abruf**
(*Verwaltung › FinTS-Zugänge*, siehe Kapitel 4) wurde nach der Dokumentation der Bibliothek `python-fints`
umgesetzt und deckt auch die TAN-Abfrage (App-/SMS-/chipTAN) ab, wurde aber noch gegen keine echte Bank
getestet – vor dem produktiven Einsatz mit der eigenen Bank ausprobieren. Die Bank-PIN wird dabei nie
gespeichert, sondern bei jedem Abruf neu abgefragt. Zusätzlich ist eine vom Betreiber selbst zu registrierende,
kostenlose FinTS-Produkt-ID erforderlich (`FINTS_PRODUCT_ID` bzw. verschlüsselt unter `/admin/` ›
Systemeinstellungen) – sie liegt nicht automatisch vor.
