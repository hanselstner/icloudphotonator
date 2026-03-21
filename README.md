# 🖼️ iCloudPhotonator

![Python](https://img.shields.io/badge/Python-3.13+-blue?logo=python&logoColor=white)
![macOS](https://img.shields.io/badge/macOS-13%2B-black?logo=apple&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green)
![osxphotos](https://img.shields.io/badge/osxphotos-0.75.6-orange)
![Status](https://img.shields.io/badge/Status-In%20Development-yellow)

## Description

Ein intelligentes macOS-Migrationswerkzeug für große Foto-/Video-Archive nach Apple Fotos / iCloud.

A smart macOS migration tool that intelligently imports large photo/video archives into Apple Photos for iCloud sync.

## Features

- Smart scanning of large local and network-based archives
- Automatic batching for stable Apple Photos imports at scale
- Deduplication before import to reduce duplicates and retries
- Live Photo support for paired media assets
- Network source support with local staging where needed
- Crash recovery and resumable jobs via persistent state tracking
- Dynamic throttling to avoid overwhelming Photos.app and iCloud sync
- Native macOS UI built for migration monitoring and control

## Screenshots

Coming soon.

## Requirements

- macOS 13+ (Ventura)
- Apple Photos with iCloud Photos enabled
- `exiftool` recommended for richer metadata extraction

## Installation

1. Download the latest `.app` bundle from the [Releases](../../releases) page.
2. Move the app to your `Applications` folder if desired.
3. On first launch, right-click the app and choose **Open** to bypass Gatekeeper.

## Usage

1. Launch the app.
2. Choose a local folder or mounted network share as the source archive.
3. Start the migration and monitor discovery, staging, deduplication, and import progress.
4. Pause, resume, or stop as needed while iCloud Photos syncs in the background.

## Architecture

iCloudPhotonator combines a native SwiftUI macOS shell with a Python 3.13 backend. The backend orchestrates scanning, deduplication, job persistence, throttling, and `osxphotos`-driven imports into Apple Photos. SQLite stores durable job state, while WebSocket JSON-RPC connects the UI and backend.

## Dependencies & Licenses

| Dependency | Version | Purpose | License | Link |
|---|---:|---|---|---|
| osxphotos | 0.75.6 | Photo import engine & Photos.app integration | MIT | [Link](https://github.com/RhetTbull/osxphotos) |
| photoscript | - | AppleScript bridge for Photos.app | MIT | [Link](https://github.com/RhetTbull/PhotoScript) |
| Python | 3.13+ | Runtime | PSF License | [Link](https://www.python.org/) |
| SwiftUI | - | Native macOS UI framework | Apple (bundled) | - |
| SQLite | - | Persistent state & job tracking | Public Domain | [Link](https://www.sqlite.org/) |
| exiftool | - | Metadata extraction | Artistic/GPL | [Link](https://exiftool.org/) |
| py2app | - | macOS `.app` bundling | MIT | [Link](https://py2app.readthedocs.io/) |
| click | - | CLI framework | BSD-3 | [Link](https://click.palletsprojects.com/) |
| pydantic | - | Data validation | MIT | [Link](https://docs.pydantic.dev/) |
| websockets | - | WebSocket communication | BSD-3 | [Link](https://websockets.readthedocs.io/) |

## Development

```bash
git clone https://github.com/hanselstner/icloudphototnator.git
cd icloudphototnator
uv sync
uv run pytest
```

## Changelog

See [CHANGELOG.md](CHANGELOG.md).

## License

MIT — see [LICENSE](LICENSE).
