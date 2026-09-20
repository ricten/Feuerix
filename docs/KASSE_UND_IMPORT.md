# Kassenbuch, Kassenbericht und Mitglieder-Import/Export

## Kassenbuch einrichten (einmalig)
1. **Kasse › Konten:** „Bankkonto“ und „Barkasse“ sind angelegt. **Eröffnungsbestand** und **Eröffnungsdatum** eintragen
   (Kontostand bzw. Kassenbestand zum Startdatum der Buchführung im System, z. B. 01.01.).
2. **Kasse › Buchungskategorien:** Vorschläge prüfen; jede Kategorie hat eine **steuerliche Sphäre** (Ideeller Bereich,
   Vermögensverwaltung, Zweckbetrieb, Wirtschaftlicher Geschäftsbetrieb). Die Zuordnung (z. B. Vereinsfest) bitte mit
   Steuerberater/Finanzamt abstimmen.

## Buchen
* **Kasse › Kassenbuch › Neu:** Datum, Einnahme/Ausgabe (Betrag immer positiv), Konto, Kategorie, Text, Beleg-Scan. Belegnummer
  `B-JJJJ-000001` wird automatisch vergeben.
* **„Aus Zahlungen/Spenden/Veranstaltungen übernehmen“:** erzeugt Buchungen aus Zahlungen auf Rechnungen (Rücklastschriften
  als Ausgabe), Geldspenden, ausgezahlten Aufwandsentschädigungen und Ist-Werten des Veranstaltungsbudgets. Jede Quelle wird
  nur einmal gebucht, mehrfaches Ausführen ist unbedenklich.
* Nicht automatisch: Bankgebühren, Zinsen, Einkäufe, sonstige Kontobewegungen → manuell buchen (Kontoauszug abarbeiten).
* Automatisch übernommene Buchungen sind in Betrag/Datum/Art gesperrt; Korrektur über eine Gegenbuchung.

## Kassenbericht
1. **Kasse › Kassenberichte › Neu:** Titel (z. B. „Kassenbericht 2026“), Zeitraum, Kassenwart, Kassenprüfer, optional
   gezählter Bargeldbestand und Kontostand laut Auszug zum Stichtag (für den Soll/Ist-Abgleich).
2. Detailseite: Kennzahlen, Kontenübersicht, Einnahmen/Ausgaben je Kategorie mit **Vorjahresvergleich**, Ergebnis je Sphäre;
   Warnungen bei Differenzen zu den Ist-Beständen und bei Buchungen ohne Beleg.
3. **PDF** (mit Logo, Unterschriftszeilen und angehängtem Kassenbuch als Prüfungsunterlage) und **Excel**.
4. Prüfungsbemerkung der Kassenprüfer eintragen, PDF ausdrucken und unterschreiben lassen.
5. **Abschließen:** sperrt den Zeitraum für Buchungen und legt das PDF in der **Ablage** (Kassenberichte/Jahr) ab.
   „Wieder öffnen“ ist nur mit Löschrecht im Modul Kassenbuch möglich (wird protokolliert).
* Rolle **Kassenprüfer** (nur Lesen auf Kasse, Rechnungen, Zahlungen, Bank, Spenden …) ist als Standardrolle vorhanden.

## Mitglieder-Import
*Mitglieder › Mitglieder-Import* (oder Button in der Mitgliederliste).
1. **Vorlage herunterladen** (Excel mit allen Spalten und Hinweisen) oder eine vorhandene Liste verwenden – gängige Überschriften
   (Geburtstag, E-Mail, Straße, Eintritt …) werden erkannt. Pflicht: **Vorname** und **Nachname**.
2. Erst mit **„Nur Testlauf“** starten: es wird nichts gespeichert, der Bericht zeigt neu/aktualisiert/Fehler je Zeile.
3. Fehler in der Datei beheben, Testlauf wiederholen, dann **ohne** Haken importieren.
* Abgleich bestehender Mitglieder über die Mitgliedsnummer, sonst über Vorname + Nachname + Geburtsdatum. Leere Zellen
  überschreiben nichts. Fehlerhafte Zeilen werden übersprungen, alle anderen übernommen.
* Mitgliedsart und Abteilungen müssen vorhanden sein – oder Option „unbekannte anlegen“ nutzen.
* IBANs werden auf Prüfsumme kontrolliert (Warnung) und verschlüsselt gespeichert. Der Import wird im Änderungsprotokoll vermerkt.

## Mitglieder-Export
*Mitgliederliste › Vollexport (Excel)*: alle Stammdaten; **„mit Bankdaten“** nur für Benutzer mit Beitragsrecht. Jeder Export wird
im Änderungsprotokoll festgehalten (Datenschutz-Nachweis). Filterbare Teilexporte (CSV/Excel) gibt es zusätzlich in jeder Liste.
