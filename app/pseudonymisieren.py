#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pseudonymisierer (lokal) – Prototyp Quantensprung

Ersetzt personenbezogene Angaben in Dokumenten durch Platzhalter, bevor ein
Dokument in ein Cloud-Werkzeug (Claude, ChatGPT, Copilot ...) geladen wird,
und setzt sie in der Auswertung wieder ein.

Alles läuft auf dem eigenen Rechner. Es werden keine Daten versendet.

Aufruf:
    python3 pseudonymisieren.py hin     DATEI [--namen "Anna Muster, Max Test"] [--orte] [--orgs]
    python3 pseudonymisieren.py zurueck DATEI --zuordnung DATEI.zuordnung.json
    python3 pseudonymisieren.py pruefen DATEI            (nur Trockenlauf, schreibt nichts)

Formate: .txt .md .docx .xlsx .rtf .pdf (RTF und PDF: Ergebnis als .txt)
"""
import argparse
import json
import re
import sys
import zipfile
from collections import OrderedDict
from pathlib import Path

# --------------------------------------------------------------------------
# Muster für feste Datenformen
# --------------------------------------------------------------------------
W = r"[\wäöüÄÖÜß]"
CAP = r"[A-ZÄÖÜ][\wäöüß-]+"

PATTERNS = [
    # (Kategorie, Regex, Gruppe)  -> Gruppe 0 = ganzer Treffer
    ("EMAIL", re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"), 0),
    ("IBAN", re.compile(r"\b[A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]{4}){3,7}(?:[ ]?[A-Z0-9]{1,4})?\b"), 0),
    ("TELEFON", re.compile(r"(?<![\w/.])\(?(?:\+49|0049|0)(?:[ \t()/.-]*\d){7,}"), 0),
    ("GEBURTSDATUM", re.compile(
        r"(?:geb\.?|geboren(?:\s+am)?|Geburtsdatum:?|Geb\.-Datum:?)\s*(\d{1,2}\.\d{1,2}\.\d{2,4})"), 1),
    ("ADRESSE", re.compile(
        rf"\b{CAP}?(?:straße|strasse|str\.|weg|gasse|platz|allee|ring|ufer|damm|pfad)\s*\d{{1,3}}\s?[a-zA-Z]?\b"), 0),
    ("ADRESSE", re.compile(rf"\b\d{{5}}\s+{CAP}(?:\s+{CAP})?"), 0),
]
# Wörter, die nach einer fünfstelligen Zahl keinen Ort bedeuten
PLZ_AUSNAHMEN = {"Euro", "Teilnehmer", "Teilnehmende", "Personen", "Mitglieder", "Besucher",
                 "Spender", "Spenden", "Zeichen", "Wörter", "Seiten", "Kilometer", "Stunden"}

ANREDE = re.compile(
    rf"\b(?:(?:Herr|Herrn|Frau)[ \t]+(?:(?:Prof|Dr)\.[ \t]*)*|(?:Prof|Dr)\.[ \t]*(?:(?:Prof|Dr)\.[ \t]*)*)({CAP}(?:[ \t]+{CAP})?)")

# Wörter, die vom Sprachmodell gern fälschlich als Namen erkannt werden
STOPP = {"Sohn", "Tochter", "Mann", "Frau", "Herr", "Herrn", "Kind", "Kinder", "Mutter", "Vater", "Eltern",
         "Kita", "Schule", "Verein", "Stiftung", "Team", "Chef", "Chefin", "Kollege", "Kollegin", "Dr", "Prof",
         "Geschäftsführer", "Geschäftsführerin", "Erzieherin", "Erzieher", "Lehrer", "Lehrerin", "Kunde",
         "Kundin", "Patient", "Patientin", "Klient", "Klientin", "Bewerber", "Bewerberin", "Mitarbeiter",
         "Mitarbeiterin", "Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"}

KATEGORIEN_PLATZHALTER = {
    "PERSON": "PERSON", "EMAIL": "EMAIL", "IBAN": "IBAN", "TELEFON": "TELEFON",
    "GEBURTSDATUM": "GEBURTSDATUM", "ADRESSE": "ADRESSE", "ORT": "ORT", "ORGANISATION": "ORG",
}


# Platzhalter, auch in abgewandelter Schreibweise der KI: \[PERSON_01\], [PERSON 01], PERSON_01
_KAT = "PERSON|EMAIL|IBAN|TELEFON|GEBURTSDATUM|ADRESSE|ORT|ORG"
PLATZHALTER_TOLERANT = re.compile(
    rf"\\?\[\s*({_KAT})[_\s]+(\d+)(?:[_\s]+(VOR|NACH))?\s*\\?\]"
    rf"|(?<![\w\[])({_KAT})_(\d+)(?:_(VOR|NACH))?(?![\w\]])")

# --------------------------------------------------------------------------
# Lesen und Schreiben der Formate
# --------------------------------------------------------------------------
def lese_einheiten(pfad: Path):
    """Gibt eine Liste von Textstücken zurück (Absätze, Zellen, Zeilen)."""
    if not pfad.exists():
        sys.exit(f"Datei nicht gefunden: {pfad.name}")
    ext = pfad.suffix.lower()
    if not ext:
        sys.exit("Dateiendung fehlt. Möglich: .docx .xlsx .txt .md .csv .rtf .pdf")
    if ext in (".txt", ".md", ".csv"):
        return pfad.read_text(encoding="utf-8").split("\n")
    if ext == ".rtf":
        return rtf_text(pfad).split("\n")
    if ext == ".docx":
        import docx
        d = docx.Document(str(pfad))
        return [p.text for p in alle_absaetze(d)]
    if ext == ".xlsx":
        import openpyxl
        wb = openpyxl.load_workbook(str(pfad))
        return [str(c.value) for ws in wb for row in ws.iter_rows() for c in row
                if isinstance(c.value, str)]
    if ext == ".pdf":
        from pypdf import PdfReader
        r = PdfReader(str(pfad))
        text = "\n\n".join((s.extract_text() or "") for s in r.pages)
        if len(text.strip()) < 20:
            sys.exit("Diese PDF hat keine Textebene (vermutlich ein Scan). "
                     "Bitte zuerst lokal mit Texterkennung (OCR) bearbeiten.")
        return text.split("\n")
    sys.exit(f"Format {ext} wird nicht unterstützt. Möglich: .docx .xlsx .txt .md .csv .rtf .pdf")


def rtf_text(pfad):
    try:
        from striprtf.striprtf import rtf_to_text
    except ImportError:
        sys.exit("Für RTF fehlt ein Baustein. Bitte einmal ausführen: pip install striprtf")
    return rtf_to_text(pfad.read_text(encoding="utf-8", errors="ignore"))


def alle_absaetze(d):
    for p in d.paragraphs:
        yield p
    for t in d.tables:
        for row in t.rows:
            for cell in row.cells:
                yield from _zellen_absaetze(cell)
    for s in d.sections:
        for teil in (s.header, s.footer, s.first_page_header, s.first_page_footer):
            for p in teil.paragraphs:
                yield p
            for t in teil.tables:
                for row in t.rows:
                    for cell in row.cells:
                        yield from _zellen_absaetze(cell)


def _zellen_absaetze(cell):
    for p in cell.paragraphs:
        yield p
    for t in cell.tables:
        for row in t.rows:
            for c in row.cells:
                yield from _zellen_absaetze(c)


def schreibe_transformiert(quelle: Path, ziel: Path, f):
    """Wendet f(text)->text auf alle Textstücke an und schreibt nach ziel."""
    ext = quelle.suffix.lower()
    if ext in (".txt", ".md", ".csv"):
        ziel.write_text("\n".join(f(z) for z in quelle.read_text(encoding="utf-8").split("\n")),
                        encoding="utf-8")
    elif ext == ".docx":
        import docx
        d = docx.Document(str(quelle))
        gesehen = set()
        for p in alle_absaetze(d):
            if p._p in gesehen:
                continue
            gesehen.add(p._p)
            alt = p.text
            neu = f(alt)
            if neu != alt:
                runweise = [f(r.text) for r in p.runs]
                if p.runs and "".join(runweise) == neu:
                    # Treffer liegen je in einem Run: Formatierung (fett, kursiv ...) bleibt erhalten
                    for r, t in zip(p.runs, runweise):
                        if r.text != t:
                            r.text = t
                elif p.runs:
                    p.runs[0].text = neu
                    for r in p.runs[1:]:
                        r.text = ""
                else:
                    p.add_run(neu)
        # Dokumenteigenschaften: Autor und Titel enthalten oft Namen
        cp = d.core_properties
        for feld in ("title", "subject", "comments", "keywords", "category"):
            wert = getattr(cp, feld, "") or ""
            if wert:
                setattr(cp, feld, f(wert))
        cp.author = ""
        cp.last_modified_by = ""
        d.save(str(ziel))
    elif ext == ".xlsx":
        import openpyxl
        wb = openpyxl.load_workbook(str(quelle))
        for ws in wb:
            for row in ws.iter_rows():
                for c in row:
                    if isinstance(c.value, str):
                        c.value = f(c.value)
        wb.save(str(ziel))
    elif ext in (".pdf", ".rtf"):
        ziel.write_text("\n".join(f(z) for z in lese_einheiten(quelle)), encoding="utf-8")
    else:
        sys.exit(f"Format {ext} wird nicht unterstützt. Möglich: .docx .xlsx .txt .md .csv .rtf .pdf")


def rohtext_fuer_leckpruefung(pfad: Path) -> str:
    """Liest möglichst ALLES, auch Textfelder und Fußnoten, für die Schlusskontrolle."""
    ext = pfad.suffix.lower()
    if ext == ".docx" or ext == ".xlsx":
        teile = []
        with zipfile.ZipFile(pfad) as z:
            for n in z.namelist():
                if n.endswith(".xml") or n.endswith(".rels"):
                    teile.append(z.read(n).decode("utf-8", errors="ignore"))
        return re.sub(r"<[^>]+>", " ", "\n".join(teile))
    return pfad.read_text(encoding="utf-8", errors="ignore")


# --------------------------------------------------------------------------
# Erkennung
# --------------------------------------------------------------------------
_nlp = None


def lade_spacy():
    global _nlp
    if _nlp is not None:
        return _nlp
    try:
        import spacy
        for name in ("de_core_news_lg", "de_core_news_md", "de_core_news_sm"):
            try:
                _nlp = spacy.load(name)
                return _nlp
            except Exception:
                continue
    except Exception:
        pass
    _nlp = False
    return _nlp


def namen_aus_text(text, nlp, mit_orten, mit_orgs):
    """Findet Namen mit dem lokalen Sprachmodell (spaCy). Gibt Listen je Kategorie zurück."""
    gefunden = {"PERSON": [], "ORT": [], "ORGANISATION": []}  # Listen mit Wiederholungen
    if not nlp:
        return gefunden
    teile = text if isinstance(text, (list, tuple)) else [text]
    nlp.max_length = max(nlp.max_length, max((len(t) for t in teile), default=0) + 1000)
    ents = [e for doc in nlp.pipe([t for t in teile if t.strip()]) for e in doc.ents]
    for ent in ents:
        s = ent.text.strip()
        if len(s) < 3 or not s[0].isupper() or any(c.isdigit() for c in s) or "\n" in s:
            continue
        if ent.label_ == "PER":
            gefunden["PERSON"].append(s)
        elif ent.label_ == "LOC" and mit_orten:
            gefunden["ORT"].append(s)
        elif ent.label_ == "ORG" and mit_orgs:
            gefunden["ORGANISATION"].append(s)
    return gefunden


class Zuordnung:
    """Verwaltet Original -> Platzhalter."""

    def __init__(self, ignorieren=()):
        self.ignorieren = set(ignorieren) | STOPP
        self.karte = OrderedDict()     # Original -> Platzhalter
        self.zaehler = {}              # Kategorie -> Anzahl
        self.person_teile = {}         # Teilstring -> Personennummer
        self.unsicher = []

    def _neu(self, kat):
        pre = KATEGORIEN_PLATZHALTER[kat]
        self.zaehler[kat] = self.zaehler.get(kat, 0) + 1
        return pre, self.zaehler[kat]

    def hinzu(self, original, kat):
        original = original.strip()
        if not original or original in self.karte:
            return
        if kat == "PERSON" and any(t in self.ignorieren for t in original.split()):
            return
        if kat == "PERSON" and original.endswith("s") and original[:-1] in self.karte:
            return  # Genitiv einer bekannten Person (Kellermanns)
        if kat in ("ORT", "ORGANISATION") and any(original in k for k in self.karte):
            return  # Teilstück einer schon erfassten Angabe (Straße, IBAN ...)
        if kat == "PERSON":
            self._person(original)
        else:
            pre, n = self._neu(kat)
            self.karte[original] = f"[{pre}_{n:02d}]"

    def _person(self, name):
        teile = [t for t in re.split(r"\s+", name) if t]
        # Titel abschneiden
        teile = [t for t in teile if not re.match(r"^(Dr\.|Prof\.|Dipl\.-.*|Herr|Herrn|Frau)$", t)]
        if not teile:
            return
        if len(teile) >= 2 and re.fullmatch(r"[A-ZÄÖÜ]\.", teile[0]) and teile[-1] in self.person_teile:
            n = self.person_teile[teile[-1]]  # „K. Aumann-Fehr“ neben „Kerstin Aumann-Fehr“
            self.karte.setdefault(name, f"[PERSON_{n:02d}]")
            return
        # kennen wir schon jemanden, dessen Teil dieser Name ist?
        if len(teile) == 1 and teile[0] in self.person_teile:
            n = self.person_teile[teile[0]]
            self.karte.setdefault(name, f"[PERSON_{n:02d}]")
            return
        n = None
        if len(teile) >= 2:
            m0 = re.fullmatch(r"\[PERSON_(\d+)\]", self.karte.get(teile[-1], ""))
            if m0:  # Nachname stand bisher allein: dieselbe Person, Nachname wird zu _NACH
                n = int(m0.group(1))
                self.karte[teile[-1]] = f"[PERSON_{n:02d}_NACH]"
        if n is None:
            _, n = self._neu("PERSON")
        voll = " ".join(teile)
        self.karte[name] = f"[PERSON_{n:02d}]"
        self.karte.setdefault(voll, f"[PERSON_{n:02d}]")
        if len(teile) >= 2:
            vor, nach = teile[0], teile[-1]
            if len(vor) >= 3 and vor not in self.karte:
                self.karte[vor] = f"[PERSON_{n:02d}_VOR]"
                self.person_teile.setdefault(vor, n)
            if len(nach) >= 3 and nach not in self.karte:
                self.karte[nach] = f"[PERSON_{n:02d}_NACH]"
                self.person_teile.setdefault(nach, n)
        else:
            self.person_teile.setdefault(teile[0], n)

    def ersetzer(self):
        if not self.karte:
            return lambda t: t
        schluessel = sorted(self.karte, key=len, reverse=True)
        alt = "|".join(re.escape(s) for s in schluessel)
        muster = re.compile(rf"(?<!{W})({alt})((?:e?s|ns)?)(?!{W})")

        def f(text):
            return muster.sub(lambda m: self.karte[m.group(1)] + m.group(2), text)
        return f


def erkenne(einheiten, bekannte_namen, mit_orten, mit_orgs, ignorieren=(), begriffe=()):
    z = Zuordnung(ignorieren)
    text = "\n".join(einheiten)

    # 1) bekannte Namen des Falls (Wortliste) – verlässlichste Quelle
    for n in bekannte_namen:
        z.hinzu(n, "PERSON")

    # 1b) feste Begriffe (Organisationen, Projekt- oder Ortsnamen, die immer ersetzt werden sollen)
    for b in begriffe:
        z.hinzu(b, "ORGANISATION")

    # 2) feste Formen
    for kat, rx, gruppe in PATTERNS:
        for m in (m_ for u_ in einheiten for m_ in rx.finditer(u_)):
            treffer = m.group(gruppe)
            if kat == "TELEFON":
                treffer = treffer.rstrip(" .-/")
            if kat == "ADRESSE" and re.match(r"^\d{5}\s", treffer):
                if treffer.split(None, 1)[1].split()[0] in PLZ_AUSNAHMEN:
                    continue
            if kat == "TELEFON" and len(re.sub(r"\D", "", treffer)) < 7:
                continue
            if kat == "TELEFON" and any(treffer in k for k in z.karte):
                continue  # Teilstück einer IBAN o. Ä.
            if kat == "TELEFON" and re.fullmatch(r"\(?\d{1,2}\.\d{1,2}\.\d{2,4}", treffer.strip()):
                continue  # Datum, keine Nummer
            z.hinzu(treffer, kat)

    # 3) Sprachmodell: Mehrwort-Namen sofort; einzelne Wörter nur mit Beleg
    nlp = lade_spacy()
    gef = namen_aus_text(einheiten, nlp, mit_orten, mit_orgs)
    nach_anrede = {m.group(1).split()[0] for m in ANREDE.finditer(text)}
    z.unsicher = []
    pers = gef["PERSON"]
    mehrfach = [s for s in OrderedDict.fromkeys(pers) if len(s.split()) >= 2]
    mehrfach.sort(key=lambda s: (-len(s.split()), bool(re.match(r"^[A-ZÄÖÜ]\.\s", s))))
    for s_ in mehrfach:
        z.hinzu(s_, "PERSON")
    for s_ in OrderedDict.fromkeys(pers):
        if len(s_.split()) >= 2 or s_ in z.karte:
            continue
        if s_ in STOPP or s_ in z.ignorieren:
            continue
        belegt = pers.count(s_) >= 2 or s_ in nach_anrede or (s_[:-1] in nach_anrede and s_.endswith("s"))
        if belegt:
            z.hinzu(s_, "PERSON")
        else:
            z.unsicher.append(s_)
    for kat in ("ORT", "ORGANISATION"):
        for s_ in OrderedDict.fromkeys(gef[kat]):
            z.hinzu(s_, kat)

    # 3b) Wort mit Großbuchstaben direkt vor einem bekannten Nachnamen = Vorname (Anna-Lena Müller-Lindqvist)
    nachnamen = [k for k, v in z.karte.items()
                 if re.fullmatch(r"\[PERSON_\d+(?:_NACH)?\]", v) and " " not in k and len(k) >= 3]
    TITEL = {"Herr", "Herrn", "Frau", "Dr", "Prof", "Dipl", "med", "Ing", "Dr.", "Prof.", "Dipl.-Ing."}
    for nn in nachnamen:
        for m in re.finditer(rf"(?<![\wäöüÄÖÜß-])({CAP})[ \t]+{re.escape(nn)}(?![\wäöüÄÖÜß])", text):
            vor = m.group(1)
            if any(f"{vor} {nn}" in k for k in z.karte):
                continue
            if vor in z.karte or vor in STOPP or vor in z.ignorieren or vor in TITEL or len(vor) < 3:
                continue
            z.hinzu(f"{vor} {nn}", "PERSON")

    # 4) Anreden: nur, was noch nicht erfasst ist
    for m in ANREDE.finditer(text):
        woerter = m.group(1).split()
        if woerter[0] in z.karte:
            continue
        if woerter[0].endswith("s") and woerter[0][:-1] in z.karte:
            continue
        z.hinzu(woerter[0] if nlp else " ".join(woerter), "PERSON")
    z.unsicher = [u for u in z.unsicher if u not in z.karte]
    return z, bool(nlp)


# --------------------------------------------------------------------------
# Befehle
# --------------------------------------------------------------------------
def lies_namen(arg_namen, namen_datei):
    namen = []
    if arg_namen:
        namen += [n.strip() for n in arg_namen.split(",") if n.strip()]
    if namen_datei:
        namen += [z.strip() for z in Path(namen_datei).read_text(encoding="utf-8").splitlines()
                  if z.strip() and not z.startswith("#")]
    return namen


def cmd_hin(a, nur_pruefen=False):
    quelle = Path(a.datei).resolve()
    einheiten = lese_einheiten(quelle)
    namen = lies_namen(a.namen, a.namen_datei)
    z, hat_nlp = erkenne(einheiten, namen, a.orte, a.orgs, lies_namen(a.ignorieren, None), lies_namen(a.begriffe, None))
    f = z.ersetzer()
    # Kandidaten, die schon in einem ersetzten Eintrag stecken (Genitiv, Adressfragment), sind nicht unsicher
    z.unsicher = [u for u in z.unsicher
                  if not any(k.startswith(u) or u.startswith(k) for k in z.karte if len(k) >= 4)]

    zeilen = []
    zeilen.append(f"# Prüfbericht Pseudonymisierung – {quelle.name}\n")
    if not hat_nlp:
        zeilen.append("**Achtung:** Das lokale Sprachmodell (spaCy) ist nicht installiert. "
                      "Namen werden nur über Anreden und über die Namensliste erkannt. "
                      "Siehe Anleitung, Abschnitt Installation.\n")
    kat_zahl = {}
    for orig, ph in z.karte.items():
        k = re.match(r"\[([A-Z]+)_", ph).group(1)
        kat_zahl[k] = kat_zahl.get(k, 0) + 1
    zeilen.append("## Ersetzt\n")
    for k, n in sorted(kat_zahl.items()):
        zeilen.append(f"- {k}: {n} Schreibweisen")
    zeilen.append("")

    if nur_pruefen:
        zeilen.append("## Trefferliste (nur Trockenlauf)\n")
        for orig, ph in z.karte.items():
            zeilen.append(f"- {ph}  ←  {orig}")
        if z.unsicher:
            zeilen.append("\n## Unsichere Kandidaten – NICHT ersetzt, bitte prüfen\n")
            zeilen += [f"- {u}" for u in z.unsicher]
        print("\n".join(zeilen))
        return

    ordner = Path(a.ausgabe).resolve() if a.ausgabe else quelle.parent / "pseudonymisiert"
    ordner.mkdir(parents=True, exist_ok=True)
    endung = ".txt" if quelle.suffix.lower() in (".pdf", ".rtf") else quelle.suffix
    ziel = ordner / f"{quelle.stem}_pseudonym{endung}"
    schreibe_transformiert(quelle, ziel, f)

    # Zuordnung: bleibt lokal, NIE hochladen
    zu = ordner / f"{quelle.stem}.zuordnung.json"
    zu.write_text(json.dumps({"quelle": quelle.name, "karte": z.karte}, ensure_ascii=False, indent=1),
                  encoding="utf-8")

    # Schlusskontrolle: steht noch ein Original im Ergebnis?
    ergebnis_text = rohtext_fuer_leckpruefung(ziel)
    lecks = [o for o in z.karte if len(o) >= 4 and re.search(rf"(?<!{W}){re.escape(o)}", ergebnis_text)]
    # Zweitprüfung: feste Formen dürfen im Ergebnis nicht mehr vorkommen
    for kat, rx, gruppe in PATTERNS:
        if kat in ("TELEFON", "EMAIL", "IBAN"):
            for m in rx.finditer(ergebnis_text):
                lecks.append(f"{kat}: {m.group(0)}")

    zeilen.append("## Schlusskontrolle\n")
    if lecks:
        zeilen.append("**Es stehen noch Angaben im Ergebnis. Datei NICHT hochladen, bevor das geklärt ist:**\n")
        for l in lecks:
            zeilen.append(f"- {l}")
        zeilen.append("\nHäufigste Ursache: Text in Textfeldern, Fußnoten, Bildern oder Kommentaren.")
    else:
        zeilen.append("Keine bekannte Angabe mehr im Ergebnis gefunden (auch nicht in Textfeldern, "
                      "Kopf- und Fußzeilen, Kommentaren).")
    zeilen.append("")
    if z.unsicher:
        zeilen.append("## Unsichere Kandidaten – NICHT ersetzt, bitte prüfen\n")
        zeilen.append("Das Sprachmodell hält diese Wörter für Namen, nennt sie aber nur einmal. "
                      "Falls es Namen sind: mit --namen ergänzen und neu laufen lassen.\n")
        for u in z.unsicher:
            zeilen.append(f"- {u}")
        zeilen.append("")
    zeilen.append("## Das Werkzeug kann nicht sehen\n")
    zeilen.append("- Namen, die weder in der Namensliste stehen noch vom Sprachmodell erkannt wurden "
                  "(seltene oder fremdsprachige Namen, Tippfehler, Spitznamen)")
    zeilen.append("- Personen, die sich aus dem Zusammenhang erkennen lassen, ohne genannt zu werden "
                  "(„die Geschäftsführerin der Stiftung in Stuttgart“)")
    zeilen.append("- Inhalt in Bildern, Scans und Grafiken")
    zeilen.append("- besondere Kategorien (Gesundheit, Religion u. a.): die bleiben auch ohne Namen heikel")
    zeilen.append("\nDeshalb: Ergebnis kurz überfliegen, bevor es hochgeladen wird.")
    pb = ordner / f"{quelle.stem}.pruefbericht.md"
    pb.write_text("\n".join(zeilen), encoding="utf-8")

    print(f"\nFertig.\n  Zum Hochladen : {ziel}\n  Zuordnung (LOKAL BEHALTEN): {zu}\n  Prüfbericht   : {pb}")
    print(f"  Ersetzt: " + ", ".join(f"{k} {n}" for k, n in sorted(kat_zahl.items())))
    if z.unsicher:
        print("\n  PRÜFEN (nicht ersetzt): " + ", ".join(z.unsicher))
    if lecks:
        print("\n  WARNUNG: Es stehen noch Angaben im Ergebnis. Siehe Prüfbericht.")
    if not hat_nlp:
        print("\n  HINWEIS: Sprachmodell fehlt, Namen nur über Anrede und Namensliste erkannt.")


def cmd_zurueck(a):
    quelle = Path(a.datei).resolve()
    daten = json.loads(Path(a.zuordnung).read_text(encoding="utf-8"))
    karte = daten["karte"]
    # Rückrichtung: Platzhalter -> Original; bei mehreren Originalen je Platzhalter das längste
    rueck = {}
    for orig, ph in karte.items():
        if ph not in rueck or len(orig) > len(rueck[ph]):
            rueck[ph] = orig
    unbekannt = set()

    def f(text):
        def r(m):
            kat = m.group(1) or m.group(4)
            nr = int(m.group(2) or m.group(5))
            teil = m.group(3) or m.group(6)
            key = f"[{kat}_{nr:02d}" + (f"_{teil}" if teil else "") + "]"
            if key in rueck:
                return rueck[key]
            unbekannt.add(key)
            return m.group(0)
        return PLATZHALTER_TOLERANT.sub(r, text)

    endung = ".txt" if quelle.suffix.lower() in (".pdf", ".rtf") else quelle.suffix
    ziel = quelle.with_name(f"{quelle.stem}_klartext{endung}")
    schreibe_transformiert(quelle, ziel, f)
    print(f"Fertig: {ziel}")
    if unbekannt:
        print("Unbekannte Platzhalter (vom Werkzeug erfunden oder verändert):", ", ".join(sorted(unbekannt)))
    # Platzhalter in Einzelteile zerlegt oder abgewandelt?
    rest = re.findall(r"\[(?:PERSON|EMAIL|IBAN|TELEFON|GEBURTSDATUM|ADRESSE|ORT|ORG)[^\]]*\]", rohtext_fuer_leckpruefung(ziel))
    if rest:
        print("Noch offene Platzhalter im Ergebnis:", ", ".join(sorted(set(rest))))


def main():
    p = argparse.ArgumentParser(description="Lokaler Pseudonymisierer")
    sp = p.add_subparsers(dest="cmd", required=True)
    for name in ("hin", "pruefen"):
        s = sp.add_parser(name)
        s.add_argument("datei")
        s.add_argument("--namen", help='Bekannte Namen, durch Komma getrennt: "Anna Muster, Max Test"')
        s.add_argument("--namen-datei", help="Textdatei mit einem Namen pro Zeile")
        s.add_argument("--ignorieren", help='Wörter, die NICHT ersetzt werden sollen: "Sonnenhof, Kita"')
        s.add_argument("--begriffe", help='Immer ersetzen, z. B. Organisationen: "Kita Sonnenhof, Projekt Falke"')
        s.add_argument("--orte", action="store_true", help="Orte ebenfalls ersetzen")
        s.add_argument("--orgs", action="store_true", help="Organisationen ebenfalls ersetzen")
        s.add_argument("--ausgabe", help="Ausgabeordner (Standard: Unterordner 'pseudonymisiert')")
    s = sp.add_parser("zurueck")
    s.add_argument("datei")
    s.add_argument("--zuordnung", required=True)
    a = p.parse_args()
    if a.cmd == "hin":
        cmd_hin(a)
    elif a.cmd == "pruefen":
        cmd_hin(a, nur_pruefen=True)
    else:
        cmd_zurueck(a)


if __name__ == "__main__":
    main()
