#!/usr/bin/env python3
"""Pseudonymisierer – Oberfläche im Browser.

Startet einen kleinen Server, der NUR auf diesem Rechner (127.0.0.1) lauscht, und öffnet die Seite
im Standardbrowser. Es wird nichts ins Internet gesendet. Die eigentliche Arbeit macht
pseudonymisieren.py; diese Datei ist nur die Bedienung davor.

Ergebnisse liegen in ~/Pseudonymisierer-Ergebnisse/ (abweichend: Umgebungsvariable PSEUDO_ERGEBNISSE).
"""
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import threading
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.util import find_spec
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

BASIS = Path(__file__).resolve().parent
KERN = BASIS / "pseudonymisieren.py"
ERGEBNISSE = Path(os.environ.get("PSEUDO_ERGEBNISSE") or (Path.home() / "Pseudonymisierer-Ergebnisse"))
TOKEN = secrets.token_urlsafe(18)
MAX_BYTES = 60 * 1024 * 1024
ERLAUBT = {".docx", ".xlsx", ".pdf", ".txt", ".md", ".csv", ".rtf"}
LAUF_ID = re.compile(r"^\d{4}-\d{2}-\d{2}_\d{6}$")
PORT = 0


def nlp_da():
    try:
        return bool(find_spec("spacy") and find_spec("de_core_news_md"))
    except Exception:
        return False


def lauf_ordner(lauf_id):
    if not LAUF_ID.match(lauf_id or ""):
        return None
    p = ERGEBNISSE / lauf_id
    return p if p.is_dir() else None


def liste_laeufe():
    aus = []
    if not ERGEBNISSE.is_dir():
        return aus
    for d in sorted(ERGEBNISSE.iterdir(), reverse=True):
        if not (d.is_dir() and LAUF_ID.match(d.name)):
            continue
        meta = {}
        try:
            meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
        except Exception:
            pass
        if not any(d.glob("*.zuordnung.json")):
            continue
        zeit = datetime.strptime(d.name, "%Y-%m-%d_%H%M%S")
        aus.append({
            "id": d.name,
            "zeit": zeit.strftime("%d.%m. %H:%M"),
            "label": meta.get("label", ""),
            "ersetzt": meta.get("ersetzt", ""),
            "dateien": sorted(f.name for f in d.iterdir()
                              if f.is_file() and not f.name.endswith(".zuordnung.json") and f.name != "meta.json"),
        })
    return aus


def starte_kern(args, timeout=600):
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    r = subprocess.run([sys.executable, str(KERN), *args], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=timeout, env=env, cwd=str(BASIS))
    return r.returncode, r.stdout, r.stderr


def fehlertext(stderr):
    zeilen = [z for z in (stderr or "").strip().splitlines() if z.strip()]
    if not zeilen:
        return "Unbekannter Fehler."
    if zeilen[0].startswith("Traceback") or any(z.startswith("Traceback") for z in zeilen):
        return "Unerwarteter Fehler: " + zeilen[-1]
    return "\n".join(zeilen)


def namen_arg(text):
    teile = []
    for z in (text or "").replace(";", "\n").splitlines():
        z = z.strip().replace(",", " ")
        z = re.sub(r"\s+", " ", z)
        if z:
            teile.append(z)
    return ",".join(teile)


def optionen_args(opt):
    a = []
    for feld, flag in (("namen", "--namen"), ("ignorieren", "--ignorieren"), ("begriffe", "--begriffe")):
        w = namen_arg(opt.get(feld, ""))
        if w:
            a.append(f"{flag}={w}")
    if opt.get("orte"):
        a.append("--orte")
    if opt.get("orgs"):
        a.append("--orgs")
    return a


def oeffne_ordner(pfad):
    try:
        if sys.platform == "darwin":
            subprocess.Popen(["open", str(pfad)])
        elif os.name == "nt":
            os.startfile(str(pfad))  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["xdg-open", str(pfad)])
        return True
    except Exception:
        return False


