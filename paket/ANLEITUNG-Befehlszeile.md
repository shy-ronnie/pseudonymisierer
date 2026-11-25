# Pseudonymisierer – Bedienung ohne Terminal

**Start:** Doppelklick auf `Pseudonymisierer-Start.command` (Mac) oder `Pseudonymisierer-Start.bat` (Windows). Beim allerersten Mal richtet sich das Programm selbst ein (einige Minuten, Internet nötig). Danach öffnet sich eine Seite im Browser. Sie läuft nur auf diesem Rechner. Das schwarze Fenster im Hintergrund offen lassen, solange Sie arbeiten.

**Mac, erster Start:** Öffnet macOS die Datei nicht („nicht verifizierter Entwickler“), mit Rechtsklick auf die Datei, dann „Öffnen“ und noch einmal „Öffnen“ bestätigen. Falls die Datei nicht startet: einmal im Terminal `chmod +x Pseudonymisierer-Start.command` im Programmordner.

**Ablauf in der Seite:**
1. *Bereinigen:* Dokument hineinziehen, Namen eintragen (ein Name pro Zeile), „Erst prüfen“ für den Trockenlauf oder „Bereinigen“. Die bereinigte Datei laden.
2. *Auswerten lassen:* Datei im KI-Werkzeug hochladen, Anweisung „Verwende die Platzhalter wie [PERSON_01] im Text unverändert.“ mitgeben.
3. *Zurücksetzen:* Dokument wählen, Antwort als Datei hineinziehen oder Text einfügen, „Namen zurücksetzen“.

**Wo liegt was:** Alles in `Pseudonymisierer-Ergebnisse` im Benutzerordner, je Lauf ein Ordner mit Datum und Uhrzeit. Darin steht auch die Zuordnung (`….zuordnung.json`). Sie bleibt auf diesem Rechner und wird nie hochgeladen. „Diesen Lauf löschen“ in Schritt 3 entfernt den Ordner samt Zuordnung. Der Dateiname Ihres Dokuments wird absichtlich nicht übernommen, weil er selbst einen Namen enthalten kann.

**Grenzen:** wie unten für die Befehlszeile. Die Seite ersetzt nur die Bedienung, nicht die Erkennung.

---

# Befehlszeile (für Fortgeschrittene)

# Pseudonymisierer – Prototyp

Ersetzt Namen, Adressen, Telefonnummern, E-Mail-Adressen, IBANs und Geburtsdaten durch Platzhalter, bevor ein Dokument in Claude, ChatGPT oder Copilot geladen wird. Nach der Auswertung setzt das Werkzeug die Originale wieder ein.

Alles läuft auf deinem Rechner. Es wird nichts versendet.

## Ablauf in drei Schritten

1. **Hin:** Dokument bereinigen
2. **Auswerten:** die bereinigte Datei in das KI-Werkzeug laden und die Auswertung machen lassen
3. **Zurück:** die Antwort mit den Originalen füllen

## Einmalige Installation (Terminal auf dem Mac)

```
pip3 install python-docx openpyxl pypdf striprtf spacy
pip3 install https://github.com/explosion/spacy-models/releases/download/de_core_news_md-3.8.0/de_core_news_md-3.8.0-py3-none-any.whl
```

Der zweite Befehl lädt das deutsche Sprachmodell, das Namen im Fließtext erkennt. Danach arbeitet alles ohne Internet. Ohne dieses Modell erkennt das Werkzeug Namen nur über die Namensliste und über Anreden wie „Frau“ oder „Dr.“. Das meldet es dir bei jedem Lauf.

## Befehle

**Hin**

```
python3 pseudonymisieren.py hin Bericht.docx --namen "Anna Muster, Max Test"
```

Das Ergebnis liegt im Unterordner `pseudonymisiert/` neben der Originaldatei:

| Datei | Verwendung |
|---|---|
| `Bericht_pseudonym.docx` | **Diese Datei hochladen** |
| `Bericht.zuordnung.json` | Enthält die Originale. **Lokal behalten, nie hochladen, nicht in Dropbox oder Google Drive legen.** |
| `Bericht.pruefbericht.md` | Was ersetzt wurde, Schlusskontrolle, unsichere Kandidaten |

**Zurück**

