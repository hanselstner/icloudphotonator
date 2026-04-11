# 📖 iCloudPhotonator — User Manual

## Table of Contents

1. [System Requirements](#1-system-requirements)
2. [Installation](#2-installation)
3. [First Launch & Permissions](#3-first-launch--permissions)
4. [Settings](#4-settings)
5. [Starting an Import (GUI)](#5-starting-an-import-gui)
6. [Starting an Import (CLI)](#6-starting-an-import-cli)
7. [During the Import](#7-during-the-import)
8. [Errors and Troubleshooting](#8-errors-and-troubleshooting)
9. [Resuming after Interruption](#9-resuming-after-interruption)
10. [After the Import](#10-after-the-import)
11. [FAQ](#11-faq)
12. [Technical Details for Advanced Users](#12-technical-details-for-advanced-users)

## 1. System Requirements

| Requirement | Details |
| --- | --- |
| Operating System | macOS 13 (Ventura) or newer |
| Apple Photos | Must be installed and opened at least once |
| Python | 3.13+ (only if building the app yourself or using the CLI) |
| Disk Space | At least 10 GB free space on the system drive (for staging) |
| iCloud Photos | Optional — if the target library syncs with iCloud, iCloud Photos should be enabled |

### Supported Sources

- Local folders (e.g., `~/Pictures/Archive`)
- External drives (e.g., `/Volumes/USB-Drive/Photos`)
- Network drives via SMB, NFS, or AFP (e.g., `/Volumes/NAS/Photos`)

### Supported Media Formats

All formats accepted by Apple Photos, including:

- **Photos**: JPEG, HEIC, PNG, TIFF, RAW (CR2, NEF, ARW, etc.)
- **Videos**: MOV, MP4, M4V
- **Live Photos**: Automatically detected when photo and video share the same base name

## 2. Installation

### Option A: Use a Pre-built .app

If you have a pre-built `iCloudPhotonator.app`:

1. Copy the app to your **Applications** folder (`/Applications`)
2. On first launch: Right-click → **Open** (to bypass Gatekeeper warning for unsigned apps)
3. Confirm with **Open**

### Option B: Build from Source

```bash
git clone https://github.com/hanselstner/icloudphotonator.git
cd icloudphotonator
uv sync
uv run pyinstaller iCloudPhotonator.spec
open dist/iCloudPhotonator.app
```

## 3. First Launch & Permissions

### Onboarding Wizard

On first launch, iCloudPhotonator shows a **step-by-step onboarding wizard** that guides you through the necessary setup:

1. **Welcome**: Overview of what the app does
2. **Permissions**: The app requests the required macOS permissions:
  - **Automation permission**: Allows the app to control Apple Photos via AppleScript
  - **Photo Library access**: Allows the app to access your photo library
3. **Ready**: Confirmation that everything is set up

### Automation Permission

The app needs to control Apple Photos via AppleScript.

1. The app shows a dialog: *"iCloudPhotonator wants to control Photos"*
2. Click **OK**
3. If the dialog doesn't appear or you declined:
  - Open **System Settings → Privacy & Security → Automation**
  - Enable **Photos** under **iCloudPhotonator**

### Photos Access

Apple Photos must be open and responsive.

- The app automatically checks if Photos.app is running and responsive (**Preflight Check**)
- If Photos is not running, it is started automatically
- If Photos is unresponsive, a restart is attempted

### Network Drive Access

When importing from a NAS or network drive:

1. Make sure the drive is **mounted** (visible in Finder under `/Volumes/`)
2. Verify you have **read access** to the photo folders
3. The app detects network paths automatically and enables **local staging**

## 4. Settings

Access settings via the **gear icon** (⚙️) in the top-right corner of the app.

### Import Performance

| Setting | Default | Description |
| --- | --- | --- |
| Min Batch Size | 5 | Minimum number of files per import batch |
| Max Batch Size | 20 | Maximum number of files per import batch |
| Cooldown between batches | 60s | Wait time between successive batches |
| Extended cooldown | 180s | Longer cooldown applied periodically |
| Extended cooldown every | 50 imports | How often the extended cooldown is triggered |

### Photos Management

| Setting | Default | Description |
| --- | --- | --- |
| Restart Photos every | 500 imports | Proactively restart Photos to prevent instability |
| Wait after restart | 120s | Time to wait after restarting Photos |

### Storage

| Setting | Default | Description |
| --- | --- | --- |
| Max staging size | 10 GB | Maximum local staging space for network files |

### Language

| Setting | Default | Description |
| --- | --- | --- |
| Language | English | UI language (English or Deutsch). Requires app restart. |

> Tip: The defaults work well for most systems. If Photos.app becomes unstable during import, reduce batch sizes and increase cooldowns. If your system handles imports well, you can carefully increase speeds.

Settings are saved to `~/.icloudphotonator/settings.json` and persist across app restarts.

## 5. Starting an Import (GUI)

### Step 1: Choose Source Folder

Click **"Browse"** and navigate to the folder containing your photos and videos. The app searches the selected folder and all subfolders recursively.

### Step 2: Album Name

- By default, the **source folder name** is used as the album name
- You can customize the name in the text field
- All imported photos will be assigned to this album in Apple Photos

### Step 3: Select Library

- The app automatically searches for Apple Photos libraries in `~/Pictures` and `/Users/Shared`
- Select your desired target library from the dropdown
- The default system library is pre-selected

### Step 4: Start Import

Click **"Start"**. The workflow:

1. **Scan Phase**: All files are inventoried (no files are copied)
2. **Duplicate Detection**: Already known files (by SHA-256 hash) are skipped
3. **Staging**: Network files are locally cached (max 10 GB)
4. **Import**: Files are imported into Apple Photos in batches
5. **Cleanup**: Staging files are deleted after successful import

## 6. Starting an Import (CLI)

### Simple Import

```bash
uv run icloudphotonator import-photos "/Volumes/NAS/Photos"
```

### With Options

```bash
uv run icloudphotonator import-photos "/Volumes/NAS/Photos" \
  --album "Family Archive" \
  --library "$HOME/Pictures/Family.photoslibrary"
```

### All Options

| Option | Description |
| --- | --- |
| --album | Target album name (default: source folder name) |
| --library / --mediathek | Path to the target library |
| --staging-dir | Local folder for network staging |
| --db-path | Path to the SQLite database |
| --help | Show all available options |

## 7. During the Import

### Understanding the Progress Display

The GUI shows the following metrics:

| Display | Meaning |
| --- | --- |
| Discovered | Total number of media files found |
| Imported | Files successfully imported into Apple Photos |
| Duplicates | Skipped files because they already exist |
| Errors | Files where the import failed |
| Staged | Currently locally cached files (for network sources) |

### Pause / Resume / Cancel

- **Pause**: Click **"Pause"** — the current batch completes, then the import stops
- **Resume**: Click **"Resume"** — the import continues exactly where it paused
- **Cancel**: Click **"Stop"** — the import ends, progress is saved

### File Status Meanings

| Status | Meaning |
| --- | --- |
| pending | File was recognized but not yet processed |
| importing | File is currently being imported |
| imported | File was successfully imported into Apple Photos |
| duplicate | File was detected as a duplicate and skipped |
| error | Import of this file failed |
| skipped | File was intentionally skipped (e.g., too large for staging) |

## 8. Errors and Troubleshooting

### "Photos.app is not responding"

**What happens automatically:**

The app has a 4-level escalation system:

1. **Level 1**: 2-minute pause, then retry
2. **Level 2**: 5-minute pause, then retry
3. **Level 3**: Photos.app is automatically restarted (graceful shutdown with up to 60s wait)
4. **Level 4**: The app pauses and shows a dialog — manual intervention required

Additionally, Photos is **proactively restarted every 500 successful imports** to prevent memory leaks.

**What you can do:**

- Wait — the app resolves most issues automatically
- At Level 4: Open Photos manually, wait until fully loaded, then click "Resume"

### Network Connection Lost

**What happens automatically:**

- The app detects connection loss within 10 seconds
- The import is **automatically paused**
- Once the network is available again, the import **resumes automatically**
- No files are lost

**What you can do:**

- Check your network connection (Finder → is the network drive still visible?)
- The app resumes on its own as soon as the path is reachable again

### "Staging area is full"

**What happens automatically:**

- The staging limit (10 GB) was reached
- The app waits until imported staging files have been cleaned up
- Then new files are staged and the import continues

**What you can do:**

- Nothing — the app handles this automatically
- If needed: free up disk space on the system drive

### "File too large for staging"

- Individual files exceeding the staging limit are **skipped**
- These appear as `skipped` in the progress display
- Import these files manually via Apple Photos (drag & drop)

### Permission Error

If the app has lost the Automation permission:

1. The app shows a dialog with instructions
2. Click **"Open System Settings"**
3. Navigate to **Privacy & Security → Automation**
4. Enable **Photos** under **iCloudPhotonator**
5. Restart the app

## 9. Resuming after Interruption

### App Restart

1. Start iCloudPhotonator
2. The app automatically detects the incomplete job
3. A dialog asks: *"Incomplete import found. Resume?"*
4. Click **"Resume"** — the import starts where it left off
5. Already imported files are **not** re-imported

### Computer Restart

Same as app restart:

1. Start the Mac
2. Open iCloudPhotonator
3. The incomplete job is detected and can be resumed

### Resume Dialog

The resume dialog shows:

- Name of the interrupted job
- Number of already imported files
- Number of remaining files
- Source folder and album name

## 10. After the Import

### Review Import Results

At the end of the import, the app shows a summary:

- ✅ Successfully imported files
- ⏭️ Skipped duplicates
- ❌ Failed files

### Retry Failed Files

If some files failed:

1. Click **"Retry"** in the GUI
2. Or via CLI: `uv run icloudphotonator retry-errors`
3. The app only retries the failed files

**Tip:** Sometimes imports fail due to temporary Photos issues. A retry often resolves this.

## 11. FAQ

**Are my original files modified or deleted?**

> No. iCloudPhotonator only reads files. Source files are never modified, moved, or deleted.

**Can I import multiple folders?**

> Yes, but sequentially. Start one import, wait until it finishes, then start the next with a different source folder.

**What happens during a power outage?**

> Progress is stored in the SQLite database. After restarting the Mac, the import can be resumed.

**Does the app work with shared libraries?**

> Yes. You can select the target library in the GUI or via CLI.

**How long does importing 50,000 photos take?**

> Depends on the source. From a local SSD: ~4–8 hours. From a NAS over Gigabit Ethernet: ~8–16 hours. The app is designed to handle these long runs stably.

**Can I use the Mac during the import?**

> Yes. The app runs in the background. Avoid using Apple Photos manually though, as it may interfere with the import.

**What are the cooldowns between batches?**

> The app intentionally waits between batches (60 seconds by default, 180 seconds every 50 files) to avoid overwhelming Apple Photos and iCloud sync. These values are configurable in Settings.

## 12. Technical Details for Advanced Users

### Database Location

The SQLite database is stored at:

```
~/.icloudphotonator/
```

The database contains:

- Job definitions (source folder, album, status)
- File status for all scanned files
- Hashes for duplicate detection
- Progress information for resume

### Settings File

User settings are stored at:

```
~/.icloudphotonator/settings.json
```

### Log Files

Logs are stored in the same directory:

```
~/.icloudphotonator/icloudphotonator.log
```

- Structured logging with timestamps
- Automatic log rotation
- Helpful for error diagnosis

### Staging Directory

For network files, a local staging directory is used:

```
/var/folders/.../icloudphotonator-staging/
```

- Maximum size: 10 GB (configurable)
- Cleaned up after each successful batch
- Guaranteed cleanup on app exit via `try/finally`
- Customizable via `--staging-dir`

### SQLite WAL Mode

The database uses WAL mode (Write-Ahead Logging) for maximum reliability:

- Checkpoints every 500 processed files
- Checkpoint on app exit
- No data loss on unexpected termination