# Pseudonymisierer – Installation und erster Start

## Was Sie bekommen
Ein Ordner „Pseudonymisierer“. Darin steckt alles, was das Programm braucht. Sie installieren nichts und brauchen keine Administratorrechte. Der Ordner ist etwa 450 MB groß.

## Schritt 1: Entpacken
Laden Sie die ZIP-Datei für Ihren Rechner herunter und entpacken Sie sie an einen Ort, an dem Sie schreiben dürfen, zum Beispiel in „Dokumente“.

**Windows:** Rechtsklick auf die ZIP-Datei, dann „Eigenschaften“. Unten steht, falls vorhanden, „Zulassen“. Haken setzen, „OK“. Danach erst entpacken („Alle extrahieren“). Ohne diesen Schritt meldet Windows bei jeder einzelnen Datei eine Warnung.

**Mac:** Doppelklick auf die ZIP-Datei. Es entsteht ein Ordner.

## Schritt 2: Starten
**Windows:** Im Ordner auf „Pseudonymisierer-Start.bat“ doppelklicken. Erscheint „Der Computer wurde geschützt“, klicken Sie auf „Weitere Informationen“, dann auf „Trotzdem ausführen“. Das Fenster mit dem schwarzen Hintergrund bleibt offen, solange das Programm läuft.

**Mac:** Im Ordner auf „Pseudonymisierer-Start.command“ mit der rechten Maustaste klicken, „Öffnen“ wählen, in der Rückfrage noch einmal „Öffnen“. Das ist nur beim ersten Mal nötig. Zeigt der Mac nur „Abbrechen“ und „In den Papierkorb“, öffnen Sie Systemeinstellungen → Datenschutz & Sicherheit, scrollen nach unten und klicken bei der Meldung zu „Pseudonymisierer-Start“ auf „Dennoch öffnen“.

Nach wenigen Sekunden öffnet sich Ihr Browser mit der Seite des Pseudonymisierers. Alles läuft auf Ihrem Rechner. Es werden keine Daten ins Internet gesendet.

## Schritt 3: Benutzen
1. Datei auswählen (Word, Excel, PDF, Text).
2. Namen eintragen, die im Dokument vorkommen. Das Programm findet vieles selbst, aber nicht alles. Ihre Liste ist der wichtigste Teil.
3. „Prüfen“ zeigt, was ersetzt würde. Nichts wird gespeichert.
4. „Bereinigen“ erzeugt die Datei mit Platzhaltern wie [PERSON_01]. Diese Datei laden Sie in Ihre KI hoch.
5. Die Antwort der KI laden Sie wieder in den Pseudonymisierer. „Zurücksetzen“ setzt die echten Namen wieder ein.

Die Zuordnung zwischen Platzhaltern und Namen bleibt auf Ihrem Rechner im Ordner „Pseudonymisierer-Ergebnisse“ (in Ihrem Benutzerordner). Geben Sie diese Datei nie weiter. Über die Seite können Sie einen Lauf samt Zuordnung löschen.

## Beenden
Auf der Seite „Beenden“ klicken oder das schwarze Fenster schließen.

## Wichtig zur Einordnung
Das Werkzeug ist ein Hilfsmittel und keine Garantie. Es findet nicht jeden Namen. Lesen Sie das bereinigte Dokument vor dem Hochladen immer durch. Pseudonymisierte Daten bleiben personenbezogene Daten im Sinne der DSGVO. Ob und wie Sie ein Dokument an eine KI geben dürfen, entscheiden Sie als Verantwortliche. Das ist keine Rechtsberatung.

Nicht erfasst werden derzeit Textfelder, Fußnoten und Kommentare in Word sowie Blattnamen, Kommentare und Kopfzeilen in Excel. Prüfen Sie diese Stellen von Hand.

## Wenn etwas nicht klappt
- Es passiert nichts: Warten Sie 20 Sekunden. Beim ersten Start entpackt sich das Sprachmodell.
- Der Browser öffnet sich nicht: Im schwarzen Fenster steht eine Adresse, die mit http://127.0.0.1 beginnt. Kopieren Sie sie in den Browser.
- Ihre IT sperrt das Programm: Fragen Sie dort nach einer Freigabe für den Ordner „Pseudonymisierer“.