```
python3 pseudonymisieren.py zurueck Auswertung.docx --zuordnung Bericht.zuordnung.json
```

Ergebnis: `Auswertung_klartext.docx`.

**Nur ansehen, nichts schreiben**

```
python3 pseudonymisieren.py pruefen Bericht.docx
```

## Optionen

| Option | Wirkung |
|---|---|
| `--namen "A B, C D"` | Namen, die der Fall sicher enthält. Die verlässlichste Quelle, weil sie nicht geraten wird. |
| `--namen-datei liste.txt` | Dasselbe als Textdatei, ein Name pro Zeile |
| `--ignorieren "Sonnenhof"` | Wörter, die stehen bleiben sollen |
| `--begriffe "Kita Sonnenhof, Projekt Falke"` | Organisationen, Projekt- oder Ortsnamen, die immer ersetzt werden sollen. Verlässlicher als `--orgs`. |
| `--orte` | Orte vom Sprachmodell erkennen lassen und ersetzen (Standard: Orte bleiben). Trefferquote mäßig. |
| `--orgs` | Organisationen vom Sprachmodell erkennen lassen und ersetzen (Standard: bleiben). Trefferquote mäßig, besser `--begriffe`. |
| `--ausgabe ORDNER` | anderer Ausgabeordner |

## Formate

Word (`.docx`, mit Tabellen, Kopf- und Fußzeilen), Excel (`.xlsx`), Text (`.txt`, `.md`, `.csv`), RTF aus dem Mac-Texteditor und PDF mit Textebene. Aus RTF und PDF entsteht eine Textdatei. Gescannte PDFs brauchen vorher eine lokale Texterkennung.

## Was die Platzhalter bedeuten

- `[PERSON_01]` ist Anna Muster. `[PERSON_01_VOR]` ist „Anna“ allein, `[PERSON_01_NACH]` ist „Muster“ allein. Das KI-Werkzeug erkennt so, dass dieselbe Person gemeint ist.
- Gleiche Angabe, gleicher Platzhalter. Die Auswertung bleibt deshalb inhaltlich stimmig.
- Das Genitiv-s steht außerhalb des Platzhalters („[PERSON_01_NACH]s Sohn“).

## Wo das Werkzeug Grenzen hat

- **Namen, die niemand nennt.** Seltene Namen, Tippfehler und Spitznamen erkennt das Sprachmodell nicht zuverlässig. Wer im Dokument vorkommt, gehört in `--namen`.
- **Einzelne Wörter.** Ein Name, der nur ein einziges Mal und ohne Anrede vorkommt, wird nicht ersetzt, sondern im Prüfbericht unter „Unsichere Kandidaten“ aufgeführt. So stehen Fehlalarme („Beratungsbericht“) nicht im Text, und echte Namen fallen trotzdem auf.
- **Zusammenhänge.** „Die Geschäftsführerin der Stiftung in Stuttgart“ nennt keinen Namen und ist trotzdem erkennbar.
- **Bilder und Scans.** Text in Grafiken wird nicht gelesen.
- **Familien mit gleichem Nachnamen.** „Kellermann“ allein wird der zuerst genannten Person zugeordnet. Die Rückübersetzung bleibt davon unberührt, weil sie das Wort selbst wieder einsetzt.
- **Rechtlich** bleiben pseudonymisierte Daten personenbezogen, solange die Zuordnungsdatei existiert. Das Risiko sinkt stark, ist aber nicht null. Besondere Kategorien (Gesundheit, Religion, Herkunft) bleiben auch ohne Namen heikel.

## Schlusskontrolle

Nach jedem Lauf liest das Werkzeug die fertige Datei noch einmal vollständig, auch Textfelder, Kommentare und Fußnoten, und prüft, ob eines der ersetzten Originale noch irgendwo steht. Wenn ja, meldet es das im Terminal und im Prüfbericht. In dem Fall die Datei nicht hochladen.

## Nächste Ausbaustufen

- Lokales Sprachmodell über Ollama als zweiter Blick auf Namen, die das Standardmodell übersieht
- Ordnerlauf für viele Dateien
- Einfache Oberfläche für Anwender ohne Terminal
- Schwärzung direkt im PDF-Layout (mit Texterkennung für Scans)
