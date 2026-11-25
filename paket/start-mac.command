#!/bin/bash
# Pseudonymisierer starten (Mac). Alles Nötige liegt in diesem Ordner, es wird nichts installiert.
cd "$(dirname "$0")" || exit 1
# Vom Browser geladene Dateien tragen eine Sperrmarkierung; sie wird hier entfernt, damit die Bausteine laufen.
xattr -dr com.apple.quarantine . 2>/dev/null || true
exec ./python/bin/python3 app/oberflaeche.py
