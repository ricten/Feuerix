import ipaddress
import os
import re
import socket
import unicodedata
import uuid
from decimal import Decimal
from urllib.parse import urlparse

from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _

INTERNE_HOSTNAMEN = {"localhost", "db", "redis", "web", "worker"}


def faelligkeits_stufe(datum):
    """'rot'/'gelb'/'gruen' je nach Resttagen bis zu einem Datum, oder None ohne Datum - rot: unter 2 Tage
    (inkl. überfällig), gelb: 2 bis unter 10 Tage, grün: ab 10 Tagen. Gemeinsam genutzt von Aufgabe
    (Fälligkeit) und Verleih (geplante Rückgabe), damit beide Kacheln auf der Startseite dieselbe
    Ampellogik verwenden."""
    from datetime import date
    if not datum:
        return None
    resttage = (datum - date.today()).days
    if resttage < 2:
        return "rot"
    if resttage < 10:
        return "gelb"
    return "gruen"


def pruefe_oeffentliche_adresse(url):
    """Verhindert SSRF (Server-Side Request Forgery) bei vom Nutzer frei konfigurierten externen Diensten
    (Paperless-, OpenSlides-Verbindung, FinTS-Bankadresse): nur echte, öffentlich erreichbare Adressen
    sind erlaubt - keine internen Docker-Hostnamen und keine privaten/loopback/link-local IP-Bereiche
    (z. B. Cloud-Metadata-Dienste wie 169.254.169.254). Wer die Verbindung nur im eigenen Verein ändern
    darf, soll darüber nicht interne Dienste des Servers ansprechen können. Kein Schutz gegen Angriffe, bei
    denen der Server erst NACH dem Speichern auf eine andere (interne) Adresse umgeleitet wird (DNS-
    Rebinding) - das deckt dieses einfache, einmalige Prüfen beim Speichern bewusst nicht ab. Lässt sich der
    Hostname nicht auflösen (kein Internetzugriff gerade, DNS-Problem, o. ä.), wird NICHT blockiert - sonst
    könnte schon ein kurzer DNS-Ausfall das Speichern einer eigentlich unbedenklichen Adresse verhindern;
    der eigentliche Schutz (interne Hostnamen, private IP-Literale) greift unabhängig davon immer."""
    host = (urlparse(url).hostname or "").lower()
    if not host:
        raise ValidationError(_("Ungültige Adresse."))
    if host in INTERNE_HOSTNAMEN:
        raise ValidationError(_("Diese Adresse ist nicht erlaubt (interner Hostname)."))
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise ValidationError(_("Diese Adresse ist nicht erlaubt (privater/interner Adressbereich)."))


def ascii_kennung(s):
    """Normalisiert einen Namen zu einer ASCII-tauglichen Kennung (z. B. für Benutzernamen in Paperless/OpenSlides):
    Umlaute/ß ausgeschrieben, alles andere auf a-z0-9._- reduziert."""
    s = (s or "").lower().replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9._-]", "", s.replace(" ", "-"))


def geld(wert):
    if wert is None:
        return "–"
    s = f"{Decimal(wert):,.2f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".") + " €"


def upload_pfad(instance, dateiname):
    return f"{instance.verein_id}/{instance._meta.model_name}/{uuid.uuid4().hex[:12]}_{os.path.basename(dateiname)}"


def logo_pfad(instance, dateiname):
    ext = os.path.splitext(dateiname)[1].lower()[:5]
    return f"vereine/{instance.kuerzel}/logo_{uuid.uuid4().hex[:8]}{ext}"


def hex_zu_rgb(hex_farbe, standard=(175, 43, 30)):
    """Zerlegt einen Hex-Farbcode (z. B. '#1F4E79') in ein (r, g, b)-Tupel, mit Standardwert bei ungültigem Wert."""
    hex_farbe = (hex_farbe or "").lstrip("#")
    if len(hex_farbe) != 6:
        return standard
    try:
        return tuple(int(hex_farbe[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return standard


def _linearisiert(kanal):
    """Ein 0..255-Farbkanal in den linearen sRGB-Raum (0..1), fuer die WCAG-Leuchtdichteformel."""
    c = kanal / 255
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def relative_leuchtdichte(hex_farbe):
    """WCAG-relative Leuchtdichte (0..1) eines Hex-Farbcodes."""
    r, g, b = hex_zu_rgb(hex_farbe)
    return 0.2126 * _linearisiert(r) + 0.7152 * _linearisiert(g) + 0.0722 * _linearisiert(b)


def lesbare_textfarbe(hex_farbe):
    """'#000' oder '#fff', je nachdem was auf hex_farbe als Hintergrund den höheren WCAG-Kontrast ergibt.
    Verwendet die tatsächliche (gamma-korrigierte) Leuchtdichte statt einer einfachen RGB-Helligkeitsformel -
    letztere liegt bei gesättigten Farben (v. a. Blau-/Rottönen) öfter spürbar daneben."""
    l = relative_leuchtdichte(hex_farbe)
    kontrast_schwarz = (l + 0.05) / 0.05
    kontrast_weiss = 1.05 / (l + 0.05)
    return "#000" if kontrast_schwarz >= kontrast_weiss else "#fff"


def rgb_zu_hex(r, g, b):
    """Formatiert ein (r, g, b)-Tupel (auch mit Fließkommazahlen) als Hex-Farbcode '#RRGGBB'."""
    r, g, b = (max(0, min(255, round(x))) for x in (r, g, b))
    return f"#{r:02X}{g:02X}{b:02X}"


def gemischte_farbe(hex_a, hex_b, anteil_a):
    """Mischt zwei Hex-Farben linear (anteil_a = Anteil der ersten Farbe, 0..1) - serverseitig statt per CSS
    color-mix(), damit z. B. die Kontrastfarbe zum Ergebnis zuverlässig berechnet werden kann."""
    ra, ga, ba = hex_zu_rgb(hex_a)
    rb, gb, bb = hex_zu_rgb(hex_b)
    anteil_b = 1 - anteil_a
    return rgb_zu_hex(ra * anteil_a + rb * anteil_b, ga * anteil_a + gb * anteil_b, ba * anteil_a + bb * anteil_b)


def betrag_in_worten(betrag):
    from num2words import num2words
    betrag = Decimal(betrag).quantize(Decimal("0.01"))
    euro, cent = int(betrag), int((betrag - int(betrag)) * 100)
    text = f"{num2words(euro, lang='de')} Euro"
    if cent:
        text += f" und {num2words(cent, lang='de')} Cent"
    return text