class Handler(BaseHTTPRequestHandler):
    server_version = "Pseudonymisierer"

    def log_message(self, *a):
        pass

    # ---- Hilfen ----
    def _host_ok(self):
        return (self.headers.get("Host") or "") in (f"127.0.0.1:{PORT}", f"localhost:{PORT}")

    def _token_ok(self, q):
        return secrets.compare_digest((self.headers.get("X-Token") or (q.get("t") or [""])[0]), TOKEN)

    def _json(self, obj, code=200):
        b = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(b)

    def _abweisen(self, code=403, text="Nicht erlaubt."):
        b = text.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    # ---- GET ----
    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if not self._host_ok():
            return self._abweisen()
        if u.path == "/":
            if not self._token_ok(q):
                return self._abweisen(403, "Bitte die Seite über das Startsymbol öffnen.")
            b = SEITE.replace("__TOKEN__", TOKEN).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(b)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(b)
            return
        if not self._token_ok(q):
            return self._abweisen()
        if u.path == "/api/status":
            return self._json({"nlp": nlp_da(), "ordner": str(ERGEBNISSE)})
        if u.path == "/api/laeufe":
            return self._json({"laeufe": liste_laeufe()})
        if u.path == "/api/datei":
            d = lauf_ordner((q.get("lauf") or [""])[0])
            name = (q.get("name") or [""])[0]
            if not d or "/" in name or "\\" in name or name.endswith(".zuordnung.json") or name == "meta.json":
                return self._abweisen(404, "Nicht gefunden.")
            f = d / name
            if not f.is_file():
                return self._abweisen(404, "Nicht gefunden.")
            data = f.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{quote(name)}")
            self.end_headers()
            self.wfile.write(data)
            return
        self._abweisen(404, "Nicht gefunden.")

    # ---- POST ----
    def do_POST(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if not (self._host_ok() and self._token_ok(q)):
            return self._abweisen()
        laenge = int(self.headers.get("Content-Length") or 0)
        if laenge > MAX_BYTES:
            return self._json({"ok": False, "fehler": "Die Datei ist zu groß (Grenze 60 MB)."}, 413)
        body = self.rfile.read(laenge) if laenge else b""
        try:
            opt = json.loads(unquote(self.headers.get("X-Optionen") or "{}"))
        except Exception:
            opt = {}
        name = unquote(self.headers.get("X-Dateiname") or "")
        try:
            if u.path == "/api/pruefen":
                return self._json(self.lauf(body, name, opt, nur_pruefen=True))
            if u.path == "/api/bereinigen":
                return self._json(self.lauf(body, name, opt, nur_pruefen=False))
            if u.path == "/api/zurueck":
                return self._json(self.zurueck(body, name, opt))
            if u.path == "/api/oeffnen":
                d = lauf_ordner(opt.get("lauf", "")) if opt.get("lauf") else ERGEBNISSE
                if d is None:
                    return self._json({"ok": False, "fehler": "Ordner nicht gefunden."})
                ERGEBNISSE.mkdir(parents=True, exist_ok=True)
                return self._json({"ok": oeffne_ordner(d), "pfad": str(d)})
            if u.path == "/api/loeschen":
                d = lauf_ordner(opt.get("lauf", ""))
                if d is None:
                    return self._json({"ok": False, "fehler": "Lauf nicht gefunden."})
                shutil.rmtree(d)
                return self._json({"ok": True})
            if u.path == "/api/ende":
                self._json({"ok": True})
                threading.Thread(target=self.server.shutdown, daemon=True).start()
                return
        except subprocess.TimeoutExpired:
            return self._json({"ok": False, "fehler": "Das Dokument braucht ungewöhnlich lange. Abgebrochen."})
        except Exception as e:  # noqa: BLE001
            return self._json({"ok": False, "fehler": f"Unerwarteter Fehler: {e}"})
        self._abweisen(404, "Nicht gefunden.")

    def lauf(self, body, name, opt, nur_pruefen):
        ext = Path(name).suffix.lower()
        if ext not in ERLAUBT:
            return {"ok": False, "fehler": f"Dieses Format wird nicht unterstützt. Möglich: "
                                           f"{' '.join(sorted(ERLAUBT))}"}
        if not body:
            return {"ok": False, "fehler": "Die Datei ist leer."}
        with tempfile.TemporaryDirectory(prefix="pseudo_") as tmp:
            # Neutraler Dateiname: Der Originalname kann selbst einen Namen enthalten.
            quelle = Path(tmp) / f"Dokument{ext}"
            quelle.write_bytes(body)
            if nur_pruefen:
                rc, out, err = starte_kern(["pruefen", str(quelle), *optionen_args(opt)])
                if rc != 0:
                    return {"ok": False, "fehler": fehlertext(err)}
                out = out.replace("mit --namen ergänzen und neu laufen lassen",
                                  "oben in die Namensliste eintragen und neu bereinigen")
                return {"ok": True, "bericht": out, "gespeichert": False}
            lauf_id = datetime.now().strftime("%Y-%m-%d_%H%M%S")
            ordner = ERGEBNISSE / lauf_id
            ordner.mkdir(parents=True, exist_ok=True)
            rc, out, err = starte_kern(["hin", str(quelle), *optionen_args(opt), f"--ausgabe={ordner}"])
            if rc != 0:
                shutil.rmtree(ordner, ignore_errors=True)
                return {"ok": False, "fehler": fehlertext(err)}
            m = re.search(r"Ersetzt:\s*(.+)", out)
            meta = {"label": name, "ersetzt": m.group(1).strip() if m else "", "endung": ext}
            (ordner / "meta.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
            bericht = ""
            pb = ordner / "Dokument.pruefbericht.md"
            if pb.exists():
                bericht = pb.read_text(encoding="utf-8")
                bericht = bericht.replace("mit --namen ergänzen und neu laufen lassen",
                                          "oben in die Namensliste eintragen und neu bereinigen")
            hochladen = [f.name for f in ordner.iterdir()
                         if f.name.startswith("Dokument_pseudonym")]
            return {"ok": True, "lauf": lauf_id, "bericht": bericht, "hochladen": hochladen[0] if hochladen else "",
                    "warnung": "WARNUNG" in out, "pruefen": "PRÜFEN" in out, "ordner": str(ordner),
                    "gespeichert": True}

    def zurueck(self, body, name, opt):
        d = lauf_ordner(opt.get("lauf", ""))
        if d is None:
            return {"ok": False, "fehler": "Der gewählte Lauf wurde nicht gefunden."}
        zu = next(iter(d.glob("*.zuordnung.json")), None)
        if zu is None:
            return {"ok": False, "fehler": "In diesem Lauf fehlt die Zuordnung."}
        if opt.get("text"):
            body, ext = opt["text"].encode("utf-8"), ".txt"
        else:
            ext = Path(name).suffix.lower()
            if ext not in ERLAUBT:
                return {"ok": False, "fehler": "Dieses Format wird nicht unterstützt."}
        if not body:
            return {"ok": False, "fehler": "Keine Antwort angegeben."}
        with tempfile.TemporaryDirectory(prefix="pseudo_") as tmp:
            antwort = Path(tmp) / f"Antwort{ext}"
            antwort.write_bytes(body)
            rc, out, err = starte_kern(["zurueck", str(antwort), f"--zuordnung={zu}"])
            if rc != 0:
                return {"ok": False, "fehler": fehlertext(err)}
            ergebnis = next(iter(Path(tmp).glob("Antwort_klartext*")), None)
            if ergebnis is None:
                return {"ok": False, "fehler": "Es ist kein Ergebnis entstanden."}
            n = 1
            while any(d.glob(f"Antwort-{n:02d}_klartext.*")):
                n += 1
            ziel = d / f"Antwort-{n:02d}_klartext{ergebnis.suffix}"
            shutil.copy2(ergebnis, ziel)
        hinweise = [z.strip() for z in out.splitlines()
                    if z.startswith(("Unbekannte Platzhalter", "Noch offene Platzhalter"))]
        text = ""
        if ziel.suffix.lower() in (".txt", ".md", ".csv") and ziel.stat().st_size < 400_000:
            text = ziel.read_text(encoding="utf-8", errors="replace")
        return {"ok": True, "lauf": d.name, "datei": ziel.name, "hinweise": hinweise, "text": text}


def main():
    global PORT
    ERGEBNISSE.mkdir(parents=True, exist_ok=True)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    PORT = srv.server_address[1]
    url = f"http://127.0.0.1:{PORT}/?t={TOKEN}"
    print("Pseudonymisierer läuft. Diese Seite öffnet sich im Browser:")
    print(f"  {url}")
    print("Dieses Fenster offen lassen, solange Sie arbeiten. Beenden: Schaltfläche 'Beenden' im Browser "
          "oder dieses Fenster schließen.")
    if not os.environ.get("PSEUDO_KEIN_BROWSER"):
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()


SEITE = r"""<!doctype html>
<html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Pseudonymisierer</title>
<style>
:root{--ak:#1F3864;--gr:#595959;--li:#d9dee6;--bg:#f6f7f9;--ok:#1d6b3a;--okb:#e8f4ec;--wa:#8a5a00;--wab:#fff4dc;--er:#a12626;--erb:#fbe9e9}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:#111;font:15px/1.5 -apple-system,"Segoe UI",Helvetica,Arial,sans-serif}
header{background:#fff;border-bottom:1px solid var(--li);padding:18px 24px}
header h1{margin:0;font-size:20px;color:var(--ak)}
header p{margin:2px 0 0;color:var(--gr);font-size:13px}
main{max-width:820px;margin:0 auto;padding:20px 24px 60px}
.tabs{display:flex;gap:6px;margin:6px 0 16px}
.tab{flex:1;padding:10px 12px;border:1px solid var(--li);background:#fff;border-radius:8px;cursor:pointer;font:inherit;color:var(--gr);text-align:left}
.tab b{display:block;color:#111}
.tab.on{border-color:var(--ak);box-shadow:inset 0 0 0 1px var(--ak);color:var(--ak)}
.tab.on b{color:var(--ak)}
.karte{background:#fff;border:1px solid var(--li);border-radius:10px;padding:18px 20px;margin-bottom:14px}
.karte h2{margin:0 0 8px;font-size:16px}
label{display:block;font-weight:600;margin:14px 0 4px}
.hilfe{color:var(--gr);font-size:13px;margin:2px 0 6px}
textarea,select{width:100%;font:inherit;padding:8px 10px;border:1px solid #b9c1cd;border-radius:6px;background:#fff}
textarea{min-height:92px;resize:vertical}
.drop{border:2px dashed #aab4c3;border-radius:10px;padding:26px 14px;text-align:center;color:var(--gr);cursor:pointer;background:#fbfcfd}
.drop.ueber{border-color:var(--ak);background:#eef2f9}
.drop.voll{border-style:solid;border-color:var(--ak);color:#111}
.drop small{display:block;margin-top:4px}
button.b{font:inherit;padding:9px 16px;border-radius:7px;border:1px solid var(--ak);cursor:pointer}
button.pri{background:var(--ak);color:#fff}
button.sek{background:#fff;color:var(--ak)}
button.b:disabled{opacity:.45;cursor:default}
.zeile{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-top:16px}
.box{border-radius:8px;padding:12px 14px;margin:12px 0;border:1px solid}
.box.ok{background:var(--okb);border-color:#9fcfb0;color:var(--ok)}
.box.wa{background:var(--wab);border-color:#e6c77a;color:var(--wa)}
.box.er{background:var(--erb);border-color:#e3a3a3;color:var(--er)}
.box b{display:block;margin-bottom:2px}
.bericht{font-size:14px}
.bericht h3{font-size:14px;margin:14px 0 4px}
.bericht ul{margin:2px 0 6px;padding-left:20px}
.bericht p{margin:4px 0}
code.p{background:#eef1f5;padding:1px 5px;border-radius:4px;font-size:13px}
details{margin-top:12px}
summary{cursor:pointer;color:var(--ak);font-weight:600}
.cb{display:flex;gap:8px;align-items:flex-start;margin:8px 0;font-weight:400}
.cb input{margin-top:4px}
.kopie{display:flex;gap:8px;align-items:stretch}
.kopie div{flex:1;background:#eef1f5;border-radius:6px;padding:9px 12px;font-family:ui-monospace,Menlo,Consolas,monospace;font-size:14px}
.warn{font-weight:700;color:var(--er)}
.rand{display:flex;justify-content:space-between;align-items:center;margin-top:26px;color:var(--gr);font-size:13px}
.rand a{color:var(--ak);cursor:pointer;text-decoration:underline}
.spin{display:inline-block;width:14px;height:14px;border:2px solid #cbd3e0;border-top-color:var(--ak);border-radius:50%;animation:s 0.8s linear infinite;vertical-align:-2px;margin-right:6px}
@keyframes s{to{transform:rotate(360deg)}}
.hidden{display:none}
</style></head><body>
<header><h1>Pseudonymisierer</h1>
<p>Läuft nur auf diesem Rechner. Es wird nichts ins Internet gesendet. Namen werden ersetzt, bevor ein Dokument an eine KI geht, und danach wieder eingesetzt.</p></header>
<main>
<div id="nlpwarn" class="box wa hidden"><b>Sprachmodell fehlt</b>Ohne das lokale Sprachmodell erkennt das Programm Namen nur über Ihre Namensliste und über Anreden wie „Frau“ oder „Dr.“. Bitte die Einrichtung noch einmal ausführen.</div>

<div class="tabs">
<button class="tab on" data-t="t1"><b>1 Bereinigen</b>Namen durch Platzhalter ersetzen</button>
<button class="tab" data-t="t2"><b>2 Auswerten lassen</b>In ChatGPT, Claude &amp; Co.</button>
<button class="tab" data-t="t3"><b>3 Zurücksetzen</b>Namen wieder einsetzen</button>
</div>

<section id="t1">
<div class="karte">
<h2>Dokument wählen</h2>
<div class="drop" id="drop1" tabindex="0">Datei hierher ziehen oder klicken<small>Word, Excel, PDF mit Text, Textdatei, RTF</small></div>
<input type="file" id="f1" class="hidden" accept=".docx,.xlsx,.pdf,.txt,.md,.csv,.rtf">
<label for="namen">Wer kommt im Dokument vor?</label>
<div class="hilfe">Ein Name pro Zeile, mit Vor- und Nachnamen, auch Spitznamen und Kurzformen. Das Programm findet zusätzlich vieles selbst, aber nicht alles.</div>
<textarea id="namen" placeholder="Anna Muster&#10;Max Beispiel&#10;Bene"></textarea>
<details><summary>Weitere Angaben</summary>
<label for="begriffe">Immer ersetzen (Organisationen, Projektnamen)</label>
<div class="hilfe">Ein Eintrag pro Zeile, zum Beispiel eine Einrichtung oder ein Vorhaben.</div>
<textarea id="begriffe" style="min-height:60px"></textarea>
<label for="ignorieren">Nie ersetzen</label>
<div class="hilfe">Wörter, die das Programm fälschlich für Namen hält. Ein Eintrag pro Zeile.</div>
<textarea id="ignorieren" style="min-height:60px"></textarea>
<label class="cb"><input type="checkbox" id="orte"><span>Orte automatisch erkennen und ersetzen (Trefferquote mäßig)</span></label>
<label class="cb"><input type="checkbox" id="orgs"><span>Organisationen automatisch erkennen und ersetzen (Trefferquote mäßig, besser oben eintragen)</span></label>
</details>
<div class="zeile">
<button class="b sek" id="bPruefen" disabled>Erst prüfen (nichts wird gespeichert)</button>
<button class="b pri" id="bHin" disabled>Bereinigen</button>
</div>
</div>
<div id="res1"></div>
</section>

<section id="t2" class="hidden">
<div class="karte">
<h2>Bereinigte Datei in die KI laden</h2>
<p>Laden Sie nur die Datei hoch, die Schritt 1 erzeugt hat, nie die Datei mit der Zuordnung. Geben Sie dazu diese Anweisung mit:</p>
<div class="kopie"><div id="anw">Verwende die Platzhalter wie [PERSON_01] im Text unverändert.</div><button class="b sek" id="bAnw">Kopieren</button></div>
<p class="hilfe" style="margin-top:12px">Ergänzen Sie dann Ihre eigentliche Aufgabe, zum Beispiel „Schreibe einen kurzen Gesprächsvermerk für die Akte“.</p>
<h2 style="margin-top:20px">Antwort sichern</h2>
<p>Speichern Sie die Antwort als Datei (Word, Text, PDF) oder kopieren Sie den Text. Beides geht in Schritt 3.</p>
<p class="hilfe">Prüfen Sie vor dem Hochladen, ob in Ihrem KI-Werkzeug Training mit Ihren Eingaben ausgeschaltet ist und ob Sie ein Konto mit Vertrag zur Auftragsverarbeitung nutzen. Bereinigt heißt nicht anonym: Rolle, Ort und Anlass können eine Person weiterhin verraten.</p>
</div>
</section>

<section id="t3" class="hidden">
<div class="karte">
<h2>Antwort zurücksetzen</h2>
<label for="lauf">Zu welchem Dokument gehört die Antwort?</label>
<select id="lauf"></select>
<div class="hilfe" id="laufhinweis"></div>
<label>Antwort der KI</label>
<div class="drop" id="drop3" tabindex="0">Antwort-Datei hierher ziehen oder klicken<small>oder unten den Text einfügen</small></div>
<input type="file" id="f3" class="hidden" accept=".docx,.xlsx,.pdf,.txt,.md,.csv,.rtf">
<textarea id="antwortText" placeholder="Hier den kopierten Antworttext einfügen" style="margin-top:10px"></textarea>
<div class="zeile">
<button class="b pri" id="bZurueck" disabled>Namen zurücksetzen</button>
<button class="b sek" id="bLoesch" disabled>Diesen Lauf löschen</button>
</div>
</div>
<div id="res3"></div>
</section>

<div class="rand"><span>Ergebnisse liegen in <a id="ordnerLink">diesem Ordner</a>. Die Zuordnung darin nie hochladen.</span><a id="ende">Beenden</a></div>
</main>
<script>
const TOKEN="__TOKEN__";
const $=s=>document.querySelector(s);
let datei1=null,datei3=null,laeufe=[];
function api(pfad,opt,datei,body){
  const h={"X-Token":TOKEN,"X-Optionen":encodeURIComponent(JSON.stringify(opt||{})),"X-Dateiname":encodeURIComponent(datei?datei.name:"")};
  return fetch(pfad,{method:"POST",headers:h,body:body||datei||""}).then(r=>r.json());
}
function esc(s){return String(s).replace(/[&<>]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;"}[c]))}
function md(t){
  const out=[];let liste=false;
  for(const z of t.split("\n")){
    let m;
    if(m=z.match(/^#{1,3}\s+(.*)/)){if(liste){out.push("</ul>");liste=false}out.push("<h3>"+inl(m[1])+"</h3>")}
    else if(m=z.match(/^-\s+(.*)/)){if(!liste){out.push("<ul>");liste=true}out.push("<li>"+inl(m[1])+"</li>")}
    else if(z.trim()===""){if(liste){out.push("</ul>");liste=false}}
    else{if(liste){out.push("</ul>");liste=false}out.push("<p>"+inl(z)+"</p>")}
  }
  if(liste)out.push("</ul>");return out.join("");
}
function inl(s){return esc(s).replace(/\*\*(.+?)\*\*/g,"<b>$1</b>").replace(/(\[[A-ZÄÖÜ]+_\d+(?:_(?:VOR|NACH))?\])/g,'<code class="p">$1</code>')}
function dl(lauf,name){return "/api/datei?lauf="+encodeURIComponent(lauf)+"&name="+encodeURIComponent(name)+"&t="+TOKEN}
function busy(el,text){el.innerHTML='<div class="box wa"><span class="spin"></span>'+text+'</div>'}
function zuTab(id){
  document.querySelectorAll("section").forEach(s=>s.classList.toggle("hidden",s.id!==id));
  document.querySelectorAll(".tab").forEach(b=>b.classList.toggle("on",b.dataset.t===id));
  if(id==="t3")ladeLaeufe();
}
document.querySelectorAll(".tab").forEach(b=>b.onclick=()=>zuTab(b.dataset.t));

function dropzone(zone,input,setzen){
  zone.onclick=()=>input.click();
  zone.onkeydown=e=>{if(e.key==="Enter"||e.key===" ")input.click()};
  input.onchange=()=>{if(input.files[0])setzen(input.files[0])};
  ["dragenter","dragover"].forEach(ev=>zone.addEventListener(ev,e=>{e.preventDefault();zone.classList.add("ueber")}));
  ["dragleave","drop"].forEach(ev=>zone.addEventListener(ev,e=>{e.preventDefault();zone.classList.remove("ueber")}));
  zone.addEventListener("drop",e=>{if(e.dataTransfer.files[0])setzen(e.dataTransfer.files[0])});
}
function zeigeDatei(zone,f){zone.classList.add("voll");zone.innerHTML="<b>"+esc(f.name)+"</b><small>Anderes Dokument: erneut klicken oder ziehen</small>"}
dropzone($("#drop1"),$("#f1"),f=>{datei1=f;zeigeDatei($("#drop1"),f);$("#bPruefen").disabled=false;$("#bHin").disabled=false;$("#res1").innerHTML=""});
dropzone($("#drop3"),$("#f3"),f=>{datei3=f;zeigeDatei($("#drop3"),f);$("#antwortText").value="";pruefeZurueck()});
// Verhindert, dass der Browser eine danebengezogene Datei öffnet
["dragover","drop"].forEach(ev=>window.addEventListener(ev,e=>e.preventDefault()));

function optionen(){return{namen:$("#namen").value,begriffe:$("#begriffe").value,ignorieren:$("#ignorieren").value,orte:$("#orte").checked,orgs:$("#orgs").checked}}

$("#bPruefen").onclick=async()=>{
  busy($("#res1"),"Dokument wird geprüft …");
  const r=await api("/api/pruefen",optionen(),datei1,await datei1.arrayBuffer());
  if(!r.ok){$("#res1").innerHTML='<div class="box er"><b>Das hat nicht geklappt</b>'+esc(r.fehler).replace(/\n/g,"<br>")+"</div>";return}
  $("#res1").innerHTML='<div class="box wa"><b>Trockenlauf: Es wurde nichts gespeichert</b>So würde ersetzt. Fehlt ein Name? Oben ergänzen und erneut prüfen.</div><div class="karte bericht">'+md(r.bericht)+"</div>";
};
$("#bHin").onclick=async()=>{
  busy($("#res1"),"Dokument wird bereinigt …");
  const r=await api("/api/bereinigen",optionen(),datei1,await datei1.arrayBuffer());
  if(!r.ok){$("#res1").innerHTML='<div class="box er"><b>Das hat nicht geklappt</b>'+esc(r.fehler).replace(/\n/g,"<br>")+"</div>";return}
  let kopf;
  if(r.warnung)kopf='<div class="box er"><b>Nicht hochladen: In der Datei stehen noch Angaben</b>Details im Bericht unten. Namen ergänzen und neu bereinigen.</div>';
  else if(r.pruefen)kopf='<div class="box wa"><b>Bitte kurz prüfen, bevor Sie hochladen</b>Das Programm hält einzelne Wörter für Namen, hat sie aber nicht ersetzt. Details unten.</div>';
  else kopf='<div class="box ok"><b>Bereinigt</b>Keine bekannte Angabe mehr gefunden. Lesen Sie die Datei trotzdem einmal durch, bevor Sie sie hochladen.</div>';
  const knoepfe='<div class="zeile"><a href="'+dl(r.lauf,r.hochladen)+'"><button class="b pri">Bereinigte Datei laden</button></a><button class="b sek" id="oeffne">Ordner zeigen</button></div>';
  const hinweis='<p class="hilfe" style="margin-top:10px">Die Zuordnung (Namen und Platzhalter) bleibt im Ordner und wird <span class="warn">nie hochgeladen</span>.</p>';
  $("#res1").innerHTML=kopf+'<div class="karte">'+knoepfe+hinweis+'</div><div class="karte bericht">'+md(r.bericht)+"</div>";
  $("#oeffne").onclick=()=>api("/api/oeffnen",{lauf:r.lauf});
};

async function ladeLaeufe(){
  const r=await fetch("/api/laeufe?t="+TOKEN).then(x=>x.json());
  laeufe=r.laeufe;const s=$("#lauf");s.innerHTML="";
  if(!laeufe.length){s.innerHTML='<option value="">Noch kein bereinigtes Dokument</option>'}
  laeufe.forEach(l=>{const o=document.createElement("option");o.value=l.id;
    o.textContent=l.zeit+(l.label?"  ·  "+l.label:"");s.appendChild(o)});
  $("#laufhinweis").textContent=laeufe.length?"Nur das Dokument, das Sie hochgeladen haben, hat die passende Zuordnung.":"Bitte zuerst in Schritt 1 ein Dokument bereinigen.";
  pruefeZurueck();
}
function pruefeZurueck(){
  const hat=laeufe.length>0&&$("#lauf").value;
  $("#bZurueck").disabled=!(hat&&(datei3||$("#antwortText").value.trim()));
  $("#bLoesch").disabled=!hat;
}
$("#lauf").onchange=pruefeZurueck;
$("#antwortText").oninput=()=>{if($("#antwortText").value.trim()){datei3=null;$("#drop3").classList.remove("voll");$("#drop3").innerHTML="Antwort-Datei hierher ziehen oder klicken<small>oder unten den Text einfügen</small>"}pruefeZurueck()};
$("#bZurueck").onclick=async()=>{
  busy($("#res3"),"Namen werden eingesetzt …");
  const opt={lauf:$("#lauf").value};
  const text=$("#antwortText").value.trim();
  if(text)opt.text=$("#antwortText").value;
  const r=await api("/api/zurueck",opt,datei3,datei3&&!text?await datei3.arrayBuffer():"");
  if(!r.ok){$("#res3").innerHTML='<div class="box er"><b>Das hat nicht geklappt</b>'+esc(r.fehler).replace(/\n/g,"<br>")+"</div>";return}
  let h="";
  if(r.hinweise.length)h+='<div class="box wa"><b>Bitte prüfen</b>'+r.hinweise.map(esc).join("<br>")+"<br>Die KI hat Platzhalter verändert oder erfunden. Betroffene Stellen im Ergebnis von Hand nachsehen.</div>";
  else h+='<div class="box ok"><b>Namen eingesetzt</b>Alle Platzhalter wurden zugeordnet.</div>';
  h+='<div class="karte"><div class="zeile" style="margin-top:0"><a href="'+dl(r.lauf,r.datei)+'"><button class="b pri">Ergebnis laden</button></a>'+(r.text?'<button class="b sek" id="kopTxt">Text kopieren</button>':"")+'<button class="b sek" id="oeffne3">Ordner zeigen</button></div>';
  if(r.text)h+='<textarea readonly id="erg" style="margin-top:12px;min-height:220px">'+esc(r.text)+"</textarea>";
  $("#res3").innerHTML=h+"</div>";
  if(r.text)$("#kopTxt").onclick=()=>navigator.clipboard.writeText(r.text);
  $("#oeffne3").onclick=()=>api("/api/oeffnen",{lauf:r.lauf});
};
$("#bLoesch").onclick=async()=>{
  if(!confirm("Diesen Lauf endgültig löschen? Danach lassen sich Antworten zu diesem Dokument nicht mehr zurücksetzen."))return;
  await api("/api/loeschen",{lauf:$("#lauf").value});$("#res3").innerHTML="";ladeLaeufe();
};
$("#bAnw").onclick=()=>{navigator.clipboard.writeText($("#anw").textContent);$("#bAnw").textContent="Kopiert";setTimeout(()=>$("#bAnw").textContent="Kopieren",1500)};
$("#ordnerLink").onclick=()=>api("/api/oeffnen",{});
$("#ende").onclick=async()=>{await api("/api/ende",{});document.body.innerHTML='<main><div class="karte"><h2>Beendet</h2><p>Das Programm läuft nicht mehr. Sie können dieses Fenster schließen.</p></div></main>'};
fetch("/api/status?t="+TOKEN).then(r=>r.json()).then(s=>{if(!s.nlp)$("#nlpwarn").classList.remove("hidden");$("#ordnerLink").title=s.ordner});
</script></body></html>
"""

if __name__ == "__main__":
    main()
