#!/usr/bin/env python3
"""Baut ein portables Paket (eingebaute Python-Laufzeit + Bausteine + Programm) als ZIP.

Aufruf:  python paket/bauen.py --triple <Zielplattform> --name <Paketname> [--cross] [--runtime DIR]
  --triple   x86_64-pc-windows-msvc | aarch64-apple-darwin | x86_64-apple-darwin
  --cross    Bausteine für eine fremde Plattform installieren (Mac Intel auf Apple-Silicon-Rechner); kein Rauchtest
  --runtime  vorhandene Laufzeit nutzen statt herunterzuladen (nur für Tests des Bauskripts)
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import urllib.request
import zipfile
from datetime import date
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
PYVER = os.environ.get("PSEUDO_PYVER", "3.12")
LATEST = "https://raw.githubusercontent.com/astral-sh/python-build-standalone/latest-release/latest-release.json"


def anfrage(url):
    kopf = {"User-Agent": "pseudonymisierer-bauskript"}
    if os.environ.get("GITHUB_TOKEN") and "api.github.com" in url:
        kopf["Authorization"] = "Bearer " + os.environ["GITHUB_TOKEN"]
    return urllib.request.urlopen(urllib.request.Request(url, headers=kopf), timeout=120)


def laufzeit_url(triple):
    tag = json.load(anfrage(LATEST))["tag"]
    muster = re.compile(rf"^cpython-{re.escape(PYVER)}\.(\d+)\+{re.escape(tag)}-{re.escape(triple)}-install_only\.tar\.gz$")
    basis = "https://api.github.com/repos/astral-sh/python-build-standalone/releases"
    rel_id = json.load(anfrage(f"{basis}/tags/{tag}"))["id"]
    treffer = []
    for seite in range(1, 30):
        assets = json.load(anfrage(f"{basis}/{rel_id}/assets?per_page=100&page={seite}"))
        if not assets:
            break
        for a in assets:
            m = muster.match(a["name"])
            if m:
                treffer.append((int(m.group(1)), a["name"], a["browser_download_url"]))
    if not treffer:
        sys.exit(f"Keine Python-Laufzeit für {triple} im Release {tag} gefunden.")
    treffer.sort()
    return treffer[-1][1], treffer[-1][2]


def hole_laufzeit(triple, ziel):
    name, url = laufzeit_url(triple)
    print("Laufzeit:", name)
    archiv = ziel.parent / name
    with anfrage(url) as r, open(archiv, "wb") as f:
        shutil.copyfileobj(r, f)
    with tarfile.open(archiv) as t:
        try:
            t.extractall(ziel.parent, filter="data")
        except TypeError:
            t.extractall(ziel.parent)
    archiv.unlink()
    return name


def sitepackages(py_dir):
    for kandidat in (py_dir / "Lib" / "site-packages", py_dir / "lib" / f"python{PYVER}" / "site-packages"):
        if kandidat.is_dir():
            return kandidat
    sys.exit("site-packages nicht gefunden in " + str(py_dir))


def python_exe(py_dir):
    for k in (py_dir / "python.exe", py_dir / "bin" / "python3", py_dir / "bin" / "python"):
        if k.exists():
            return k
    sys.exit("Python-Programm nicht gefunden in " + str(py_dir))


def installiere(py_dir, cross):
    req = str(WURZEL / "requirements.txt")
    if cross:
        site = sitepackages(py_dir)
        cmd = [sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "--no-compile",
               "--target", str(site), "--platform", "macosx_14_0_x86_64", "--python-version", PYVER,
               "--implementation", "cp", "--abi", f"cp{PYVER.replace('.', '')}", "--only-binary=:all:", "-r", req]
    else:
        cmd = [str(python_exe(py_dir)), "-m", "pip", "install", "--disable-pip-version-check",
               "--no-warn-script-location", "-r", req]
    print(" ".join(cmd))
    subprocess.run(cmd, check=True)


def aufraeumen(py_dir):
    for p in list(py_dir.rglob("__pycache__")):
        shutil.rmtree(p, ignore_errors=True)
    for rel in (("Lib", "test"), ("lib", f"python{PYVER}", "test"), ("Lib", "idlelib"),
                ("lib", f"python{PYVER}", "idlelib")):
        shutil.rmtree(py_dir.joinpath(*rel), ignore_errors=True)


def packe(ordner, ziel_zip):
    if shutil.which("ditto"):  # macOS: erhält Rechte und Verknüpfungen
        subprocess.run(["ditto", "-c", "-k", "--keepParent", str(ordner), str(ziel_zip)], check=True)
        return
    with zipfile.ZipFile(ziel_zip, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for p in sorted(ordner.rglob("*")):
            if p.is_file():
                z.write(p, p.relative_to(ordner.parent))


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--triple", required=True)
    a.add_argument("--name", required=True)
    a.add_argument("--cross", action="store_true")
    a.add_argument("--runtime")
    a = a.parse_args()
    windows = "windows" in a.triple

    bau = WURZEL / "build" / "Pseudonymisierer"
    shutil.rmtree(WURZEL / "build", ignore_errors=True)
    bau.mkdir(parents=True)
    py_dir = bau / "python"
    if a.runtime:
        shutil.copytree(a.runtime, py_dir, symlinks=True)
        name = "lokale Laufzeit"
    else:
        name = hole_laufzeit(a.triple, py_dir)
    installiere(py_dir, a.cross)
    aufraeumen(py_dir)

    shutil.copytree(WURZEL / "app", bau / "app")
    if windows:
        shutil.copy2(WURZEL / "paket" / "start-windows.bat", bau / "Pseudonymisierer-Start.bat")
    else:
        ziel = bau / "Pseudonymisierer-Start.command"
        shutil.copy2(WURZEL / "paket" / "start-mac.command", ziel)
        ziel.chmod(0o755)
    stand = date.today().isoformat()
    sha = os.environ.get("GITHUB_SHA", "lokal")[:7]
    (bau / "VERSION.txt").write_text(f"Pseudonymisierer, Stand {stand}, Build {sha}\nLaufzeit: {name}\n"
                                     f"Ziel: {a.triple}\n", encoding="utf-8")

    if not a.cross and not a.runtime:
        print("Rauchtest …")
        subprocess.run([str(python_exe(py_dir)), str(WURZEL / "paket" / "smoke.py"), str(bau)], check=True)

    dist = WURZEL / "dist"
    dist.mkdir(exist_ok=True)
    zip_pfad = dist / f"{a.name}.zip"
    zip_pfad.unlink(missing_ok=True)
    packe(bau, zip_pfad)
    print("Fertig:", zip_pfad, round(zip_pfad.stat().st_size / 1e6), "MB")


if __name__ == "__main__":
    main()
