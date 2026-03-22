# 🖼️ iCloudPhotonator

![Python](https://img.shields.io/badge/Python-3.13+-blue?logo=python&logoColor=white)
![macOS](https://img.shields.io/badge/macOS-13%2B-black?logo=apple&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green)
![osxphotos](https://img.shields.io/badge/osxphotos-0.75.6-orange)
![Status](https://img.shields.io/badge/Status-In%20Development-yellow)

**Intelligenter Foto-Migrationshelfer für macOS.**

iCloudPhotonator importiert große Foto- und Videoarchive von NAS-Systemen, externen Festplatten oder lokalen Ordnern zuverlässig nach **Apple Fotos**. Die App wurde speziell für lange, sensible Migrationen gebaut: mit Scan-Phase, Staging, Duplikat-Erkennung, Wiederaufnahme nach Unterbrechungen und einer GUI, die den gesamten Ablauf transparent macht.

## Was die App macht

- importiert Fotos und Videos aus bestehenden Ordnerstrukturen nach **Apple Fotos**
- eignet sich für **große Archive** auf lokalen Laufwerken und Netzlaufwerken
- schützt die Ziel-Mediathek durch **kontrollierte, adaptive Batch-Importe**
- ermöglicht **Pause, Fortsetzen und Abbrechen** während Scan **und** Import
- speichert den Fortschritt persistent, damit unterbrochene Läufe wieder aufgenommen werden können

## Funktionen

- 🗂️ **Auto-Album**: Standardmäßig wird automatisch ein Album mit dem Namen des Quellordners angelegt.
- 📚 **Mediathek-Auswahl**: Auswahl der Ziel-Mediathek direkt in der GUI oder per CLI über `--library` / `--mediathek`.
- ⏸️ **Pause / Fortsetzen / Abbrechen**: Steuerung funktioniert sowohl während des Scan-Vorgangs als auch im laufenden Import.
- 🖥️ **GUI und CLI**: Dieselbe Import-Engine kann grafisch oder über die Kommandozeile genutzt werden.
- 📸 **Live-Photo-Erkennung**: Foto-/Video-Paare mit gleichem Basisnamen werden als Live Photos erkannt.
- 🔄 **Fortsetzen nach Unterbrechung**: Unvollständige Jobs werden erkannt und können wieder aufgenommen werden.
- 🌐 **Netzlaufwerk-Support**: NAS- und andere Netzwerkquellen werden mit lokalem Staging stabil verarbeitet.
- 📊 **Transparente Fortschrittsanzeige**: Entdeckt, importiert, übersprungen, Duplikate, Fehler und verbleibende Dateien sind jederzeit sichtbar.

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
- halbiert sich bei Fehlern bis minimal **1 Datei pro Batch**
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
- `orchestrator.py` — durchgehender Workflow von Scan bis Abschluss

## Entwicklung

```bash
export PATH="$HOME/.local/bin:$PATH"
git clone https://github.com/hanselstner/icloudphototnator.git
cd icloudphototnator
uv sync
uv run python -m pytest tests/ -q --tb=short
```

## Lizenz

MIT — siehe [LICENSE](LICENSE).
