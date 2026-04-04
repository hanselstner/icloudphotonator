# 🖼️ iCloudPhotonator

![Python](https://img.shields.io/badge/Python-3.13+-blue?logo=python&logoColor=white)
![macOS](https://img.shields.io/badge/macOS-13%2B-black?logo=apple&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green)
![osxphotos](https://img.shields.io/badge/osxphotos-powered-orange)
![Status](https://img.shields.io/badge/Status-Stable-brightgreen)
![Tests](https://img.shields.io/badge/Tests-216%2B%20passing-brightgreen)
![Build](https://img.shields.io/badge/Build-PyInstaller-blue)
![Version](https://img.shields.io/badge/Version-v1.0.0-blueviolet)

**Intelligent photo migration helper for macOS.**

> *Screenshots coming soon*

---

## What is iCloudPhotonator?

iCloudPhotonator is a macOS desktop app that **reliably and controllably** imports large photo and video archives from NAS systems, external drives, or local folders into **Apple Photos**.

The app was built for users who want to migrate **10,000 to 100,000+ media files** from existing folder structures — such as a Synology, QNAP, or external USB drive — into their Apple Photos library. Instead of a simple drag-and-drop, the import runs as a **multi-stage, fault-tolerant pipeline**:

**Scan → Staging → Duplicate Detection → Import → Cleanup**

Every step is persistently stored in a SQLite database. If the app crashes, the Mac restarts, or the network drops, the import can be resumed exactly where it left off — without importing files twice or losing any.

### Who is this for?

- You have **thousands of photos and videos** on a NAS or external drive
- You want to bring them **into Apple Photos** (local or with iCloud sync)
- You need a tool that **doesn't freeze, crash, or forget files** at scale
- You want to **pause, resume, and monitor** the import

### What iCloudPhotonator is NOT

- **Not a sync tool**: The app does not continuously sync folders. It imports once.
- **Not a backup tool**: It does not create backups. Source files are never modified or deleted.
- **Not a cloud upload tool**: The import goes into the local Apple Photos library. iCloud sync is handled by macOS.

### Key Features

- **Adaptive Batches**: Batch size adjusts automatically — grows on success, shrinks on errors
- **Network Resilience**: Import pauses automatically on connection loss and resumes when the network is back
- **Graceful Photos Restart**: When Apple Photos stops responding, it's cleanly restarted with escalation logic
- **4-Level Escalation**: 2 min pause → 5 min pause → Photos restart → Manual intervention
- **Internationalization**: English (default) and German UI
- **Settings Dialog**: Configurable batch sizes, cooldowns, restart intervals
- **Step-by-step Onboarding**: Guided wizard with permission checks on first launch
- **Dark/Light Mode**: Modern flat UI design with system appearance support

## Features

- 🗂️ **Auto-Album**: Automatically creates an album named after the source folder.
- 📚 **Library Selection**: Choose the target library in the GUI or via CLI (`--library` / `--mediathek`).
- ⏸️ **Pause / Resume / Cancel**: Full control during both scanning and importing.
- 🖥️ **GUI and CLI**: The same import engine works graphically or from the command line.
- 📸 **Live Photo Detection**: Photo/video pairs with the same base name are recognized as Live Photos.
- 🔄 **Resume after Interruption**: Incomplete jobs are detected and can be resumed.
- 🌐 **Network Drive Support**: NAS and other network sources are handled stably with local staging.
- 📊 **Transparent Progress**: Discovered, imported, skipped, duplicates, errors, and remaining files are always visible.
- 🚀 **Pipeline Mode**: Scan and import run in parallel — import starts after the first 50 scanned files.
- 📊 **Batch Summary**: After each batch and at job end, imported, skipped, and failed files are clearly listed.
- 🔐 **Permission Onboarding**: Step-by-step wizard guides through macOS permissions on first launch.
- ⚙️ **Settings Dialog**: Configure batch sizes, cooldowns, restart intervals, and language.
- 🌍 **Internationalization**: English (default) and German UI with JSON-based locale files.
- ⚠️ **Smart Error Detection**: Fatal errors like missing Automation permission are immediately detected.
- 💾 **Data Safety**: WAL checkpoints every 500 files and on exit — no data loss on crash.
- 🔍 **Photos Preflight**: Automatic pre-check of the Apple Photos environment before import.
- 🔄 **Graceful Photos Restart**: On silent failures, Photos is cleanly quit and restarted with up to 60s wait.
- 🛡️ **4-Level Escalation**: Automatic recovery for Photos issues with progressive escalation.
- 🎨 **Modern UI**: Flat design with dark/light mode support.

## ⚡ Smart Data Management

> **This is the core of iCloudPhotonator:** The app doesn't blindly push a large archive into Apple Photos all at once. Instead, it works in a controlled, database-backed, fault-tolerant manner.

### Scan Phase — Inventory Only, No Copying

During the scan phase, **nothing is imported and nothing is staged locally**. The app first inventories the existing files and writes results to SQLite.

- Captures **filenames/paths, sizes, media types, timestamps, and hashes**
- **Does not copy any files** to the Photos library during this phase
- Can inventory archives with **50,000 files in minutes**
- Stores the complete scan state in **SQLite** for subsequent deduplication, import, and resume

### Staging with 10 GB Limit

Network files are copied to a local temporary area before import.

- Uses local staging for network paths like **SMB, NFS, or AFP**
- Hard limit of **10 GB** prevents the system drive from filling up
- If the limit would be exceeded, the next step **is not blindly continued**
- Successfully imported staging files are **cleaned up** after each batch
- Result: **Never more than 10 GB** in the local staging area at any time

### Adaptive Batching

The app dynamically adjusts the load based on Apple Photos behavior.

- Starts with **5 files per batch**
- Grows on success up to **20 files per batch** (configurable)
- Halves on errors down to **5 files per batch** (configurable)
- Waits **60 seconds** between batches by default
- Extended cooldown of **3 minutes** every **50 files**

This keeps the import stable even with large volumes.

### Duplicate Detection

Before import, iCloudPhotonator checks files hash-based for duplicates.

- Uses **SHA-256 hashes** to detect identical files
- Skips duplicates within the current job and within the same batch
- Reduces unnecessary imports, wait times, and error chains
- The actual import also runs with `skip_dups=True`

### Resume after Crash or App Restart

Large migration runs must not restart from scratch on every problem.

- Persists job and file status in **SQLite**
- Stores active jobs separately so incomplete runs can be found
- Only retries **unfinished files**
- Already imported or skipped files are preserved
- The GUI detects incomplete jobs and actively offers **resume**

### Network Resilience

Especially with NAS systems or external sources, fault tolerance is critical.

- File copies are performed with **automatic retries**
- Exponential backoff reduces cascading failures on transient issues
- Network paths are monitored in the background
- Availability is checked every **10 seconds** by default
- On connection loss, the import pauses automatically; on recovery, it resumes

## Installation & Usage

### Prerequisites

- macOS **13+**
- **Apple Photos** installed on the system
- For iCloud targets: **iCloud Photos** enabled
- `exiftool` recommended for robust metadata processing
- Python **3.13+** if you want to build the app or use the CLI

### Build the .app

```bash
git clone https://github.com/hanselstner/icloudphototnator.git
cd icloudphototnator
uv sync
uv run pyinstaller iCloudPhotonator.spec
open dist/iCloudPhotonator.app
```

### CLI Usage

The CLI uses the same orchestration logic as the GUI.

```bash
uv run icloudphotonator --help
uv run icloudphotonator import-photos "/Volumes/NAS/Photos"
uv run icloudphotonator import-photos "/Volumes/NAS/Photos" --album "Family Archive" --library "~/Pictures/Family.photoslibrary"
```

Options:

- `--album`: Target album name (default: source folder name)
- `--library` / `--mediathek`: Target photo library
- `--staging-dir`: Local folder for network staging
- `--db-path`: Path to the SQLite database

### GUI Usage

Start the GUI via the built `.app` or directly:

```bash
uv run icloudphotonator
```

Workflow:

1. **Choose source folder** (local, external drive, or mounted network drive)
2. **Album name** is auto-detected or can be customized
3. **Select target library**
4. **Start import**
5. **Pause, resume, or cancel** as needed

## Technical Details

| Area | Technology | Purpose |
|---|---|---|
| Backend | Python 3.13 | Orchestration of scan, staging, dedup, persistence, and import |
| GUI | `customtkinter` | Native desktop interface for macOS |
| Import Engine | `osxphotos` | Import to Apple Photos incl. album/library management |
| Persistence | SQLite | Durable storage of jobs, file status, and resume |
| CLI | `click` | Command-line interface |
| i18n | JSON locales | English + German UI translations |
| Settings | `dataclass` + JSON | Persistent user configuration |
| Packaging | PyInstaller | Bundling as macOS `.app` |

Key modules:

- `scanner.py` — File discovery, classification, hashing, and Live Photo pairs
- `staging.py` — Local staging with 10 GB protection for network sources
- `throttle.py` — Adaptive batch and cooldown management
- `dedup.py` — Hash-based duplicate detection
- `resilience.py` — Retry logic and network monitoring
- `photos_preflight.py` — Pre-check of Apple Photos environment (permissions, library, iCloud)
- `orchestrator.py` — End-to-end workflow from scan to completion
- `settings.py` — Persistent settings with defaults
- `i18n.py` — Internationalization module

## Open-Source Dependencies

| Package | Version | Purpose | License |
|---------|---------|---------|---------|
| [osxphotos](https://github.com/RhetTbull/osxphotos) | ≥5.x | Import engine: Apple Photos communication via AppleScript | MIT |
| [customtkinter](https://github.com/TomSchimansky/CustomTkinter) | ≥5.2.2 | Desktop GUI: modern Tkinter with dark mode | MIT |
| [click](https://github.com/pallets/click) | ≥8.x | CLI framework | BSD-3-Clause |
| [pydantic](https://github.com/pydantic/pydantic) | ≥2.x | Data validation and settings management | MIT |
| [websockets](https://github.com/python-websockets/websockets) | ≥12.x | WebSocket communication | BSD-3-Clause |
| [aiohttp](https://github.com/aio-libs/aiohttp) | ≥3.x | Async HTTP client/server | Apache-2.0 |
| [PyInstaller](https://github.com/pyinstaller/pyinstaller) | ≥6.19 | Packaging as native macOS .app | GPL-2.0 (with bootloader exception) |
| [pytest](https://github.com/pytest-dev/pytest) | ≥8.x | Test framework | MIT |
| [pytest-asyncio](https://github.com/pytest-dev/pytest-asyncio) | ≥0.x | Async test support | Apache-2.0 |
| [PyObjC](https://github.com/ronaldoussoren/pyobjc) | 12.1 | macOS integration: native AppleScript, permissions | MIT |
| [SQLite](https://sqlite.org/) | (stdlib) | Embedded database for jobs, file status, progress | Public Domain |
| [hatchling](https://github.com/pypa/hatch) | ≥1.27 | Build system | MIT |

## Development

```bash
git clone https://github.com/hanselstner/icloudphototnator.git
cd icloudphototnator
uv sync
uv run python -m pytest tests/ -q --tb=short
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for development guidelines.

## Changelog

### v1.0.0 — April 4, 2026

- Complete UI redesign: modern flat design with dark/light mode support
- Internationalization: English (default) + German
- Settings dialog: configurable batch sizes, cooldowns, restart intervals
- Step-by-step onboarding wizard with permission checks
- Smart 4-level escalation for Photos.app issues
- Graceful Photos restart with clean quit and wait
- Cooldown optimization: skip cooldown for duplicate-only batches
- Oversized file handling: graceful skip instead of blocking

See [CHANGELOG.md](CHANGELOG.md) for the full version history.

## License

MIT — see [LICENSE](LICENSE).
