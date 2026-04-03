# 📖 iCloudPhotonator — Benutzerhandbuch

## Inhaltsverzeichnis

1. [Systemvoraussetzungen](#1-systemvoraussetzungen)
2. [Installation](#2-installation)
3. [Erster Start & Berechtigungen](#3-erster-start--berechtigungen)
4. [Import starten (GUI)](#4-import-starten-gui)
5. [Import starten (CLI)](#5-import-starten-cli)
6. [Während des Imports](#6-während-des-imports)
7. [Fehler und Probleme](#7-fehler-und-probleme)
8. [Import fortsetzen nach Unterbrechung](#8-import-fortsetzen-nach-unterbrechung)
9. [Nach dem Import](#9-nach-dem-import)
10. [FAQ](#10-faq)
11. [Technische Details für Fortgeschrittene](#11-technische-details-für-fortgeschrittene)

---

## 1. Systemvoraussetzungen

| Anforderung | Details |
|---|---|
| **Betriebssystem** | macOS 13 (Ventura) oder neuer |
| **Apple Fotos** | Muss auf dem System installiert und mindestens einmal geöffnet worden sein |
| **Python** | 3.13+ (nur wenn du die App selbst bauen oder die CLI verwenden möchtest) |
| **Speicherplatz** | Mindestens 10 GB freier Speicher auf dem Systemlaufwerk (für Staging) |
| **iCloud Fotos** | Optional — wenn die Ziel-Mediathek mit iCloud synchronisiert wird, sollte iCloud Fotos aktiviert sein |

### Unterstützte Quellen

- Lokale Ordner (z. B. `~/Pictures/Archiv`)
- Externe Festplatten (z. B. `/Volumes/USB-Platte/Fotos`)
- Netzlaufwerke via SMB, NFS oder AFP (z. B. `/Volumes/NAS/Fotos`)

### Unterstützte Medienformate

Alle Formate, die Apple Fotos akzeptiert, u. a.:
- **Fotos**: JPEG, HEIC, PNG, TIFF, RAW (CR2, NEF, ARW, etc.)
- **Videos**: MOV, MP4, M4V
- **Live Photos**: Werden automatisch erkannt wenn Foto und Video denselben Basisnamen haben

---

## 2. Installation

### Option A: Fertige .app verwenden

Falls du eine fertige `iCloudPhotonator.app` erhalten hast:

1. Kopiere die App in den Ordner **Programme** (`/Applications`)
2. Beim ersten Öffnen: Rechtsklick → **Öffnen** (wegen Gatekeeper-Warnung bei unsignierten Apps)
3. Bestätige mit **Öffnen**

### Option B: Selbst bauen

```bash
git clone https://github.com/hanselstner/icloudphototnator.git
cd icloudphototnator
export PATH="$HOME/.local/bin:$PATH"
uv sync
uv run pyinstaller iCloudPhotonator.spec
open dist/iCloudPhotonator.app
```

---

## 3. Erster Start & Berechtigungen

Beim ersten Start führt die App durch die notwendigen macOS-Berechtigungen. Ohne diese Berechtigungen kann die App **nicht importieren**.

### Automation-Berechtigung

Die App muss Apple Fotos per AppleScript steuern dürfen.

1. Die App zeigt einen Dialog: *„iCloudPhotonator möchte Fotos steuern"*
2. Klicke auf **OK**
3. Falls der Dialog nicht erscheint oder du ihn abgelehnt hast:
   - Öffne **Systemeinstellungen → Datenschutz & Sicherheit → Automation**
   - Aktiviere **Fotos** unter **iCloudPhotonator**

### Fotos-Zugriff

Apple Fotos muss geöffnet und bereit sein.

- Die App prüft automatisch, ob Photos.app läuft und ansprechbar ist (**Preflight-Check**)
- Falls Photos nicht läuft, wird es automatisch gestartet
- Falls Photos nicht reagiert, wird ein Neustart versucht

### Netzlaufwerk-Zugriff

Wenn du von einem NAS oder Netzlaufwerk importierst:

1. Stelle sicher, dass das Laufwerk **gemountet** ist (im Finder sichtbar unter `/Volumes/`)
2. Prüfe, dass du **Lesezugriff** auf die Foto-Ordner hast
3. Die App erkennt Netzwerkpfade automatisch und aktiviert das **lokale Staging**

---

## 4. Import starten (GUI)

### Schritt 1: Quellordner wählen

Klicke auf **„Ordner wählen"** und navigiere zum Ordner mit deinen Fotos und Videos. Die App durchsucht den gewählten Ordner und alle Unterordner rekursiv.

### Schritt 2: Album-Name

- Standardmäßig wird der **Name des Quellordners** als Album-Name verwendet
- Du kannst den Namen im Textfeld anpassen
- Alle importierten Fotos werden diesem Album in Apple Fotos zugeordnet

### Schritt 3: Mediathek auswählen

- Die App sucht automatisch nach Apple-Fotos-Mediatheken in `~/Pictures` und `/Users/Shared`
- Wähle die gewünschte Ziel-Mediathek aus dem Dropdown
- Die Standard-Mediathek ist vorausgewählt

### Schritt 4: Import starten

Klicke auf **„Import starten"**. Der Ablauf:

1. **Scan-Phase**: Alle Dateien werden inventarisiert (keine Dateien werden kopiert)
2. **Duplikat-Erkennung**: Bereits bekannte Dateien (per SHA-256-Hash) werden übersprungen
3. **Staging**: Netzwerkdateien werden lokal zwischengespeichert (max. 10 GB)
4. **Import**: Dateien werden batchweise nach Apple Fotos importiert
5. **Cleanup**: Staging-Dateien werden nach erfolgreichem Import gelöscht

---

## 5. Import starten (CLI)

### Einfacher Import

```bash
uv run icloudphotonator import-photos "/Volumes/NAS/Fotos"
```

### Mit Optionen

```bash
uv run icloudphotonator import-photos "/Volumes/NAS/Fotos" \
  --album "Familienarchiv" \
  --mediathek "$HOME/Pictures/Familie.photoslibrary"
```

### Alle Optionen

| Option | Beschreibung |
|--------|-------------|
| `--album` | Name des Ziel-Albums (Standard: Name des Quellordners) |
| `--library` / `--mediathek` | Pfad zur Ziel-Mediathek |
| `--staging-dir` | Lokaler Ordner für Netzwerk-Staging |
| `--db-path` | Pfad zur SQLite-Datenbank |
| `--help` | Alle verfügbaren Optionen anzeigen |

---

## 6. Während des Imports

### Fortschrittsanzeige verstehen

Die GUI zeigt folgende Kennzahlen:

| Anzeige | Bedeutung |
|---------|-----------|
| **Entdeckt** | Gesamtzahl der gefundenen Mediendateien |
| **Importiert** | Erfolgreich nach Apple Fotos importierte Dateien |
| **Duplikate** | Übersprungene Dateien, da sie bereits existieren |
| **Fehler** | Dateien, bei denen der Import fehlgeschlagen ist |
| **Staged** | Aktuell lokal zwischengespeicherte Dateien (bei Netzwerkquellen) |

### Pause / Fortsetzen / Abbrechen

- **Pause**: Klicke auf **„Pause"** — der aktuelle Batch wird noch abgeschlossen, dann stoppt der Import
- **Fortsetzen**: Klicke auf **„Fortsetzen"** — der Import macht exakt dort weiter, wo er pausiert wurde
- **Abbrechen**: Klicke auf **„Abbrechen"** — der Import wird beendet, der Fortschritt bleibt gespeichert

### Was die Status bedeuten

| Status | Bedeutung |
|--------|-----------|
| `pending` | Datei wurde erkannt, aber noch nicht verarbeitet |
| `importing` | Datei wird gerade importiert |
| `imported` | Datei wurde erfolgreich nach Apple Fotos importiert |
| `duplicate` | Datei wurde als Duplikat erkannt und übersprungen |
| `error` | Import dieser Datei ist fehlgeschlagen |
| `skipped` | Datei wurde bewusst übersprungen (z. B. zu groß für Staging) |

---

## 7. Fehler und Probleme

### „Photos.app reagiert nicht"

**Was passiert automatisch:**

Die App hat eine 4-stufige Eskalationslogik:

1. **Stufe 1**: 2 Minuten Pause, dann Retry
2. **Stufe 2**: 5 Minuten Pause, dann Retry
3. **Stufe 3**: Photos.app wird automatisch neugestartet (Graceful Shutdown mit bis zu 60s Wartezeit)
4. **Stufe 4**: Die App pausiert und zeigt einen Dialog — manueller Eingriff nötig

Zusätzlich wird Photos **alle 500 erfolgreichen Imports** präventiv neugestartet, um Speicherlecks vorzubeugen.

**Was du tun kannst:**
- Warte ab — die meisten Probleme löst die App automatisch
- Bei Stufe 4: Öffne Photos manuell, warte bis es vollständig geladen ist, dann klicke „Fortsetzen"

### Netzwerkverbindung verloren

**Was passiert automatisch:**
- Die App erkennt den Verbindungsverlust innerhalb von 10 Sekunden
- Der Import wird **automatisch pausiert**
- Sobald das Netzwerk wieder verfügbar ist, wird der Import **automatisch fortgesetzt**
- Keine Dateien gehen verloren

**Was du tun kannst:**
- Prüfe die Netzwerkverbindung (Finder → Netzlaufwerk noch sichtbar?)
- Die App setzt selbstständig fort, sobald der Pfad wieder erreichbar ist

### „Staging area is full"

**Was passiert automatisch:**
- Das Staging-Limit (10 GB) wurde erreicht
- Die App wartet, bis importierte Staging-Dateien aufgeräumt wurden
- Dann werden neue Dateien gestaged und der Import fortgesetzt

**Was du tun kannst:**
- Nichts — die App regelt das automatisch
- Bei Bedarf: Freien Speicherplatz auf dem Systemlaufwerk schaffen

### „Datei zu groß für Staging"

- Einzelne Dateien, die das Staging-Limit überschreiten, werden **übersprungen**
- Diese erscheinen als `skipped` in der Fortschrittsanzeige
- Importiere diese Dateien manuell über Apple Fotos (Drag & Drop)

### Berechtigungsfehler

Wenn die App die Automation-Berechtigung verloren hat:

1. Die App zeigt einen Dialog mit Hinweis
2. Klicke auf **„Systemeinstellungen öffnen"**
3. Navigiere zu **Datenschutz & Sicherheit → Automation**
4. Aktiviere **Fotos** unter **iCloudPhotonator**
5. Starte die App neu

---

## 8. Import fortsetzen nach Unterbrechung

### App-Neustart

1. Starte iCloudPhotonator
2. Die App erkennt automatisch den unvollständigen Job
3. Ein Dialog fragt: *„Unvollständiger Import gefunden. Fortsetzen?"*
4. Klicke **„Fortsetzen"** — der Import startet dort, wo er aufgehört hat
5. Bereits importierte Dateien werden **nicht** erneut importiert

### Rechner-Neustart

Genauso wie bei App-Neustart:
1. Starte den Mac
2. Öffne iCloudPhotonator
3. Der unvollständige Job wird erkannt und kann fortgesetzt werden

### Resume-Dialog

Der Resume-Dialog zeigt:
- Name des unterbrochenen Jobs
- Anzahl der bereits importierten Dateien
- Anzahl der verbleibenden Dateien
- Quellordner und Album-Name

---

## 9. Nach dem Import

### Import-Ergebnisse prüfen

Am Ende des Imports zeigt die App eine Zusammenfassung:
- ✅ Erfolgreich importierte Dateien
- ⏭️ Übersprungene Duplikate
- ❌ Fehlerhafte Dateien

### Fehlerhafte Dateien nochmal versuchen

Wenn einzelne Dateien fehlgeschlagen sind:

1. Klicke auf **„Fehler wiederholen"** in der GUI
2. Oder per CLI: `uv run icloudphotonator retry-errors`
3. Die App versucht nur die fehlgeschlagenen Dateien erneut zu importieren

**Tipp:** Manchmal scheitern Imports wegen vorübergehender Photos-Probleme. Ein Retry löst das oft.

---

## 10. FAQ

**Werden meine Original-Dateien verändert oder gelöscht?**
> Nein. iCloudPhotonator liest Dateien nur. Es werden keine Quelldateien verändert, verschoben oder gelöscht.

**Kann ich mehrere Ordner importieren?**
> Ja, aber nacheinander. Starte einen Import, warte bis er fertig ist, dann starte den nächsten mit einem anderen Quellordner.

**Was passiert bei einem Stromausfall während des Imports?**
> Der Fortschritt ist in der SQLite-Datenbank gespeichert. Nach dem Neustart des Macs kann der Import fortgesetzt werden.

**Funktioniert die App mit geteilten Mediatheken (Shared Libraries)?**
> Ja. Du kannst die Ziel-Mediathek in der GUI oder per CLI auswählen.

**Wie lange dauert der Import von 50.000 Fotos?**
> Das hängt von der Quelle ab. Von einer lokalen SSD: ca. 4–8 Stunden. Von einem NAS über Gigabit-Ethernet: ca. 8–16 Stunden. Die App ist darauf ausgelegt, diese langen Läufe stabil durchzuführen.

**Kann ich den Mac während des Imports benutzen?**
> Ja. Die App läuft im Hintergrund. Vermeide aber, Apple Fotos manuell zu benutzen, da dies den Import stören kann.

**Was bedeuten die Cooldowns zwischen den Batches?**
> Die App wartet absichtlich zwischen Batches (60 Sekunden, alle 100 Dateien sogar 180 Sekunden), um Apple Fotos und die iCloud-Synchronisierung nicht zu überlasten.

---

## 11. Technische Details für Fortgeschrittene

### Datenbank-Speicherort

Die SQLite-Datenbank wird standardmäßig unter folgendem Pfad gespeichert:

```
~/.icloudphotonator/
```

Die Datenbank enthält:
- Job-Definitionen (Quellordner, Album, Status)
- Dateistatus aller gescannten Dateien
- Hashes für Duplikat-Erkennung
- Fortschrittsinformationen für Resume

### Log-Dateien

Logs werden im selben Verzeichnis gespeichert:

```
~/.icloudphotonator/icloudphotonator.log
```

- Strukturiertes Logging mit Zeitstempeln
- Automatische Log-Rotation
- Hilfreich für die Fehlerdiagnose

### Staging-Verzeichnis

Für Netzwerkdateien wird ein lokales Staging-Verzeichnis verwendet:

```
/var/folders/.../icloudphotonator-staging/
```

- Maximale Größe: 10 GB
- Wird nach jedem erfolgreichen Batch aufgeräumt
- Bei App-Beendigung wird das Verzeichnis bereinigt (`try/finally`)
- Kann per `--staging-dir` angepasst werden

### SQLite WAL-Modus

Die Datenbank nutzt den WAL-Modus (Write-Ahead Logging) für maximale Zuverlässigkeit:
- Checkpoints alle 500 verarbeiteten Dateien
- Checkpoint beim App-Beenden
- Kein Datenverlust bei unerwartetem Abbruch
