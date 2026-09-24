"""Mitgelieferte, im System frei bearbeitbare Standardvorlagen (Platzhalter siehe Platzhalter-Hilfe)."""

GRUSS = "Mit freundlichen Grüßen\n\nDer Vorstand\n{verein}\n\n{unterschrift_1}\n{unterschrift_2}"

STANDARDVORLAGEN = [
    {
        "name": "Einladung Mitgliederversammlung", "art": "einladung", "standard": True,
        "betreff": "Einladung zur Mitgliederversammlung am {veranstaltung_datum}",
        "hinweis": "Einladungsfrist und -form laut Satzung prüfen! Bei Bedarf Anträge-Frist ergänzen.",
        "text": (
            "{briefanrede}\n\n"
            "hiermit laden wir Sie herzlich zur Mitgliederversammlung des {verein} ein.\n\n"
            "Termin: {veranstaltung_datum}, {veranstaltung_uhrzeit} Uhr\nOrt: {veranstaltung_ort}\n\n"
            "Tagesordnung:\n{tagesordnung}\n\n"
            "Anträge zur Tagesordnung reichen Sie bitte bis spätestens [Datum] schriftlich beim Vorstand ein.\n\n"
            "Wir freuen uns auf Ihr Kommen.\n\n" + GRUSS),
    },
    {
        "name": "Einladung Vorstandssitzung", "art": "einladung",
        "betreff": "Einladung zur Vorstandssitzung am {veranstaltung_datum}",
        "text": (
            "{briefanrede}\n\n"
            "zur nächsten Sitzung des Vorstands laden wir Sie ein.\n\n"
            "Termin: {veranstaltung_datum}, {veranstaltung_uhrzeit} Uhr\nOrt: {veranstaltung_ort}\n\n"
            "Vorläufige Tagesordnung:\n{tagesordnung}\n\n"
            "Bitte teilen Sie uns mit, falls Sie verhindert sind.\n\n" + GRUSS),
    },
    {
        "name": "Einladung Veranstaltung / Vereinsfest", "art": "einladung",
        "betreff": "Einladung: {veranstaltung}",
        "text": (
            "{briefanrede}\n\n"
            "wir laden Sie herzlich zu unserer Veranstaltung „{veranstaltung}“ ein.\n\n"
            "Wann: {veranstaltung_datum}, ab {veranstaltung_uhrzeit} Uhr\nWo: {veranstaltung_ort}\n\n"
            "{veranstaltung_beschreibung}\n\n"
            "Um besser planen zu können, bitten wir um Anmeldung bis {anmeldeschluss}.\n\n" + GRUSS),
    },
    {
        "name": "Protokoll Mitgliederversammlung", "art": "protokoll", "standard": True,
        "betreff": "Protokoll der Mitgliederversammlung vom {veranstaltung_datum}",
        "hinweis": "Beschlüsse mit Abstimmungsergebnis (Ja/Nein/Enthaltung) festhalten; vom Versammlungsleiter und Protokollführer unterschreiben lassen. Bei Wahlen über OpenSlides zuerst „Wahlergebnisse aus OpenSlides übernehmen“ in der Veranstaltung nutzen, dann füllt {wahlergebnisse} die Stimmenverteilung; wer gewählt ist, bitte selbst eintragen.",
        "text": (
            "Verein: {verein}\nDatum: {veranstaltung_datum}\nOrt: {veranstaltung_ort}\n"
            "Beginn: {veranstaltung_uhrzeit} Uhr    Ende: [Uhrzeit] Uhr\n\n"
            "Versammlungsleiter/in: [Name]\nProtokollführer/in: [Name]\n\n"
            "Anwesend: [Anzahl] stimmberechtigte Mitglieder (Anwesenheitsliste liegt bei).\n"
            "Die Einladung erfolgte fristgerecht am [Datum] gemäß Satzung. Die Versammlung war beschlussfähig: [ja / nein].\n\n"
            "Tagesordnung:\n{tagesordnung}\n\n"
            "Verlauf und Beschlüsse:\n\n"
            "TOP 1: [Ergebnis / Beschluss]\nAbstimmung: Ja [ ]  Nein [ ]  Enthaltung [ ]\n\n"
            "TOP 2: [Ergebnis / Beschluss]\nAbstimmung: Ja [ ]  Nein [ ]  Enthaltung [ ]\n\n"
            "[weitere Tagesordnungspunkte]\n\n"
            "Wahlergebnisse (Stimmenverteilung aus OpenSlides, gewählte Person bitte ergänzen):\n{wahlergebnisse}\n\n"
            "Die Versammlungsleitung schloss die Versammlung um [Uhrzeit] Uhr.\n\n\n"
            "______________________________          ______________________________\n"
            "Versammlungsleiter/in                                Protokollführer/in"),
    },
    {
        "name": "Protokoll Vorstandssitzung", "art": "protokoll",
        "betreff": "Protokoll der Vorstandssitzung vom {veranstaltung_datum}",
        "text": (
            "Verein: {verein}\nDatum: {veranstaltung_datum}, {veranstaltung_uhrzeit} Uhr\nOrt: {veranstaltung_ort}\n\n"
            "Anwesend: [Namen]\nEntschuldigt: [Namen]\nProtokoll: [Name]\n\n"
            "Tagesordnung:\n{tagesordnung}\n\n"
            "Besprechung und Beschlüsse:\n[Text]\n\n"
            "Aufgaben / Verantwortliche / Fristen:\n[Aufgabe – Wer – Bis wann]\n\n"
            "Nächster Termin: [Datum]\n\n\n"
            "______________________________\nProtokollführer/in"),
    },
    {
        "name": "Mitgliederinformation (allgemein)", "art": "serienbrief", "standard": True,
        "betreff": "Information für unsere Mitglieder",
        "text": ("{briefanrede}\n\n[Ihr Text]\n\nBei Fragen erreichen Sie uns unter {verein_email}.\n\n" + GRUSS),
    },
    {
        "name": "Information zum Mitgliedsbeitrag", "art": "serienbrief",
        "betreff": "Ihr Mitgliedsbeitrag {jahr}",
        "text": (
            "{briefanrede}\n\n"
            "wir bedanken uns für Ihre Unterstützung als Mitglied ({mitgliedsart}, Mitgliedsnummer {mitgliedsnummer}) "
            "im {verein}.\n\n"
            "Der Mitgliedsbeitrag für {jahr} wird zum [Datum] fällig. [Hinweis zu Zahlungsweise / Lastschrift]\n\n"
            "Ihre Rechnung erhalten Sie gesondert.\n\n" + GRUSS),
    },
    {
        "name": "Glückwunsch zum Mitgliedsjubiläum", "art": "brief",
        "betreff": "Herzlichen Glückwunsch zum {mitglied_seit_jahre}-jährigen Jubiläum",
        "text": (
            "{briefanrede}\n\n"
            "seit {eintritt} sind Sie Mitglied im {verein} – in diesem Jahr sind es {mitglied_seit_jahre} Jahre. "
            "Dafür danken wir Ihnen ganz herzlich!\n\n"
            "Wir würden uns freuen, Sie zur Ehrung am [Datum] begrüßen zu dürfen.\n\n" + GRUSS),
    },
    {
        "name": "Zugangsdaten OpenSlides (Mitgliederversammlung online)", "art": "serienbrief",
        "betreff": "Ihre Zugangsdaten für die Versammlung",
        "hinweis": "Erst nach dem OpenSlides-Abgleich verwenden. Danach Startpasswörter in der OpenSlides-Anbindung löschen.",
        "text": (
            "{briefanrede}\n\n"
            "für die digitale Durchführung unserer Mitgliederversammlung haben wir für Sie ein Konto eingerichtet.\n\n"
            "Adresse: {openslides_url}\nBenutzername: {openslides_benutzername}\nStartpasswort: {openslides_passwort}\n\n"
            "Bitte ändern Sie das Passwort nach der ersten Anmeldung und geben Sie es nicht weiter.\n\n" + GRUSS),
    },
    {
        "name": "Brief (allgemein)", "art": "brief", "betreff": "[Betreff]",
        "text": "{briefanrede}\n\n[Ihr Text]\n\n" + GRUSS,
    },
]
