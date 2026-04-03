# 🖼️ iCloudPhotonator

![Python](https://img.shields.io/badge/Python-3.13+-blue?logo=python&logoColor=white)
![macOS](https://img.shields.io/badge/macOS-13%2B-black?logo=apple&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green)
![osxphotos](https://img.shields.io/badge/osxphotos-powered-orange)
![Status](https://img.shields.io/badge/Status-Beta-brightgreen)
![Tests](https://img.shields.io/badge/Tests-215%2B%20passing-brightgreen)
![Build](https://img.shields.io/badge/Build-PyInstaller-blue)
![Version](https://img.shields.io/badge/Version-v0.3.0--beta-blueviolet)

**Intelligenter Foto-Migrationshelfer für macOS.**

---

## Was ist iCloudPhotonator?

iCloudPhotonator ist eine macOS-Desktop-App, die große Foto- und Videoarchive von NAS-Systemen, externen Festplatten oder lokalen Ordnern **zuverlässig und kontrolliert** nach **Apple Fotos** importiert.

Die App wurde speziell für Nutzer entwickelt, die **10.000 bis 100.000+ Mediendateien** aus bestehenden Ordnerstrukturen — etwa von einer Synology, QNAP oder einer externen USB-Festplatte — in ihre Apple-Fotos-Mediathek migrieren möchten. Der Import läuft dabei nicht als einfacher Drag-and-Drop, sondern als **mehrstufige, fehlertolerante Pipeline**:

**Scan → Staging → Duplikat-Erkennung → Import → Cleanup**

Jeder Schritt ist persistent in einer SQLite-Datenbank gespeichert. Wenn die App abstürzt, der Mac neugestartet wird oder das Netzwerk ausfällt, kann der Import exakt dort fortgesetzt werden, wo er unterbrochen wurde — ohne Dateien doppelt zu importieren oder zu verlieren.

### Für wen ist die App?

- Du hast **tausende Fotos und Videos** auf einem NAS oder einer externen Platte
- Du möchtest diese **nach Apple Fotos** bringen (lokal oder mit iCloud-Synchronisation)
- Du brauchst ein Werkzeug, das bei großen Mengen **nicht einfriert, abstürzt oder Dateien vergisst**
- Du willst den Import **pausieren, fortsetzen und überwachen** können

### Was iCloudPhotonator NICHT ist

- **Kein Sync-Tool**: Die App synchronisiert keine Ordner dauerhaft. Sie importiert einmalig.
- **Kein Backup-Tool**: Sie erstellt keine Sicherungen. Quelldateien werden nicht verändert oder gelöscht.
- **Kein Cloud-Upload-Tool**: Der Import geht in die lokale Apple-Fotos-Mediathek. iCloud-Sync ist Sache von macOS.

### Besonderheiten

- **Adaptive Batches**: Die Batch-Größe passt sich automatisch an — bei Erfolg wächst sie, bei Fehlern schrumpft sie
- **Netzwerk-Resilienz**: Bei Verbindungsverlust pausiert der Import automatisch und setzt fort, sobald das Netzwerk wieder da ist
- **Automatischer Photos-Restart**: Wenn Apple Fotos nicht mehr reagiert, wird es automatisch neugestartet — mit Eskalationslogik
- **4-stufige Eskalation**: 2 Min Pause → 5 Min Pause → Photos Restart → Manueller Eingriff

## Funktionen

- 🗂️ **Auto-Album**: Standardmäßig wird automatisch ein Album mit dem Namen des Quellordners angelegt.
- 📚 **Mediathek-Auswahl**: Auswahl der Ziel-Mediathek direkt in der GUI oder per CLI über `--library` / `--mediathek`.
- ⏸️ **Pause / Fortsetzen / Abbrechen**: Steuerung funktioniert sowohl während des Scan-Vorgangs als auch im laufenden Import.
- 🖥️ **GUI und CLI**: Dieselbe Import-Engine kann grafisch oder über die Kommandozeile genutzt werden.
- 📸 **Live-Photo-Erkennung**: Foto-/Video-Paare mit gleichem Basisnamen werden als Live Photos erkannt.
- 🔄 **Fortsetzen nach Unterbrechung**: Unvollständige Jobs werden erkannt und können wieder aufgenommen werden.
- 🌐 **Netzlaufwerk-Support**: NAS- und andere Netzwerkquellen werden mit lokalem Staging stabil verarbeitet.
- 📊 **Transparente Fortschrittsanzeige**: Entdeckt, importiert, übersprungen, Duplikate, Fehler und verbleibende Dateien sind jederzeit sichtbar.
- 🚀 **Pipeline-Modus**: Scan und Import laufen parallel — der Import startet bereits nach den ersten 50 gescannten Dateien.
- 📊 **Batch-Zusammenfassung**: Nach jedem Batch und am Ende des Jobs werden importierte, übersprungene und fehlerhafte Dateien klar aufgeschlüsselt.
- 🔐 **Berechtigungs-Onboarding**: Beim ersten Start führt die App durch die nötigen macOS-Berechtigungen (Automation, Fotomediathek).
- ⚠️ **Intelligente Fehlererkennung**: Fatale Fehler wie fehlende Automation-Berechtigung werden sofort erkannt und der Import sauber gestoppt.
- 💾 **Datensicherheit**: WAL-Checkpoints alle 500 Dateien und beim Beenden — kein Datenverlust bei App-Abbruch.
- 🔍 **Photos Preflight**: Automatische Vorab-Prüfung der Apple-Fotos-Umgebung vor dem Import — erkennt fehlende Berechtigungen, gesperrte Mediatheken und iCloud-Probleme frühzeitig.
- 🔄 **Graceful Photos-Restart**: Bei Silent Failures wird Photos sauber beendet und neugestartet — mit bis zu 60s Wartezeit.
- 🛡️ **Eskalationslogik**: 4-stufige automatische Fehlerbehebung bei Photos-Problemen.

## ⚡ Intelligentes Datenmanagement

> **Das ist das Herzstück von iCloudPhotonator:** Die App versucht nicht, ein großes Archiv „blind“ auf einmal in Apple Fotos zu schieben. Stattdessen arbeitet sie kontrolliert, datenbankgestützt und fehlertolerant.

### Scan-Phase — nur Inventarisierung, kein Kopieren

In der Scan-Phase wird **noch nichts importiert und nichts lokal gestaged**. Die App inventarisiert zunächst nur den Bestand und schreibt die Ergebnisse in SQLite.

- erfasst u. a. **Dateinamen/Pfade, Größen, Medientypen, Zeitstempel und Hashes**
- kopiert in dieser Phase **keine Dateien** in die Fotos-Mediathek
- kann so auch Archive mit **50.000 Dateien in wenigen Minuten** erfassen
- legt den kompletten Scan-Status in **SQLite** ab, damit danach dedupliziert, importiert und fortgesetzt werden kann

### Staging mit 10-GB-Limit

Netzwerkdateien werden vor dem Import kontrolliert in einen lokalen temporären Bereich kopiert.

- nutzt lokales Staging für Netzwerkpfade wie **SMB, NFS oder AFP**
- hartes Limit von **10 GB** verhindert, dass das Systemlaufwerk vollläuft
- wenn das Limit überschritten würde, wird der nächste Schritt **nicht blind fortgesetzt**
- erfolgreich importierte Staging-Dateien werden nach jedem Batch wieder **aufgeräumt**
- Ergebnis: Es liegen **nie mehr als 10 GB gleichzeitig** im lokalen Staging-Bereich

### Adaptives Batching

Die App importiert nicht statisch, sondern passt die Last dynamisch an das Verhalten von Apple Fotos und der Umgebung an.

- Start mit **5 Dateien pro Batch**
- wächst bei Erfolg schrittweise bis maximal **50 Dateien pro Batch**
- halbiert sich bei Fehlern bis minimal **10 Dateien pro Batch**
- wartet standardmäßig **30 Sekunden** zwischen zwei Batches
- führt nach jeweils **100 verarbeiteten Dateien** einen erweiterten Cooldown von **2 Minuten** aus

So bleibt der Import auch bei großen Datenmengen stabil und überfordert weder Fotos noch iCloud-Synchronisierung.

### Duplikat-Erkennung

Vor dem Import prüft iCloudPhotonator Dateien hash-basiert auf Duplikate.

- nutzt **SHA-256-Hashes** zur Erkennung identischer Dateien
- überspringt Duplikate innerhalb des laufenden Jobs und innerhalb desselben Batches
- reduziert unnötige Importe, Wartezeiten und Fehlerketten
- der eigentliche Import läuft zusätzlich mit `skip_dups=True`

### Fortsetzen nach Absturz oder App-Neustart

Große Migrationsläufe dürfen nicht bei jedem Problem von vorne beginnen.

- persistiert Job- und Dateistatus in **SQLite**
- speichert aktive Jobs separat, damit unvollständige Läufe wiedergefunden werden
- setzt nur **nicht abgeschlossene Dateien** erneut an
- bereits importierte oder übersprungene Dateien bleiben erhalten
- die GUI erkennt unvollständige Jobs und bietet das **Fortsetzen** aktiv an

### Netzwerk-Resilienz

Gerade bei NAS-Systemen oder externen Quellen ist Ausfallsicherheit entscheidend.

- Dateikopien werden mit **automatischen Wiederholungen** ausgeführt
- exponentielles Backoff reduziert Folgeschäden bei kurzzeitigen Problemen
- Netzwerkpfade werden im Hintergrund überwacht
- die Verfügbarkeit wird standardmäßig alle **10 Sekunden** geprüft
- bei Verbindungsverlust wird der Import automatisch pausiert, bei Wiederherstellung wieder fortgesetzt

## Installation & Nutzung

### Voraussetzungen

- macOS **13+**
- **Apple Fotos** auf dem System
- für iCloud-Zielszenarien: **iCloud Fotos** aktiviert
- `exiftool` wird für eine robuste Metadatenverarbeitung empfohlen
- Python **3.13+**, wenn du die App lokal bauen oder die CLI verwenden möchtest

### `.app` bauen

```bash
export PATH="$HOME/.local/bin:$PATH"
uv sync
uv run pyinstaller iCloudPhotonator.spec
open dist/iCloudPhotonator.app
```

Nach dem Build liegt die gebündelte macOS-App unter `dist/iCloudPhotonator.app`.

### CLI verwenden

Die CLI nutzt dieselbe Orchestrierungslogik wie die GUI.

```bash
export PATH="$HOME/.local/bin:$PATH"
uv run icloudphotonator --help
```

```bash
export PATH="$HOME/.local/bin:$PATH"
uv run icloudphotonator import-photos "/Volumes/NAS/Fotos"
```

```bash
export PATH="$HOME/.local/bin:$PATH"
uv run icloudphotonator import-photos "/Volumes/NAS/Fotos" \
  --album "Familienarchiv" \
  --mediathek "$HOME/Pictures/Familie.photoslibrary"
```

Nützliche Optionen:

- `--album`: Name des Ziel-Albums; ohne Angabe wird der Name des Quellordners verwendet
- `--library` / `--mediathek`: explizite Ziel-Mediathek
- `--staging-dir`: lokaler Ordner für das Netzwerk-Staging
- `--db-path`: Pfad zur SQLite-Datenbank für persistente Jobs

### GUI verwenden

Du kannst die GUI entweder über die gebaute `.app` oder direkt aus dem Projekt starten:

```bash
export PATH="$HOME/.local/bin:$PATH"
uv run icloudphotonator
```

Ablauf in der GUI:

1. **Quellordner wählen** (lokal, externe Platte oder gemountetes Netzlaufwerk)
2. **Album automatisch übernehmen** oder manuell anpassen
3. **Ziel-Mediathek auswählen**
4. **Import starten**
5. bei Bedarf **pausieren, fortsetzen oder abbrechen**

Die GUI erkennt Apple-Fotos-Mediatheken in typischen Verzeichnissen wie `~/Pictures` und `/Users/Shared` und zeigt sie direkt in der Auswahl an.

## Technische Details

| Bereich | Technologie | Zweck |
|---|---|---|
| Backend | Python 3.13 | Orchestrierung von Scan, Staging, Dedup, Persistenz und Import |
| GUI | `customtkinter` | native Desktop-Oberfläche für macOS |
| Import-Engine | `osxphotos` | Import nach Apple Fotos inkl. Album-/Mediathek-Steuerung |
| Persistenz | SQLite | dauerhafte Speicherung von Jobs, Dateistatus und Wiederaufnahme |
| CLI | `click` | Kommandozeilen-Interface |
| Packaging | PyInstaller | Bundling als macOS-`.app` |

Wichtige Implementierungsbausteine:

- `scanner.py` — Dateierkennung, Klassifizierung, Hashing und Live-Photo-Paare
- `staging.py` — lokales Staging mit 10-GB-Schutz für Netzwerkquellen
- `throttle.py` — adaptives Batch- und Cooldown-Management
- `dedup.py` — hash-basierte Duplikat-Erkennung
- `resilience.py` — Retry-Logik und Netzwerküberwachung
- `photos_preflight.py` — Vorab-Prüfung der Apple-Fotos-Umgebung (Berechtigungen, Mediathek, iCloud)
- `orchestrator.py` — durchgehender Workflow von Scan bis Abschluss

## Open-Source-Software

| Paket | Version | Verwendungszweck | Lizenz |
|-------|---------|-----------------|--------|
| [osxphotos](https://github.com/RhetTbull/osxphotos) | ≥5.x | Import-Engine: Kommunikation mit Apple Fotos via AppleScript, Album-Management | MIT |
| [customtkinter](https://github.com/TomSchimansky/CustomTkinter) | ≥5.2.2 | Desktop-GUI: Moderne Tkinter-Oberfläche mit Dark-Mode-Support | MIT |
| [click](https://github.com/pallets/click) | ≥8.x | CLI-Framework: Kommandozeilen-Interface mit Optionen und Hilfe | BSD-3-Clause |
| [pydantic](https://github.com/pydantic/pydantic) | ≥2.x | Datenvalidierung: Konfiguration und Settings-Management | MIT |
| [websockets](https://github.com/python-websockets/websockets) | ≥12.x | WebSocket-Kommunikation zwischen UI und Backend | BSD-3-Clause |
| [aiohttp](https://github.com/aio-libs/aiohttp) | ≥3.x | Async HTTP Client/Server | Apache-2.0 |
| [PyInstaller](https://github.com/pyinstaller/pyinstaller) | ≥6.19 | Packaging: Bundling als native macOS-`.app` | GPL-2.0 (mit Bootloader-Ausnahme) |
| [pytest](https://github.com/pytest-dev/pytest) | ≥8.x | Testing: Test-Framework | MIT |
| [pytest-asyncio](https://github.com/pytest-dev/pytest-asyncio) | ≥0.x | Testing: Async-Test-Support | Apache-2.0 |
| [PyObjC](https://github.com/ronaldoussoren/pyobjc) | 12.1 | macOS-Integration: Native AppleScript-Ausführung, Berechtigungsprüfung | MIT |
| [SQLite](https://sqlite.org/) | (stdlib) | Eingebettete Datenbank für Jobs, Dateistatus, Fortschritt | Public Domain |
| [hatchling](https://github.com/pypa/hatch) | ≥1.27 | Build-System | MIT |

## Entwicklung

```bash
export PATH="$HOME/.local/bin:$PATH"
git clone https://github.com/hanselstner/icloudphototnator.git
cd icloudphototnator
uv sync
uv run python -m pytest tests/ -q --tb=short
```

## Changelog

### v0.3.0-beta — 3. April 2026

#### Stabilität & Fehlerbehebung
- **Konservatives Throttling**: Maximale Batch-Größe auf 20 reduziert, Cooldowns erhöht (60s zwischen Batches, 180s Extended Cooldown) für stabileren Import bei großen Archiven
- **Graceful Photos-Restart**: Photos.app wird bei Problemen sauber beendet statt hart gekillt, mit bis zu 60s Wartezeit für ordnungsgemäßes Herunterfahren
- **Präventiver Photos-Neustart**: Alle 500 erfolgreichen Imports wird Photos automatisch neugestartet, um Speicherlecks und Instabilität vorzubeugen
- **4-stufige Eskalationslogik**: Automatische Fehlerbehebung bei Photos-Problemen: 2 Min Pause → 5 Min Pause → Photos Restart → Manueller Eingriff
- **Staging-Cleanup garantiert**: `try/finally` stellt sicher, dass staged Files auch bei Fehlern immer aufgeräumt werden
- **Übergroße Dateien**: Dateien, die das Staging-Limit überschreiten, werden übersprungen statt den gesamten Import zu blockieren

### v0.2.1-beta — 31. März 2026

#### Verbesserungen
- **Auto-Restart Photos.app**: Bei konsekutiven Import-Fehlern wird Photos automatisch neugestartet

### v0.2.0-beta — 29.–30. März 2026

#### Neue Funktionen
- **Netzwerk-Erkennung**: Netzwerk-Nichtverfügbarkeit wird erkannt und von Silent Failures unterschieden
- **Konsekutive Batch-Failure-Erkennung**: Automatische Retry-Logik bei aufeinanderfolgenden Fehlschlägen
- **Duplikat-Handling**: Duplikate und fehlende Staging-Files werden als Skip statt Error behandelt
- **Kumulative Staging-Zählung**: Transparente Anzeige der insgesamt gestagten Dateien
- **Quellordner-Validierung**: Prüfung ob der Quellordner existiert und lesbar ist
- **Photos Preflight**: Automatische Vorab-Prüfung der Fotos-Umgebung (Berechtigungen, Mediathek, iCloud)
- **Automation-Berechtigung mit Recovery-Loop**: Wiederholte Prüfung statt stilles Scheitern
- **Retry-Errors**: Fehlgeschlagene Imports können gezielt wiederholt werden
- **Medienvalidierung**: Magic-Bytes-Prüfung vor dem Import

#### Verbesserungen
- **Batch-Minimum auf 10 angehoben**: Das adaptive Batching reduziert die Batch-Größe bei Fehlern jetzt bis minimal 10 Dateien (vorher 1)

### v0.1.1-beta — 27.–28. März 2026

#### Verbesserungen
- **Photos Auto-Recovery**: Automatische Wiederherstellung mit Window-Detection
- **Preflight-Checks**: Prüfung der Photos-Bereitschaft vor dem Import
- **Import-Timeout-Kontrolle**: Timeout-basierte Recovery bei hängenden Imports
- **Job-Count-Synchronisation**: Korrekte Zähler bei Resume nach Unterbrechung
- **Fehlerdiagnostik**: Verbesserte Exception-Chains für bessere Fehlerverfolgung

### v0.1.0-beta — 21.–25. März 2026

#### Erster vollständiger Release
- **Scan → Staging → Dedup → Import Pipeline**: Kompletter mehrstufiger Workflow
- **GUI mit customtkinter**: Desktop-Oberfläche mit Dark-Mode-Support
- **CLI mit click**: Kommandozeilen-Interface mit allen Optionen
- **Adaptives Batching**: ThrottleController passt Batch-Größe dynamisch an (5–50 Dateien)
- **SQLite-Persistenz**: WAL-Modus für zuverlässige Datenspeicherung
- **Live-Photo-Erkennung**: Foto-/Video-Paare werden automatisch erkannt
- **Netzwerk-Resilienz**: Retry mit exponentiellem Backoff, automatische Pause bei Verbindungsverlust
- **Pause/Resume/Cancel**: Volle Steuerung während Scan und Import
- **Auto-Album**: Album wird automatisch nach Quellordner benannt
- **Mediathek-Auswahl**: Ziel-Mediathek direkt in GUI oder CLI wählbar
- **Berechtigungs-Onboarding**: Geführter Dialog beim ersten Start
- **PyInstaller-Bundling**: Native macOS-`.app`
- **215+ Tests**: Umfassende Test-Suite

## Lizenz

MIT — siehe [LICENSE](LICENSE).
