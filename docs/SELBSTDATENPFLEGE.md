# Selbstdatenpflege für Mitglieder

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

Straße/PLZ/Ort, Telefon, Mobil, E-Mail, Kontoinhaber, IBAN, BIC. Alle anderen Felder (Status, Mitgliedsart,
individueller Beitrag, Mitgliedsnummer, Ein-/Austrittsdatum, Funktionen, Dokumente …) bleiben ausschließlich
für Mitarbeiter mit passendem Recht änderbar. Jede Änderung wird wie gewohnt automatisch im
Änderungsprotokoll erfasst.

## Zugang sperren / Startpasswort löschen

* **„Zugang zur Selbstdatenpflege sperren“**: deaktiviert das Benutzerkonto (Anmeldung nicht mehr möglich).
  Erneutes „Zugangsdaten senden“ reaktiviert es mit neuem Passwort.
* **„Gespeichertes Startpasswort löschen“**: entfernt das zuletzt vergebene Startpasswort aus der Datenbank
  (wird verschlüsselt gespeichert, bis es gelöscht wird – ähnlich wie bei der OpenSlides-Anbindung).

## Rechte

Eigenes Modul **„Selbstdatenpflege (Zugänge der Mitglieder verwalten)“** unter *Verwaltung › Rollen*. Die
Rolle **Vorstand** hat es standardmäßig vollständig; zusätzlich gibt es die schlanke Standardrolle
**„Mitgliederverwaltung“** (nur dieses Modul + Lesezugriff auf Mitglieder) für Personen, die ausschließlich
Zugänge verwalten sollen, ohne sonstige Vorstandsrechte.

**Hinweis für bestehende Installationen:** Neue Standardrollen werden automatisch angelegt (Verein-Signal /
`ersteinrichtung`-Kommando), bereits vorhandene Rollen wie „Vorstand“ werden aber **nicht** rückwirkend
aktualisiert. Bitte bei Bedarf unter *Verwaltung › Rollen* händisch das Häkchen bei „Selbstdatenpflege“
für die gewünschte(n) Rolle(n) setzen.
