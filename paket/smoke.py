"""Rauchtest für ein fertiges Paket. Aufruf: <paketpython> paket/smoke.py <paketordner>"""
import json, os, re, subprocess, sys, tempfile, threading, time, urllib.request
from pathlib import Path

paket = Path(sys.argv[1]).resolve()
app = paket / "app"
py = sys.executable
fehler = []

def pruefe(name, ok, info=""):
    print(("OK   " if ok else "FEHLER"), name, info)
    if not ok:
        fehler.append(name)

# 1) Bausteine und Sprachmodell
r = subprocess.run([py, "-c", "import docx, openpyxl, pypdf, striprtf, spacy; spacy.load('de_core_news_md'); print('bausteine ok')"],
                   capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
pruefe("Bausteine und Sprachmodell", "bausteine ok" in r.stdout, r.stderr[-300:])

# 2) Hin und zurück mit erfundenem Dokument
with tempfile.TemporaryDirectory() as t:
    t = Path(t)
    import docx
    d = docx.Document()
    p = d.add_paragraph("Heute sprach ")
    p.add_run("Frau Dr. Ayşe Kaplan-Reuter").bold = True
    p.add_run(" mit Herrn Tobias Wegener, erreichbar unter t.wegener@beispiel.de oder 07151 987654.")
    d.add_paragraph("Frau Kaplan-Reuter und Herr Wegener vereinbaren einen Termin.")
    d.save(t / "Dokument.docx")
    h = subprocess.run([py, str(app / "pseudonymisieren.py"), "hin", str(t / "Dokument.docx"), f"--ausgabe={t/'out'}"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
    erg = docx.Document(str(t / "out" / "Dokument_pseudonym.docx"))
    text = "\n".join(x.text for x in erg.paragraphs)
    pruefe("Bereinigen ersetzt Namen", "Kaplan" not in text and "Wegener" not in text and "@beispiel" not in text, text[:120])
    pruefe("Keine Warnung", "WARNUNG" not in h.stdout, h.stdout[-200:])
    pruefe("Fettdruck bleibt", any(r.bold for pp in erg.paragraphs for r in pp.runs if "[PERSON" in r.text))
    z = subprocess.run([py, str(app / "pseudonymisieren.py"), "zurueck", str(t / "out" / "Dokument_pseudonym.docx"),
                        f"--zuordnung={t/'out'/'Dokument.zuordnung.json'}"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
    back = docx.Document(str(t / "out" / "Dokument_pseudonym_klartext.docx"))
    pruefe("Zurücksetzen stellt Text her",
           [x.text for x in back.paragraphs] == [x.text for x in d.paragraphs], z.stdout[-200:])

# 3) Oberfläche starten, Seite abrufen, beenden
with tempfile.TemporaryDirectory() as t:
    env = dict(os.environ, PSEUDO_KEIN_BROWSER="1", PSEUDO_ERGEBNISSE=t, PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")
    srv = subprocess.Popen([py, str(app / "oberflaeche.py")], stdout=subprocess.PIPE, text=True, encoding="utf-8", errors="replace", env=env)
    wache = threading.Timer(90, srv.kill)
    wache.start()
    url = None
    for _ in range(40):
        zeile = srv.stdout.readline()
        m = re.search(r"http://127\.0\.0\.1:\d+/\?t=\S+", zeile)
        if m:
            url = m.group(0)
            break
        time.sleep(0.25)
    pruefe("Oberfläche startet", url is not None)
    if url:
        seite = urllib.request.urlopen(url, timeout=10).read().decode("utf-8")
        pruefe("Seite lädt", "Pseudonymisierer" in seite)
        token = url.split("t=")[1]
        base = url.split("/?")[0]
        st = json.loads(urllib.request.urlopen(f"{base}/api/status?t={token}", timeout=10).read())
        pruefe("Sprachmodell wird gefunden", st.get("nlp") is True, str(st))
        req = urllib.request.Request(f"{base}/api/ende", method="POST", headers={"X-Token": token})
        urllib.request.urlopen(req, timeout=10).read()
    wache.cancel()
    try:
        srv.wait(timeout=10)
    except Exception:
        srv.kill()

print("\nERGEBNIS:", "alles in Ordnung" if not fehler else "Fehler bei: " + ", ".join(fehler))
sys.exit(1 if fehler else 0)
