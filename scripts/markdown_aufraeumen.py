"""Bringt Markdown-Dateien auf die Regeln von markdownlint, die in diesem Projekt (VS Code) angezeigt werden.

Aufruf:  python scripts/markdown_aufraeumen.py [Dateien ...]     (ohne Angabe: alle *.md im Repository)

Behebt: MD022 (Leerzeile um Überschriften), MD032 (Leerzeile um Listen, auch beim Wechsel zwischen nummerierter Liste und
Aufzählung), MD004 (einheitliches Listenzeichen je Datei - das der ersten Aufzählung), MD060 (Leerzeichen in der Trennzeile von
Tabellen). Nicht automatisch behebbar, aber geprüft und gemeldet: MD036 (fetter Satz allein in einer Zeile statt Überschrift).
Codeblöcke bleiben unberührt."""
import re
import subprocess
import sys
from pathlib import Path

LISTE = re.compile(r"^(\s*)([-*+]|\d+[.)])\s+")
UEBER = re.compile(r"^#{1,6}\s")
EINRUECK = (" ", "\t")
NUR_FETT = re.compile(r"^\*\*[^*]*[^*.,;:!?]\*\*$")     # mit Satzzeichen am Ende (z. B. "**Schritte:**") meldet markdownlint nichts
TABELLE_TRENNER = re.compile(r"^\|(\s*:?-{3,}:?\s*\|)+\s*$")


def listenzeichen(text):
    """Das Zeichen der ersten Aufzählung der Datei (außerhalb von Codeblöcken) - gilt für die ganze Datei."""
    fence = False
    for z in text.split("\n"):
        if z.lstrip().startswith("```"):
            fence = not fence
        m = LISTE.match(z)
        if not fence and m and m.group(2) in "-*+":
            return m.group(2)
    return "-"


def tabellen_trenner(zeile):
    zellen = [z.strip() for z in zeile.strip().strip("|").split("|")]
    return "| " + " | ".join(zellen) + " |"


def aufraeumen(text):
    zeichen = listenzeichen(text)
    aus, fence, letzte_art = [], False, None   # letzte_art: "num"/"punkt" der laufenden Liste auf oberster Ebene
    for z in text.split("\n"):
        if z.lstrip().startswith("```"):
            fence = not fence
            aus.append(z)
            continue
        if fence:
            aus.append(z)
            continue
        if TABELLE_TRENNER.match(z):
            z = tabellen_trenner(z)
        m = LISTE.match(z)
        if m and m.group(2) in "-*+" and m.group(2) != zeichen:
            z = z[:m.start(2)] + zeichen + z[m.end(2):]       # Listenzeichen der Datei verwenden
            m = LISTE.match(z)
        prev = aus[-1] if aus else ""
        oben = bool(m) and not m.group(1)
        art = ("num" if m.group(2)[0].isdigit() else "punkt") if oben else None
        if UEBER.match(z) and prev.strip():
            aus.append("")
        elif prev.strip() and UEBER.match(prev) and z.strip():
            aus.append("")
        elif oben and prev.strip() and letzte_art is None:
            aus.append("")      # Liste beginnt direkt unter einem Absatz
        elif oben and prev.strip() and letzte_art != art:
            aus.append("")      # Wechsel zwischen nummerierter Liste und Aufzaehlung
        elif z.strip() and not m and not z.startswith(EINRUECK) and letzte_art and prev.strip():
            aus.append("")      # Absatz direkt nach einer Liste
        if not z.strip() or UEBER.match(z):
            letzte_art = None
        elif oben:
            letzte_art = art
        elif not z.startswith(EINRUECK):
            letzte_art = None
        aus.append(z)
    return "\n".join(aus)


def fett_statt_ueberschrift(text):
    fence, treffer = False, []
    for n, z in enumerate(text.split("\n"), 1):
        if z.lstrip().startswith("```"):
            fence = not fence
        if not fence and NUR_FETT.match(z.strip()):
            treffer.append(n)
    return treffer


def dateien():
    ausgabe = subprocess.run(["git", "ls-files", "*.md"], capture_output=True, text=True, check=True).stdout
    return [Path(p) for p in ausgabe.split("\n") if p]


def main(argumente):
    pfade = [Path(a) for a in argumente] or dateien()
    for pfad in pfade:
        s = pfad.read_text(encoding="utf-8")
        n = aufraeumen(s)
        if n != s:
            pfad.write_text(n, encoding="utf-8")
            print("korrigiert:", pfad)
        for zeile in fett_statt_ueberschrift(n):
            print(f"WARNUNG {pfad}:{zeile}: fetter Text allein in einer Zeile (MD036) - als Überschrift oder im Satz formulieren")


if __name__ == "__main__":
    main(sys.argv[1:])
