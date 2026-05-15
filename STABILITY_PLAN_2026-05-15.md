# Stability Plan — v1.0.2 import failures (2026-05-15)

Investigation grounded in: CTO log (2026-04-30 + 2026-05-14), `icloudphotonator/{importer,orchestrator,resilience,scanner,photos_preflight}.py`, `packaging/entitlements.plist`, `iCloudPhotonator.spec`, `scripts/build_release.sh`, and external sources (osxphotos issues #1836/#1862/#1910/#1973, Apple DTS forum #724969, eclecticlight.co).

> **Methodik:** Jede Vermutung ist mit Datei:Zeile oder URL belegt. Confidence ehrlich markiert (Hoch / Mittel / Niedrig).

---

## TL;DR

| # | Symptom | Wahrscheinliche Root Cause | Confidence | Fix-Ansatz (1 Satz) |
|---|---------|----------------------------|-----------|---------------------|
| 1 | App startet seit 2 Wochen aus `/Volumes/iCloudPhotonator[ 1]/...` | DMG wird wiederholt frisch gemountet; ggf. **App Translocation** (Gatekeeper Path Randomisation) → unbekannter Pfad in TCC, FDA gilt evtl. nicht | Hoch (DMG-Launch belegt), Mittel (Translocation) | Bei Start prüfen ob `MEIPASS` unter `/Volumes/` oder `/private/var/folders/.../AppTranslocation/` liegt und User zum Move in `/Applications` zwingen (LetsMove-Pattern). |
| 2 | `AppleScriptError ... User canceled. (-128) range=1130-1147` ohne User-Aktion | Apple-Event-Timeout (60 s Default) wenn Photos.app blockiert/cold-start; `-128` aus PhotoScript-Wrapper, NICHT direkt aus AppleScript | Hoch (osxphotos #1910/#1836 dokumentieren identische Signatur) | osxphotos auf neueste Version, `--use-PhotoKit`-Pfad evaluieren, Photos vor Batch warm-up + Watchdog mit `killall Photos` (osxphotos #1862/#1973). |
| 3 | Importer-Timeout 30 s / 120 s, aber 14 min Lücke im Log | `ThreadPoolExecutor.future.result(timeout=N)` blockiert nur den Caller, **killt den Worker-Thread nicht** und osxphotos läuft weiter | **Sehr Hoch** (Code-Beweis: `importer.py:252-257`) | Auf `subprocess.Popen` + `Popen.kill()` umstellen ODER osxphotos in eigenem Process via `multiprocessing` mit hartem Kill. |
| 4 | Single-File-Fallback meldet `success=True, errors=0` aber Final-Tally `0 imported, 5 errors` | Wenn Report-CSV nicht existiert (kein File-Row geschrieben), liefert `_result_from_report` `success=fallback_success=True, imported=0, errors=0`. Orchestrator wertet das als „Import failed without a generated report" | **Sehr Hoch** (Beweis: `importer.py:278-285, 287` + `orchestrator.py:1112`) | `success` nur dann True, wenn `report_path.exists()` UND mindestens eine Zeile vorhanden ist; sonst `success=False`. |
| 5 | Externes Laufwerk verschwindet während 34-min-Hang | Kein Watchdog auf Source-Volume; `NetworkMonitor` wird offenbar nicht auf `/Volumes/Extern` gestartet; USB-Auto-Sleep unmountet das Drive | Hoch (Code-Beweis: `resilience.py:25-109` existiert, wird aber nicht im Import-Pfad eingesetzt) | Vor jeder Batch `os.path.ismount(source_volume_root)` prüfen + `NetworkMonitor` (oder Variante) auch für `/Volumes/Extern` aktivieren. |
| 6 | „Cold start" Photos.app dauert Minuten beim ersten Mal | osxphotos `photosLibraryWaitForPhotos` wartet auf Photos-Boot; default Apple-Event-Timeout 60 s ist zu kurz | Mittel (osxphotos #1836 nennt 600 GB-Library und mech. HDD als Faktor) | Vor erstem Import einen „warming up"-UI-State + längeren ersten-Lauf-Timeout (z. B. 600 s). |
| 7 | `-128` trotz korrekter Entitlements | `com.apple.security.automation.apple-events` korrekt gesetzt; aber bei Translocation TCC-Eintrag matcht evtl. nicht → Apple-Events scheitern lautlos | Mittel | Translocation-Detection (siehe #1) + Onboarding fragt FDA + Automation explizit nach Move. |
| 8 | PyInstaller-Bundle `PATH` für `exiftool`/`osascript` | Build verwendet `use_exiftool=False` (Orchestrator Zeile 646, 696), aber osxphotos ruft trotzdem `osascript` Subprocess — kein Risiko im aktuellen Pfad, aber Falle für Zukunft | Niedrig | Wenn exiftool wieder aktiviert: explizit `exiftool`-Pfad mitbundlen und über `OSXPHOTOS_EXIFTOOL_PATH` setzen. |

---

## Detailed Findings (per Strang)

### Strang 1 — DMG-Launch / App Translocation

**Beweis aus Log:**
> `MEIPASS: /Volumes/iCloudPhotonator 1/iCloudPhotonator.app/Contents/Frameworks` (Session 1)
> `MEIPASS: /Volumes/iCloudPhotonator/iCloudPhotonator.app/...` (Session 2)

Die „ 1" am Ende des Mount-Punktes zeigt, dass das DMG mehrfach gemountet wurde, ohne das vorherige zu unmounten — typisches Verhalten, wenn der User die App jedes Mal aus dem **frisch geöffneten DMG** startet, statt zu installieren.

**Risiken:**
- **App Translocation** (= Gatekeeper Path Randomisation): Wenn macOS die App in einen zufälligen `/private/var/folders/.../AppTranslocation/<UUID>/d/` Pfad kopiert, läuft die App aus einem **anderen Pfad** als der TCC-Eintrag erwartet. FDA/Automation werden dann ggf. nicht honoriert (Apple DTS thread [724969](https://developer.apple.com/forums/thread/724969)).
- **Read-only DMG**: `~/.icloudphotonator/` bleibt unter `$HOME` und ist beschreibbar — das passt, aber **PyInstaller `MEIPASS`-Caches** und Side-Effects (z. B. `.pyc`-Schreibversuche) können scheitern.
- **TCC matcht via App-Path + Code-Signature**. Bei Translocation matcht die Signatur zwar, aber der Pfad nicht; macOS hat in vergangenen Versionen damit Inkonsistenzen gezeigt.

**Aktueller Code-Status:** Keine Detection. `icloudphotonator/ui/app.py:1542-1546` loggt nur `MEIPASS`, prüft nicht ob es unter `/Volumes/` oder `/private/var/folders/.../AppTranslocation/` liegt.

**Best-Practice-Referenzen:**
- **LetsMove / PFMoveApplication** (Andy Matuschak, klassisch in Sparkle-Apps): zeigt Dialog „Move to Applications folder?" beim Start, kopiert die App, relauncht.
- **SecTranslocateIsTranslocatedURL / SecTranslocateCreateOriginalPathForURL** (privat, aber inoffiziell verwendet — [Synack-Artikel](https://www.synack.com/exploits-explained/untranslocating-apps/)).
- Pragmatische Python-Variante: `sys._MEIPASS` + `sys.executable` prüfen — wenn `/Volumes/` oder `AppTranslocation` → Dialog + Abbruch.

---

### Strang 2 — AppleScript -128 „User canceled"

**Beweis aus Log:**
> `AppleScriptError: run_script 'photosLibraryWaitForPhotos' failed: User canceled. (-128) app='iCloudPhotonator' range=1130-1147`
> `AppleScriptError: run_script 'photosLibraryImport' failed: User canceled. (-128)`

**Quellen:**
- [osxphotos #1910](https://github.com/RhetTbull/osxphotos/issues/1910): exakt dieselbe Range `1130-1147` + Signatur. Photos.app „blockiert ohne Window", `killall Photos` löst es manchmal. → in v0.69+ wurde PR #1870 gemerged, der bei Hängern Photos killt.
- [osxphotos #1836](https://github.com/RhetTbull/osxphotos/issues/1836): identische Signatur auf Sequoia 15.4.1. Maintainer: „Photos AppleScript interface is very buggy on Photos side". Trotzdem auch `-1712` (`AppleEvent timed out`) sichtbar.
- [AppleScript Definitive Guide, §19.5](https://litux.nl/mirror/applescriptdefinitiveguide/applescpttdg2-CHP-19-SECT-5.html): Apple-Event-Default-Timeout = **60 Sekunden**. Erweiterbar via `with timeout of N seconds` (max 8 947 848 s).
- [Apple DTS forum #730884](https://developer.apple.com/forums/thread/730884): Hardened-Runtime + Apple Events erfordert `com.apple.security.automation.apple-events` (haben wir) + `NSAppleEventsUsageDescription` (haben wir, `iCloudPhotonator.spec:222`).

**Was passiert wirklich:** `-128` aus PhotoScript ist KEIN echtes User-Cancel. Die PhotoScript-Lib wrappt den Apple-Event-Timeout: wenn ein `tell application "Photos"`-Call länger als der konfigurierte Timeout läuft, wirft AppleScript `-1712`, das wird von PhotoScript an manchen Stellen zu `-128` umgemünzt oder Photos.app re-raised `User canceled` als Folge eines internen Watchdogs (siehe osxphotos #1910 Diskussion). Effektiv: **Photos.app hängt → Apple Event timed out → wir bekommen `-128`**.

**Eigene Entitlements (Belege):**
`packaging/entitlements.plist` enthält:
- `com.apple.security.automation.apple-events` ✓ (zwingend für Hardened Runtime)
- `com.apple.security.cs.disable-library-validation` ✓ (PyInstaller benötigt)
- `com.apple.security.cs.allow-unsigned-executable-memory` ✓
- `com.apple.security.cs.allow-jit` ✓
- `com.apple.security.cs.allow-dyld-environment-variables` ✓

Fehlend (nicht zwingend, aber bei manchen TCC-Issues hilfreich): `com.apple.security.temporary-exception.apple-events` mit Photos-Bundle-ID. In modernen macOS-Versionen ist das jedoch eher Cargo-Cult, der Hauptkey reicht.

**Confidence:** Hoch — die Symptomatik passt 1:1 zu osxphotos #1910. Es ist KEIN Permissions-Problem auf dieser Maschine (Preflight `automation_permission=True`, FDA-Check über sqlite ist True).

---

### Strang 3 — Importer-Timeout killt Subprozess nicht

**Code-Beweis** (`icloudphotonator/importer.py:252-257`):
```python
with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
    future = executor.submit(_do_import)
    try:
        future.result(timeout=timeout)
    except concurrent.futures.TimeoutError:
        raise TimeoutError(f"osxphotos import timed out after {timeout}s")
```

**Problem:** `Future.result(timeout=...)` lässt den Caller nach `timeout` Sekunden zurück, **bricht aber den Worker-Thread NICHT ab**. `_do_import` ruft `import_cli(**import_kwargs)` synchron auf, das wiederum osxphotos+photoscript+osascript anstößt. Der Subprozess osascript läuft weiter; der Worker-Thread bleibt aktiv; der `with ThreadPoolExecutor` Block wartet beim Exit darauf, dass alle Worker fertig sind — der `with`-Exit ruft `shutdown(wait=True)` standardmäßig auf!

→ Das erklärt **direkt** die 14-min-Lücke: Wir werfen zwar `TimeoutError`, aber der `with`-Block wartet on-exit auf den Worker-Thread, der erst nach Hängern-Ende von osascript / Apple-Event zurückkommt. (Python 3.9+: `ThreadPoolExecutor(max_workers=1).__exit__` ruft `shutdown(wait=True)`).

**Wo's noch hängt:** `Future.result` selbst kehrt zurück (gut), aber das `raise` wird durch das `with __exit__` aufgehalten. Daher kommt das `TimeoutError` faktisch erst, wenn der Worker fertig ist.

**Beleg im Log:**
- Session 2, Single-File-Fallback timeout=30s, aber 14 min zwischen Log-Lines.

**Fix-Optionen (kein Code-Change jetzt — nur Vorschlag):**
1. **Pragmatisch:** `executor.shutdown(wait=False, cancel_futures=True)` (Py 3.9+) UND zusätzlich ein hartes Kill der osascript-Subprozesse (via `pgrep osascript` + `kill`).
2. **Sauber:** Statt Thread-Pool **`subprocess.Popen`** auf osxphotos CLI starten (`osxphotos import …`), `Popen.kill()` bei Timeout, return code parsen.
3. **Alternative:** osxphotos in **`multiprocessing.Process`** auslagern; bei Timeout `process.terminate()` / `process.kill()`.

Variante 2 ist am robustesten (sauberer Boundary) und matcht das, was die Code-Kommentare ohnehin suggerieren („import_cli completed successfully").

---

### Strang 4 — `success=True` ohne tatsächlichen Import

**Code-Beweis** (`icloudphotonator/importer.py:270-300`):
```python
def _result_from_report(self, report_path, fallback_success, ...):
    parsed = self._parse_report(report_path) if report_path.exists() else ImportResult(
        success=fallback_success,        # ← True wenn kein Exception
        imported_count=0,
        skipped_count=0,
        error_count=0,
        errors=[],
        report_path=None,
    )
    parsed.success = fallback_success and parsed.error_count == 0
```

**Was passiert in den 5 Single-File-Fallbacks (Session 1):**
1. osxphotos `import_cli(**kwargs)` returnt **innerhalb < 1 s** ohne Exception (höchstwahrscheinlich weil osxphotos sofort feststellt, dass Photos.app schon hängt — UND silent fails ODER weil die Quelldatei in der Zwischenzeit `No such file` ist — siehe Strang 5).
2. Da keine Exception fliegt, geht `importer.py:136` in den Erfolgs-Pfad: `return self._result_from_report(report_path, fallback_success=True)`.
3. Report-CSV wurde nie geschrieben → `report_path.exists()` ist False → `ImportResult(success=True, imported=0, errors=0)`.
4. Orchestrator loggt `success=True, errors=0` (`orchestrator.py:702-707`).
5. Aber: keine Row im Report → kein `row_by_path` Match → der „leere Report"-Pfad (`orchestrator.py:1083-1117`) klassifiziert die Datei als `"Import failed without a generated report"`.

→ **Doppelte Buchhaltung:** der Importer meldet Erfolg, der Orchestrator meldet Fehler. Beide haben recht in ihrer Welt; das Ergebnis ist UI-irreführend.

**Bug-Fix-Ansatz:**
- `importer.py:278-285`: Wenn `report_path` nicht existiert UND `fallback_success=True` UND `file_count > 0`: das ist **kein Erfolg**, sondern „silent fail". Setze `success=False` und einen aussagekräftigen Error: `"osxphotos returned without writing a report — likely Photos.app didn't import the file"`.
- Zusätzlich: `importer.py` sollte beim `_do_import` Exit prüfen, ob `report_path` existiert UND non-empty ist, und im negativen Fall eine `RuntimeError` werfen, damit das Orchestrator-Fallback nicht zugeschlagen wird (oder im Gegenteil — kontextabhängig).

**Confidence:** Sehr Hoch — direkter Code-Beweis + 1:1-Match mit Log-Anomalie.

---

### Strang 5 — Externes Laufwerk verschwindet

**Beweis aus Log:**
> `22:55:20  Files _DSF9269..9307 all "File not readable: [Errno 2] No such file or directory"`

Das externe USB-Drive ging während des 34-min-AppleScript-Hangs in Sleep / unmount.

**Code-Status:**
- `icloudphotonator/resilience.py` hat `NetworkMonitor` (Zeilen 25-109) mit `_check_path()` via `os.stat` und `asyncio.create_task(_monitor_loop)`. Funktional.
- `icloudphotonator/scanner.py` hat `_is_network_path` (Zeilen 193-229), das via `mount`-Output `smbfs|nfs|afpfs` erkennt — **USB-Drives matchen NICHT** (das sind `hfs`/`apfs`/`exfat`). Daher wird der Source als „lokal" behandelt und kein Network-/Staging-Pfad aktiviert.
- **`NetworkMonitor.start()` wird im Import-Pfad nirgends mit dem Source-Volume aufgerufen.** Grep zeigt nur Tests/Resilience-Module selbst.

**Folge:** Kein Heartbeat → der 34-min-Hang bemerkt nicht, dass das Volume weg ist → wenn osxphotos die Datei lesen will, gibt's `ENOENT`.

**Best-Practice-Fix:**
1. Vor jeder Batch `Path("/Volumes/Extern").is_mount()` (oder `os.path.ismount(...)`) prüfen. Wenn False → Abort mit klarer Fehlermeldung.
2. `NetworkMonitor` mit dem **Source-Root-Volume** starten, nicht nur bei explizit-network-fs. Callback: laufenden Import sauber pausieren (Photos-App ist gnadenlos, aber wir können die nächsten Batches abbrechen).
3. USB-Auto-Sleep verhindern: `caffeinate -dimsuw <pid>` Subprocess für die Dauer des Imports (klassisches macOS-Idiom). Mehr Wirkung als Polling.

---

### Strang 6 — Best-Practice-Audit (proaktiv)

**6.1 Code-Signing / Bundling**
- `scripts/build_release.sh:131-160` signiert `*.so/*.dylib` → Python.framework → main exec → app bundle. **Korrekt**, dem Apple-Vorgehen entsprechend.
- Entitlements werden NUR auf den outer-bundle-codesign-Call angewendet (Z. 157-159). **Korrekt.**
- ⚠️ `iCloudPhotonator.spec:197`: `codesign_identity='iCloudPhotonator Dev'` — das ist nur der **interne PyInstaller-Sign** vor dem späteren build_release-Resign. Sollte konsistent zu `Developer ID Application: e-Networkers GmbH (9MK4SNL8ZA)` sein oder `None` (späterer codesign überschreibt). Nicht direkt schädlich, aber unsauber.
- `build_release.sh:174` startet die App headless 6 s. **Reicht nicht** um echte Photos-AppleScript-Wege zu testen — nur Loader-Smoke-Test.

**6.2 Sandbox vs. Hardened Runtime**
- ✓ Kein `com.apple.security.app-sandbox` → App ist **nicht** sandboxed. Korrekt für Photos-Library-Zugriff über User-Pfade.
- Aber: Bei Sandbox wäre `/Volumes/Extern` nicht mehr lesbar ohne Security-Scoped-Bookmark. Da wir nicht sandboxed sind, geht's. **Kein Risiko aktuell.**

**6.3 Security-Scoped Bookmarks**
- Nicht implementiert. Bei Hardened Runtime nicht zwingend; aber gut, falls wir später sandboxen wollen. **Niedrig.**

**6.4 PyInstaller `PATH` für externe Tools**
- `exiftool` ist im PyInstaller-Bundle **nicht** als Binary mitgebundlet (geprüft `REQUIRED_PACKAGES` in `build_release.sh:30-37` → nur Python-Packages). Aktuell wird `use_exiftool=False` gesetzt (`orchestrator.py:646, 696`), darum nicht akut.
- `osascript` ist System-Binary unter `/usr/bin/osascript` → immer da. **Kein Risiko.**

**6.5 Photos-Cold-Start**
- Erste osxphotos-Operation nach Photos-Boot kann **Minuten** dauern (osxphotos #1836 erwähnt 600 GB-Library auf HDD, mehrere Minuten pro Foto). Wir haben:
  - `OSASCRIPT_TIMEOUT = 15` in `photos_preflight.py:66` für **Preflight-Pings** (das ist OK, hier nur „ping").
  - Aber: `photos_preflight.ensure_photos_responsive` (`photos_preflight.py:229-258`) versucht max **2 Recovery-Runden** mit `pkill -9 Photos` + restart + 5 s Wait. Bei großen Libraries reicht das oft nicht — Photos braucht länger.
- Es gibt **keinen** „Warming up Photos…"-UI-State; der User sieht nur die hängende Progress-Bar.

**6.6 Logfile Rotation**
- `icloudphotonator/ui/app.py:1542` und Umfeld setzt einen `FileHandler` ohne `RotatingFileHandler`. Bei 34-min-Hängern mit DEBUG-Level kann das schnell groß werden. Akut nur ein Komfort-Issue (Log-Tail in UI), aber das war der Grund der Frage.

**6.7 `os.chdir` in Worker-Thread** (`importer.py:238`)
- `_do_import` ruft `os.chdir(str(osxphotos_data_dir))` — `os.chdir` ist **prozessweit**, nicht thread-lokal. Wenn der Worker hängt UND parallel ein anderer Thread `getcwd()` braucht, kann das Verhalten verwirrend werden. Nur Komfort-Issue, kein Bug.

**6.8 Mehrfaches DMG-Mount**
- macOS hängt automatisch ` 1`/` 2` an, wenn dasselbe Volume-Label bereits gemountet ist. Das DMG vom User wird also nie unmounted. Wenn er den Import lange genug nutzt, sammeln sich Mounts an. **Nutzer-UX-Smell.**

**6.9 Preflight wird nur einmal vor erstem Batch geprüft**
- Code-Check (`orchestrator.py:622-635`): `ensure_photos_responsive` wird **vor jeder Batch** aufgerufen. ✓ Gut.
- Aber: Source-Volume-Mount wird **nicht** vor jeder Batch geprüft. ✗ Siehe Strang 5.

---

## Best-Practice Gaps — geordnet nach Risiko-Höhe

| Risiko | Lücke | Adressiert in |
|--------|-------|---------------|
| 🔴 Hoch | Timeout killt Worker/osascript nicht | Strang 3 |
| 🔴 Hoch | Single-File-Fallback meldet falschen Erfolg | Strang 4 |
| 🔴 Hoch | DMG-Launch / App-Translocation nicht erkannt | Strang 1 |
| 🟡 Mittel | Photos-Cold-Start ohne UI-Feedback | Strang 6.5 |
| 🟡 Mittel | Source-Volume nicht überwacht | Strang 5 |
| 🟡 Mittel | osxphotos-Version ggf. ohne PR #1870 (Kill-on-Hang) | Strang 2 |
| 🟢 Niedrig | `os.chdir` prozessweit im Worker | Strang 6.7 |
| 🟢 Niedrig | Logfile ohne Rotation | Strang 6.6 |
| 🟢 Niedrig | `codesign_identity` im Spec inkonsistent | Strang 6.1 |

---

## Vorgeschlagene Fix-Roadmap

### Quick wins (≤ 1 h)

1. **(Strang 4) Strenge `success`-Semantik in `importer.py:_result_from_report`** — wenn `report_path` nicht existiert / leer ist und `file_count > 0`: `success=False`, `error_count=file_count`, klare Fehlermeldung. *Adressiert: Strang 4.* Risiko: minimal, nur lokal.
2. **(Strang 1) DMG-/Translocation-Detection beim App-Start** — `sys._MEIPASS` oder `sys.executable` Pfad-Check, modaler Dialog „Bitte App nach `/Applications` ziehen". *Adressiert: Strang 1, 7.* Risiko: niedrig.
3. **(Strang 5) `os.path.ismount(source_root)`-Check vor jeder Batch** in `orchestrator.py` direkt nach `ensure_photos_responsive`. *Adressiert: Strang 5.* Risiko: niedrig.
4. **(Strang 6.5) UI-State „Photos.app wird vorbereitet…"** mit Erst-Lauf-Heuristik (Dauer des Preflights messen). *Adressiert: Strang 6.5.*

### Medium (~ 2–4 h, sinnvoll vor v1.0.3)

5. **(Strang 3) `subprocess.Popen`-Variante für osxphotos-Aufruf** — anstelle des In-Process-import_cli den osxphotos-CLI (oder ein eigenes Helper-Script via `-m icloudphotonator.osxphotos_helper`) als Subprozess starten, `Popen.kill()` bei Timeout, Return-Code prüfen. *Adressiert: Strang 3, 4 (sauberer Boundary).* Risiko: mittel — größerer Eingriff, gute Test-Coverage nötig.
6. **(Strang 2 / 6.5) osxphotos-Version pinnen + Kill-on-Hang Pfad** — auf eine Version mit PR #1870 (Kill Photos on hang) heben; optional eigenes `pkill Photos` + Re-Try-Wrapper bei `-128`/`-1712`. *Adressiert: Strang 2.* Risiko: mittel — osxphotos-Updates können neue API-Brüche bringen, daher mit `uv lock` + Smoke-Test.
7. **(Strang 5) `caffeinate -dimsuw <pid>`-Subprocess während Import** + `NetworkMonitor` auf Source-Volume aktivieren (auch für non-SMB-FS). *Adressiert: Strang 5.* Risiko: niedrig.
8. **(Strang 6.6) `RotatingFileHandler`** mit z. B. 5 MB × 5 Files. *Adressiert: Strang 6.6.* Risiko: trivial.

### Long-term (≥ 1 d, eigene Hotfix-Wave)

9. **(Strang 2) PhotoKit-Pfad evaluieren** — osxphotos `--use-PhotoKit` als alternativer Importer (Maintainer-Kommentar in #1862 empfiehlt das). PhotoKit benötigt andere Permissions (`NSPhotoLibraryAddUsageDescription` haben wir), aber umgeht AppleScript komplett. *Adressiert: Strang 2 root cause, Strang 6.5.* Risiko: hoch — neue Permission-UX, andere Bugs.
10. **(Strang 1) LetsMove-Pattern volle Implementierung** — App kopiert sich nach `/Applications`, relauncht, original DMG-App löscht sich. *Adressiert: Strang 1 root cause + UX.* Risiko: mittel — viele Edge-Cases (Permissions, Signature-Validierung).
11. **(Strang 3 / 6.5) osxphotos in eigenem Helper-Subprocess** mit JSON-RPC für Progress-Updates. Lange Investition, aber löst gleichzeitig Timeout-Kill, Progress-Reporting und Photos-Cold-Start-UX.

## Wave 1 — committed (2026-05-15)
Tasks 76, 77, 78, 79 — alle 4 Quick Wins/Medium aus der Roadmap, parallel implementiert.
Target-Release: v1.0.3 sobald grün.

---

## User decisions (2026-05-15)

- **osxphotos-Version:** `>=0.75.6` gepinnt → enthält PR #1870 (Kill-on-Hang) — kein Update nötig.
- **DMG-Launch:** **warnen** mit „Trotzdem fortfahren"-Button (nicht hart blocken).
- **PhotoKit-Pfad:** nicht jetzt (Long-Term).
- **First-Run-Timeout:** 600 s, Steady-State 120 s.
- **`caffeinate` während Import:** ja, **mit Setting in Preferences zum Deaktivieren** (default on).

---

## Anhang — Datei:Zeile-Referenzen (zusammengefasst)

- **`importer.py:252-257`** — `ThreadPoolExecutor` + `future.result(timeout)` Pattern (Strang 3).
- **`importer.py:270-300`** — `_result_from_report` Success-Semantik (Strang 4).
- **`importer.py:136`** — `return self._result_from_report(..., fallback_success=True)` Pfad (Strang 4).
- **`orchestrator.py:641-651`** — Batch-Import-Call, `timeout=120` (Strang 3).
- **`orchestrator.py:687-707`** — Single-File-Fallback-Loop, `timeout=30` (Strang 3, 4).
- **`orchestrator.py:1083-1117`** — Report-leere Behandlung, `"Import failed without a generated report"` (Strang 4).
- **`orchestrator.py:622-635`** — `ensure_photos_responsive`-Vorprüfung pro Batch (Strang 6.9).
- **`photos_preflight.py:229-258`** — `ensure_photos_responsive` mit 2 Recovery-Runden (Strang 6.5).
- **`photos_preflight.py:66`** — `OSASCRIPT_TIMEOUT = 15` (Strang 6.5).
- **`scanner.py:193-229`** — `_is_network_path` matcht nur `smbfs|nfs|afpfs` (Strang 5).
- **`resilience.py:25-109`** — `NetworkMonitor` existiert, wird nicht im Import-Pfad eingesetzt (Strang 5).
- **`packaging/entitlements.plist`** — 5 Hardened-Runtime-Keys, korrekt (Strang 2).
- **`iCloudPhotonator.spec:197, 215-225`** — internes Sign + `NSAppleEventsUsageDescription` (Strang 2, 6.1).
- **`scripts/build_release.sh:131-160`** — Sign-Pipeline (Strang 6.1).

---

*Erstellt: 2026-05-15 · Adaption der Workspace-Note „Analysis — v1.0.2 import failures" · Read-only Investigation als Basis.*
