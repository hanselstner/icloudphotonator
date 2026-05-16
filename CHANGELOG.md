# Changelog

All notable changes to iCloudPhotonator will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.0.4] — 2026-05-16

FDA registration UX fix: app now appears reliably in System Settings → Privacy & Security → Full Disk Access on fresh macOS Tahoe installs, without requiring users to manually drag the bundle into the FDA pane via the "+" button.

### Fixed
- **Full Disk Access UI visibility on macOS Tahoe**: bundle's `Info.plist` now declares the full standard set of `NS*UsageDescription` keys (Desktop, Documents, Downloads, RemovableVolumes, NetworkVolumes, SystemAdministration) in addition to the existing Photos/AppleEvents keys. Without these strings the TCC pane in System Settings does not render an entry, even when the bundle is correctly registered in `TCC.db`. Matches the declarations used by FDA-visible reference apps (Dropbox, BBEdit, etc.).
- **TCC attribution chain**: added an early `open(2)` probe against TCC-protected paths (`~/Library/Safari/Bookmarks.plist` and fallbacks) that runs in the bundle process before any subprocess or AppleEvent is launched. This guarantees the TCC record is staged against `com.hanselstner.icloudphotonator` (our bundle identity) on every launch, not against the parent terminal when the app is started from a dev environment.

### Notes
- macOS Tahoe 26.1/26.2 has an Apple-confirmed UI bug (FB21009024, fixed in 26.3 beta) where some bundles fail to render in the FDA pane even with correct TCC.db registration. If v1.0.4 still does not appear after a fresh install on those versions, use the "+" button in System Settings → Privacy & Security → Full Disk Access to add `/Applications/iCloudPhotonator.app` manually. No `tccutil reset` is required when upgrading from v1.0.3.

## [1.0.3] — 2026-05-15

Stability release addressing persistent import failures reported on production machines (CTO log 2026-05-14). No new features; all fixes target known-bad failure modes.

