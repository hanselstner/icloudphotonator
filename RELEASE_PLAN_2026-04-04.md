# iCloudPhotonator — Release-Umsetzungsplan
**Datum:** 4. April 2026
**Ziel:** Die App für den Open-Source-Release vorbereiten — modernes UI, i18n, Settings, GitHub Release.
**Version:** v1.0.0

---

## Übersicht

| Wave | Aufgabe | Abhängigkeiten |
|------|---------|----------------|
| **Wave 1** | UI-Redesign (komplett neu, modern, flat, Best-Practice UX) | — |
| **Wave 2** | i18n (EN default + DE) + Settings-Dialog | Wave 1 |
| **Wave 3** | Onboarding, Berechtigungen, Final Polish | Wave 2 |
| **Wave 4** | Release-Build, GitHub Release, Docs-Update | Wave 3 |

---

## Wave 1 — UI-Redesign

### Ziel
Komplettes visuelles Redesign der App. Modern, clean, flat. Muss auf macOS 13+ (Ventura, Sonoma, Sequoia) gut aussehen. Dark Mode + Light Mode.

### Design-Prinzipien
- **Flat Design** — keine Schatten, keine Gradienten, klare Kanten
- **Reduzierte Farbpalette** — Ein Akzentblau (#007AFF), Grau-Abstufungen, Grün/Rot/Gelb nur für Status
- **Einheitliche Icons** — SF Symbols-Stil (Unicode-basiert da customtkinter keine SF Symbols kann), konsistenter Stil
- **Whitespace** — Großzügig, nicht überladen
- **Typography** — System-Font (San Francisco via -apple-system), klare Hierarchie
- **Responsive** — Fenster skaliert sauber von 600x700 bis Vollbild

### Konkretes Layout (Top → Bottom)

1. **Header** (schmal)
   - App-Icon (minimal, flat) + "iCloudPhotonator" + Subtitle
   - Settings-Zahnrad oben rechts (öffnet Settings-Dialog)

2. **Source/Config Section** (Karte mit abgerundeten Ecken)
   - Source Folder: Entry + Browse-Button
   - Album: Entry + Auto-Button
   - Library: Dropdown
   - Alles in einer aufgeräumten Card

3. **Progress Section** (prominent)
   - Große Prozentanzeige (z.B. "34%") zentriert
   - Darunter: dünner, eleganter Progress-Bar
   - Status-Text darunter (z.B. "Importing... 14,003 of 80,182")

4. **Stats Grid** (2x3 Karten)
   - Discovered | Imported | Staged
   - Duplicates | Errors | Remaining
   - Jede Karte: große Zahl, kleines Label darunter
   - Dezent, nicht zu bunt — Fehler-Karte nur bei errors > 0 rot

5. **Controls** (eine Reihe, gleichmäßig)
   - ▶ Start | ⏸ Pause | ⏹ Stop | 🔄 Retry
   - Alle gleich breit, flat, mit hover-Effekt
   - "Photos neu starten" nur wenn nötig, als Banner oberhalb

6. **Log Area** (unten, expandierbar)
   - Dunkler Hintergrund, Monospace
   - Auto-scroll
   - Minimale Höhe, wächst mit Fenster

7. **Footer** (minimal)
   - Version links, "GitHub" Link rechts

### Farben
- Background: System (Light: #f5f5f7 / Dark: #1c1c1e)
- Cards: Light: #ffffff / Dark: #2c2c2e
- Accent: #007AFF
- Success: #34C759
- Warning: #FF9500
- Error: #FF3B30
- Text Primary: System
- Text Secondary: #8E8E93

### Was NICHT ändern
- Backend-Logik (orchestrator, bridge, throttle, etc.)
- Funktionale Abläufe
- Nur die visuelle Darstellung in app.py

---

## Wave 2 — i18n + Settings Dialog

### i18n
- Neues Modul: `icloudphotonator/i18n.py`
- JSON-basierte Sprachdateien: `icloudphotonator/locales/en.json`, `icloudphotonator/locales/de.json`
- Alle UI-Strings + Log-Meldungen über i18n-Funktion `t("key")`
- Default: Englisch
- Sprachauswahl im Settings-Dialog
- Sprache persistent in settings.json

### Settings Dialog
- Modal-Dialog (eigenes Fenster oder Overlay)
- Sections:
  1. **General** — Language selection
  2. **Import Performance** — Batch size (min/max), Cooldown (normal/extended), Extended cooldown interval, Photos restart interval
  3. **Advanced** — Escalation pause durations, Max staging size
- Einleitungstext: "These are recommended defaults that work well for most systems. If Photos.app becomes unstable, reduce batch sizes and increase cooldowns. If your system handles imports well, you can carefully increase speeds."
- Reset-to-Defaults Button
- Settings persistent in `~/.icloudphotonator/settings.json`
- ThrottleController + Orchestrator lesen Settings beim Start

---

## Wave 3 — Onboarding + Polish

### Berechtigungs-Onboarding (überarbeitet)
- Erster Start: Schritt-für-Schritt Dialog (nicht alles auf einmal)
- Step 1: "iCloudPhotonator needs Automation access to control Photos.app"
  - Prüft ob Berechtigung da → weiter
  - Nicht da → "Open System Settings" Button
- Step 2: "Please ensure Photos.app is installed and accessible"
  - Quick-Check
- Visuell ansprechend, mit Icons

### Final Polish
- Alle Texte auf Englisch (mit deutscher Übersetzung)
- Error-Handling: Alle Fehlermeldungen benutzerfreundlich
- Version in Footer aktualisieren
- Edge Cases: Was passiert bei leerem Ordner, keiner Berechtigung, etc.

---

## Wave 4 — Release

### GitHub Release Build
- GitHub Actions Workflow: `.github/workflows/build.yml`
- macOS Build mit PyInstaller
- Code-Signing (self-signed für Open Source)
- `.dmg` oder `.zip` Artefakt
- GitHub Release erstellen mit Changelog

### Docs
- README finale Überarbeitung (EN)
- MANUAL.md aktualisieren (DE + EN)
- CHANGELOG.md aktualisieren
- CONTRIBUTING.md erstellen
- Version auf 1.0.0

### Git Cleanup
- `.gitignore` prüfen (dist/, build/, *.pyc, __pycache__)
- Sicherstellen dass keine Build-Artefakte im Repo sind

---

## Risiken & Mitigationen

| Risiko | Mitigation |
|--------|-----------|
| customtkinter Limitationen (keine echten Flat-Icons) | Unicode-Emoji als Icons, konsistenter Stil |
| i18n Komplexität | Einfaches JSON-basiertes System, kein gettext |
| PyInstaller auf GitHub Actions | Testen mit macOS-Runner |
| Laufende App unterbrechen | Nur Code ändern, NICHT builden bis User sagt OK |
