# CLAUDE.md — Project Notes for AI Assistants

This file documents non-obvious facts and conventions for AI assistants (and humans) working on iCloudPhotonator.

## Landing Page (GitHub Pages)

- Public URL: [https://hanselstner.github.io/icloudphotonator/](https://hanselstner.github.io/icloudphotonator/)
- Source: `main` branch, `/docs` folder (legacy Pages build, no Actions workflow)
- Single file: `docs/index.html` (no Jekyll, no build step)
- Download button URL is hardcoded — must be updated on every release to point at the new DMG asset
  - Pattern: `https://github.com/hanselstner/icloudphotonator/releases/download/vX.Y.Z/iCloudPhotonator-vX.Y.Z-macos.dmg`
  - Currently: v1.0.4
- After updating, GitHub Pages auto-rebuilds within ~1–2 minutes after the push to main

## Release Workflow

- Production releases live on `main` and use semver tags `vX.Y.Z`
- Build script: `scripts/build_release.sh` (PyInstaller → sign → notarize → dmgbuild → upload)
- DMG settings: `scripts/dmg_settings.py` (uses `dmgbuild`, builtin-arrow background, /Applications symlink)
- Signing identity: `Developer ID Application: e-Networkers GmbH (9MK4SNL8ZA)`
- Notarization profile: `iCloudPhotonator` (stored in `notarytool --keychain-profile`)
- Asset naming convention on GitHub Releases: `iCloudPhotonator-vX.Y.Z-macos.dmg` (note the leading `v`)
- Internal DMG filename (in `dist/`) is `iCloudPhotonator-X.Y.Z.dmg` (no `v`) — renamed during upload

## Info.plist (FDA / TCC requirements)

The Full Disk Access pane in System Settings refuses to render an app entry unless the bundle declares the full standard set of NS*UsageDescription keys, even if TCC.db is correctly populated. Keep these 8 keys in `iCloudPhotonator.spec` `info_plist`:

- NSAppleEventsUsageDescription
- NSPhotoLibraryUsageDescription
- NSDesktopFolderUsageDescription
- NSDocumentsFolderUsageDescription
- NSDownloadsFolderUsageDescription
- NSRemovableVolumesUsageDescription
- NSNetworkVolumesUsageDescription
- NSSystemAdministrationUsageDescription

Additionally, `icloudphotonator/__main__.py` runs an early FDA-attribution probe (`_early_fda_registration_probe`) before any subprocesses, to ensure the TCC record is staged against the bundle identity (not the parent terminal). Guarded against running inside `osxphotos` subprocesses.

## Repo Conventions

- Coordinator-agent workflow: spec note + delegated implementor agents; no direct edits by Coordinator
- Auto-commit is enabled in the workspace
- README.md version badge is auto-updated by `scripts/build_release.sh` Step 8 on every release
- Tests: `pytest` from repo root, 276+ passing as of v1.0.5
- Python: 3.13+