### Fixed
- **Importer**: Strict success accounting — batches no longer report `success=True` when the osxphotos report CSV is missing or unparseable. Subprocess timeouts now actually kill the worker (process group `os.killpg` + 5s grace SIGTERM → SIGKILL); previously `Future.result(timeout=N)` only blocked the caller while the osxphotos process kept running indefinitely. Resolves "0 photos imported but success reported" and "30s timeout claim followed by 14-min silent gap".
- **Volume resilience**: New volume watchdog detects when an external/network source disappears mid-import (e.g. USB auto-sleep) and aborts cleanly with a localized error instead of hanging in osxphotos. `caffeinate` is held during the import phase to prevent macOS from sleeping the system or display.
- **App launch**: Detects DMG-mounted launches (`/Volumes/iCloudPhotonator*/...`) and App Translocation (random `/private/var/folders/.../AppTranslocation/...` paths). Shows a one-time warning dialog asking the user to drag the app to `/Applications` first — TCC entries are bound to the bundle path and don't transfer from the DMG copy.
- **First-run UX**: Added "Warming up Photos.app" UI state with a 600s preflight timeout (was 30s). Photos.app on a cold launch with a large library can take several minutes to respond to the first AppleScript event; the previous 30s timeout produced spurious AppleScript -128 "User canceled" errors that aren't actually user cancellations.
- **PyInstaller bundle**: Frozen app now dispatches osxphotos via a `--run-osxphotos` self-call instead of `sys.executable -m osxphotos`, which silently failed in the bundle (the app binary doesn't honour `-m`).

### Changed
- `osxphotos` dependency pinned to `>=0.75.6` (was unpinned). Includes the LetsMove-kill-on-hang fix landed in osxphotos v0.69. No transitive dependency bumps.
- Error dialogs now show a tail of the last 40 log lines (collapsible) for easier diagnosis on user machines.
- Build pipeline auto-detects RELEASE_ID from the version tag instead of requiring it to be passed manually.

### Upgrade notes
- No `tccutil reset` needed — entitlements are unchanged from v1.0.2.
- If the previous v1.0.2 install was launched directly from the DMG, drag v1.0.3 to /Applications first to avoid the new translocation warning.

## [1.0.2] - 2026-04-29

### Fixed
- **macOS Automation permission prompt now appears correctly.** The hardened runtime previously blocked Apple Events silently because the entitlement was missing, so the app never showed up in *System Settings → Privacy & Security → Automation*. The build now ships with a proper entitlements.plist that grants `com.apple.security.automation.apple-events` and the standard PyInstaller exceptions (allow-unsigned-executable-memory, disable-library-validation, allow-jit, allow-dyld-environment-variables).

### Upgrade note
- If you previously installed v1.0.1, run this in Terminal once before launching v1.0.2 to clear stale TCC entries:
  ```
  tccutil reset AppleEvents com.hanselstner.icloudphotonator
  ```

## [1.0.1] — 2026-04-28

### Added

- Full Disk Access onboarding step: new 4-step wizard (Welcome → Automation → Full Disk Access → Ready) with deeplink to System Settings, live status check, and gated Next button
- Full Disk Access error dialog: actionable dialog (Open / Check Again / Restart App) shown when an import fails because Photos.sqlite is unreadable
- FDA-skip flag persisted in `config.json` across dialog instances; cleared on actual FDA grant; subtle hint when revisiting onboarding after a previous skip
- 9 new i18n keys (de+en) covering the FDA onboarding step and dialogs

### Fixed

- Import failure on macOS Sequoia when the bundled app lacks Full Disk Access: pre-import readability check (`PRAGMA schema_version` against `Photos.sqlite`) now maps `OperationalError` to a structured `error.full_disk_access_missing` marker and aborts cleanly instead of looping single-file retries with cryptic SQLite errors
- Mid-session TCC revocation handling: orchestrator scans `ImportResult.errors` for the structured marker and triggers the dialog once (one-shot guard), cancels the import, and skips fallback

## [1.0.0] — 2026-04-11

### Added

- Complete UI redesign: modern flat design with dark/light mode support
- Internationalization: English (default) + German with JSON-based locale files
- Settings dialog: configurable batch sizes, cooldowns, restart intervals, and language
- Step-by-step onboarding wizard with permission checks
- AAE sidecar exclusion: Apple edit sidecar files (.AAE) are automatically filtered out during scan

### Improved

- Smart escalation: 4-level automatic recovery (pause → longer pause → Photos restart → manual)
- Conservative throttling: smaller batches, longer cooldowns for stability
- Graceful Photos restart: clean quit with wait instead of force-kill
- Proactive Photos restart every N imports to prevent instability
- Cooldown optimization: skip cooldown for duplicate-only batches
- All internal log messages and error strings translated to English

### Fixed

- Escalation fix: only trigger on real Photos errors, not duplicates
- Staging cleanup: guaranteed cleanup via try/finally
- Oversized file handling: files larger than staging limit are skipped gracefully
- i18n bundle fix: locale JSON files correctly included in PyInstaller builds
- Button state fix: UI buttons correctly disabled/enabled during import phases

## [0.3.0-beta] — 2026-04-03

### Improved

- Conservative throttling: max batch size reduced to 20, cooldowns increased (60s between batches, 180s extended cooldown) for more stable imports with large archives
- Graceful Photos restart: Photos.app is cleanly quit instead of force-killed, with up to 60s wait for proper shutdown
- Proactive Photos restart: Photos is automatically restarted every 500 successful imports to prevent memory leaks and instability
- 4-level escalation: automatic recovery for Photos issues (2 min pause → 5 min pause → Photos restart → manual intervention)

### Fixed

- Staging cleanup guaranteed: try/finally ensures staged files are always cleaned up, even on errors
- Oversized files: files exceeding the staging limit are skipped instead of blocking the entire import

## [0.2.1-beta] — 2026-03-31

### Improved

- Auto-restart Photos.app: Photos is automatically restarted on consecutive import failures

## [0.2.0-beta] — 2026-03-29

### Added

- Network detection: network unavailability is detected and distinguished from silent failures
- Consecutive batch failure detection: automatic retry logic on consecutive failures
- Cumulative staging count: transparent display of total staged files
- Source folder validation: checks if source folder exists and is readable
- Photos preflight: automatic pre-check of Photos environment (permissions, library, iCloud)
- Automation permission with recovery loop: repeated checks instead of silent failure
- Retry errors: failed imports can be retried selectively
- Media validation: magic bytes check before import

### Improved

- Duplicate handling: duplicates and missing staging files treated as skip instead of error
- Batch minimum raised to 10: adaptive batching now reduces to minimum 10 files on errors (previously 1)

## [0.1.1-beta] — 2026-03-27

### Improved

- Photos auto-recovery: automatic recovery with window detection
- Preflight checks: Photos readiness check before import
- Import timeout control: timeout-based recovery for hanging imports
- Job count synchronization: correct counters on resume after interruption
- Error diagnostics: improved exception chains for better error tracing

## [0.1.0-beta] — 2026-03-21

### Added

- Scan → Staging → Dedup → Import pipeline: complete multi-stage workflow
- GUI with customtkinter: desktop interface with dark mode support
- CLI with click: command-line interface with all options
- Adaptive batching: ThrottleController dynamically adjusts batch size (5–50 files)
- SQLite persistence: WAL mode for reliable data storage
- Live Photo detection: photo/video pairs are automatically recognized
- Network resilience: retry with exponential backoff, automatic pause on connection loss
- Pause/Resume/Cancel: full control during scan and import
- Auto-album: album is automatically named after source folder
- Library selection: target library selectable in GUI or CLI
- Permission onboarding: guided dialog on first launch
- PyInstaller bundling: native macOS .app
- 215+ tests: comprehensive test suite