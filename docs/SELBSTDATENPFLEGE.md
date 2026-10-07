# Selbstdatenpflege für Mitglieder

> Teil des [Handbuchs](HANDBUCH.md) – siehe dort Kapitel 3 „Mitgliederverwaltung“ für den Gesamtüberblick.

Mitglieder können ausgewählte eigene Daten selbst online pflegen, ohne Zugriff auf die übrige Verwaltung zu
erhalten. Das ist ein separater, schlanker Zugang – unabhängig vom Rollen-/Rechtesystem für Mitarbeiter
(*Verwaltung › Benutzer*).

## Einrichtung durch den Vorstand

1. Auf der Detailseite eines Mitglieds (Voraussetzung: E-Mail-Adresse ist hinterlegt) den Button
   **„Zugangsdaten für Selbstdatenpflege senden“** klicken.
2. Das System legt bei Bedarf ein Benutzerkonto an (Benutzername = E-Mail-Adresse), vergibt ein zufälliges
   Startpasswort und verschickt beides per E-Mail direkt an das Mitglied.
3. Das Mitglied meldet sich unter `/login/` an, landet automatisch auf **„Meine Daten“** (nicht auf dem
   Verwaltungs-Dashboard) und sollte das Passwort zeitnah ändern (oben rechts unter „Passwort“).

Erneutes Klicken auf den Button erzeugt ein neues Startpasswort und verschickt es erneut (z. B. falls die
E-Mail nicht ankam oder das Mitglied sein Passwort vergessen hat).

## Was Mitglieder selbst ändern können

Straße/PLZ/Ort, Telefon, Mobil, E-Mail, Zahlungsart, Kontoinhaber, IBAN, BIC. Alle anderen Felder (Status,
Mitgliedsart, individueller Beitrag, Mitgliedsnummer, Ein-/Austrittsdatum, Funktionen, Dokumente …) bleiben
ausschließlich für Mitarbeiter mit passendem Recht änderbar. Jede Änderung wird wie gewohnt automatisch im
Änderungsprotokoll erfasst. **Hinweis zur Zahlungsart:** Eine Umstellung auf „SEPA-Lastschrift“ allein reicht
nicht aus – dafür wird zusätzlich ein gültiges SEPA-Mandat (Referenz und Datum) benötigt, das weiterhin nur der
Vorstand/Kassenwart hinterlegen kann.

## Zugang sperren / Startpasswort löschen

* **„Zugang zur Selbstdatenpflege sperren“**: deaktiviert das Benutzerkonto (Anmeldung nicht mehr möglich).
  Erneutes „Zugangsdaten senden“ reaktiviert es mit neuem Passwort.
* **„Gespeichertes Startpasswort löschen“**: entfernt das zuletzt vergebene Startpasswort aus der Datenbank
  (wird verschlüsselt gespeichert, bis es gelöscht wird – ähnlich wie bei der OpenSlides-Anbindung).

## Rechte

Eigenes Modul **„Selbstdatenpflege (Zugänge der Mitglieder verwalten)“**, über die Berechtigungsmatrix bzw. Tags
vergeben (siehe Handbuch Kapitel 2 „Zugriff über Tags“). Die sechs DSO-Rollen sowie Administrator haben es
standardmäßig vollständig (Zeile „Vereinssoftware / Verwaltung“ der Berechtigungsmatrix); zusätzlich gibt es das
schlanke Tag **„Mitgliederverwaltung“** (nur dieses Modul + Lesezugriff auf Mitglieder) für Personen, die
ausschließlich Zugänge verwalten sollen, ohne sonstige Vorstandsrechte.

## Verwaltungszugang direkt aus dem Mitglied heraus einrichten

Wer als Mitarbeiter vollen Zugriff auf die Verwaltung braucht (also einen Zugang mit Rolle, wie sonst unter
*Verwaltung › Benutzer*), muss dafür nicht mehr extra dort angelegt werden – sofern die Person bereits als
Mitglied erfasst ist:

1. Auf der Mitglieder-Detailseite (Voraussetzung: E-Mail-Adresse hinterlegt) **„Verwaltungszugang
   einrichten“** klicken.
2. Rolle auswählen (z. B. 1. Vorsitzender, Kassenwart, Schriftführer …) und speichern.
3. Zugangsdaten (Benutzername = E-Mail-Adresse, zufälliges Startpasswort) werden automatisch per E-Mail
   verschickt.

Besteht für das Mitglied bereits ein Selbstdienst-Konto (siehe oben), wird **dasselbe** Benutzerkonto
weiterverwendet – die Person hat dann mit einem Login sowohl Verwaltungszugriff als auch Zugriff auf „Meine
Daten“. Existiert bereits ein Verwaltungszugang, erscheint stattdessen ein Link zum Bearbeiten der Rolle
(führt auf die normale Seite unter *Verwaltung › Benutzer*). Rechte: benötigt das Modul **„Verwaltung“**
(wie das Anlegen unter *Verwaltung › Benutzer* auch) – das haben die sechs DSO-Rollen und Administrator
standardmäßig vollständig, außerdem (als Rechte-Bypass) der Superadministrator.
