# Release Process

This document describes how to build, sign, notarize and publish a new release of **iCloudPhotonator**.

The entire pipeline is automated by [`scripts/build_release.sh`](scripts/build_release.sh).

## Prerequisites

- macOS 13+ with Xcode Command Line Tools (`xcode-select --install`)
- [`uv`](https://docs.astral.sh/uv/) for Python dependency management
- Apple **Developer ID Application** certificate installed in the login keychain
  - Identity used: `Developer ID Application: e-Networkers GmbH (9MK4SNL8ZA)`
- Notarization credentials stored in a keychain profile named `iCloudPhotonator`
- A GitHub credential available via `git credential fill` for the `github.com` host
  (used to upload assets to the release)

### One-time: notarization credentials

Create the `iCloudPhotonator` keychain profile once per machine:

```bash
xcrun notarytool store-credentials iCloudPhotonator \
  --apple-id "<your-apple-id@example.com>" \
  --team-id  "9MK4SNL8ZA" \
  --password "<app-specific-password>"
```

The app-specific password is generated at <https://appleid.apple.com> → *Sign-In and Security* → *App-Specific Passwords*.

## Quick Release

From the project root:

```bash
./scripts/build_release.sh
```

This runs the full 8-step pipeline:

1. Clean build (`uv run pyinstaller --noconfirm --clean iCloudPhotonator.spec`)
2. Dependency audit — verifies all required packages are bundled
3. App launch smoke test — starts the app for 6s and checks for `ModuleNotFoundError`
4. Code signing — every `.so`/`.dylib`, the embedded Python framework, the main binary and the `.app` bundle (each with `--options runtime --timestamp`)
5. DMG creation (`hdiutil create` + `codesign`)
6. Notarization (`xcrun notarytool submit --wait` + `stapler staple` + `stapler validate`)
7. Upload to the configured GitHub release (deletes the previous asset of the same name first)
8. Cleanup of local DMG artifacts

## Options

| Flag | Effect |
|------|--------|
| `--version VERSION` | Override the version string used for the DMG name (default: `1.0.0`) |
| `--skip-upload`     | Build, sign and notarize, but do **not** upload to GitHub |
| `--skip-notarize`   | Build and sign, but skip notarization (and therefore the staple step) |
| `-h`, `--help`      | Print usage |

Examples:

```bash
# Build a v1.0.2 release end-to-end (tag must already exist on GitHub)
./scripts/build_release.sh --version v1.0.2

# Local dry-run: build + sign only, no notarization, no upload
./scripts/build_release.sh --skip-notarize --skip-upload
```

The `--version` value is used both as the DMG version suffix and as the
GitHub release **tag** to upload to. Create the tag/release first, e.g.
`gh release create v1.0.2 --notes-file RELEASE_NOTES.md`.

## Manual Steps

If you need to run individual steps by hand (e.g. to debug a single phase):

### Build

```bash
rm -rf dist build
uv run pyinstaller --noconfirm --clean iCloudPhotonator.spec
```

The signed `.app` bundle ends up in `dist/iCloudPhotonator.app`.

### Sign

```bash
IDENTITY='Developer ID Application: e-Networkers GmbH (9MK4SNL8ZA)'

find dist/iCloudPhotonator.app \( -name '*.so' -o -name '*.dylib' \) \
  -exec codesign --force --options runtime --timestamp --sign "$IDENTITY" {} \;

codesign --force --options runtime --timestamp --sign "$IDENTITY" \
  dist/iCloudPhotonator.app/Contents/MacOS/iCloudPhotonator

codesign --force --options runtime --timestamp --sign "$IDENTITY" \
  dist/iCloudPhotonator.app

codesign --verify --deep --strict --verbose=2 dist/iCloudPhotonator.app
```

### DMG

```bash
hdiutil create -volname iCloudPhotonator \
  -srcfolder dist/iCloudPhotonator.app \
  -ov -format UDZO \
  dist/iCloudPhotonator-1.0.0.dmg

codesign --force --options runtime --timestamp \
  --sign "$IDENTITY" dist/iCloudPhotonator-1.0.0.dmg
```

### Notarize

```bash
xcrun notarytool submit dist/iCloudPhotonator-1.0.0.dmg \
  --keychain-profile iCloudPhotonator --wait

xcrun stapler staple    dist/iCloudPhotonator-1.0.0.dmg
xcrun stapler validate  dist/iCloudPhotonator-1.0.0.dmg
spctl --assess --type open --context context:primary-signature -vv \
  dist/iCloudPhotonator-1.0.0.dmg
```

## Troubleshooting

### `sqlite3.OperationalError: unable to open database file`

The packaged app does not have **Full Disk Access**. Grant it in
*System Settings → Privacy & Security → Full Disk Access*. This is a runtime
issue, not a build issue — the bundle itself is fine.

### Dependency audit fails: "Missing bundled packages: …"

A package is declared in `pyproject.toml` but PyInstaller did not pick it up.
Add it to either `hiddenimports` or the `collect_all(...)` loop in
[`iCloudPhotonator.spec`](iCloudPhotonator.spec) and rebuild.

### App launch test fails with `ModuleNotFoundError`

Same root cause as above — a runtime import of an un-bundled module.
Fix the spec and re-run `./scripts/build_release.sh`.

### Notarization fails

- Check that the `iCloudPhotonator` keychain profile exists:
  `xcrun notarytool history --keychain-profile iCloudPhotonator`
- Inspect the rejection log:
  `xcrun notarytool log <submission-id> --keychain-profile iCloudPhotonator`
- Common causes: a binary inside the bundle was not signed with the hardened
  runtime, or the signature is missing a secure timestamp. The script signs
  every `.so`/`.dylib` with `--options runtime --timestamp` to avoid this.

### GitHub upload fails with 401 / 404

- Ensure `git credential fill` returns a token with `repo` scope for `github.com`.
  Test with: `printf 'protocol=https\nhost=github.com\n\n' | git credential fill`
- The script resolves the release id from the `--version` tag at runtime via
  the GitHub API. If you see *"Could not resolve release id for tag …"*, the
  tag does not exist yet — create the release first with
  `gh release create <tag> --notes-file RELEASE_NOTES.md` (e.g. `v1.0.2`).
