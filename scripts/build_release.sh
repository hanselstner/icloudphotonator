#!/usr/bin/env bash
#
# build_release.sh — End-to-end macOS release pipeline for iCloudPhotonator.
#
# Steps:
#   1. Clean PyInstaller build
#   2. Dependency audit (verify required packages are bundled)
#   3. Code sign (.so/.dylib, Python framework, main binary, .app bundle)
#   4. App launch smoke test (catches import / dynamic-loader errors on signed bundle)
#   5. Build + sign DMG
#   6. Notarize + staple + validate
#   7. Upload DMG to GitHub Release (replaces existing asset)
#   8. Cleanup local artifacts
#
# Usage: ./scripts/build_release.sh [--version VERSION] [--skip-upload] [--skip-notarize]

set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
SIGNING_IDENTITY='Developer ID Application: e-Networkers GmbH (9MK4SNL8ZA)'
NOTARY_PROFILE='iCloudPhotonator'
GITHUB_REPO='hanselstner/icloudphotonator'

APP_NAME='iCloudPhotonator'
BUNDLE_ID='com.hanselstner.icloudphotonator'
DEFAULT_VERSION='1.0.0'

REQUIRED_PACKAGES=(
  PIL click customtkinter darkdetect osxphotos pydantic annotated_types bs4
  soupsieve bitmath mac_alias mako markdown2 more_itertools objexplore
  packaging pathvalidate ptpython pytimeparse2 shortuuid tenacity wurlitzer
  xdg_base_dirs cffi appdirs rich textx toml yaml requests certifi
  charset_normalizer idna urllib3 psutil photoscript wrapt markupsafe
  wcwidth prompt_toolkit typing_extensions
)

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
VERSION="$DEFAULT_VERSION"
SKIP_UPLOAD=0
SKIP_NOTARIZE=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --version)
      VERSION="$2"
      shift 2
      ;;
    --skip-upload)
      SKIP_UPLOAD=1
      shift
      ;;
    --skip-notarize)
      SKIP_NOTARIZE=1
      shift
      ;;
    -h|--help)
      sed -n '2,16p' "$0"
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_ROOT"

DIST_DIR="$PROJECT_ROOT/dist"
APP_PATH="$DIST_DIR/$APP_NAME.app"
DMG_NAME="$APP_NAME-$VERSION.dmg"
DMG_PATH="$DIST_DIR/$DMG_NAME"

log()  { printf '\n\033[1;34m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m!!\033[0m %s\n' "$*" >&2; }
fail() { printf '\033[1;31mxx\033[0m %s\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# 1. Clean build
# ---------------------------------------------------------------------------
log "Step 1/8 — Clean PyInstaller build (version $VERSION)"
rm -rf dist build
uv run pyinstaller --noconfirm --clean iCloudPhotonator.spec

[[ -d "$APP_PATH" ]] || fail "PyInstaller did not produce $APP_PATH"

# ---------------------------------------------------------------------------
# 2. Dependency audit
# ---------------------------------------------------------------------------
log "Step 2/8 — Dependency audit (${#REQUIRED_PACKAGES[@]} packages)"
EXE_PATH="$APP_PATH/Contents/MacOS/$APP_NAME"
[[ -f "$EXE_PATH" ]] || fail "Could not locate executable at $EXE_PATH"

# PyInstaller embeds pure-Python packages inside the PYZ archive appended
# to the executable; only compiled extensions are written to disk. Inspect
# both locations so the audit doesn't false-negative on PYZ-only packages.
PYZ_LISTING="$(mktemp -t icp-pyz.XXXXXX)"
uv run pyi-archive_viewer -l -r -b "$EXE_PATH" >"$PYZ_LISTING" 2>/dev/null \
  || fail "pyi-archive_viewer could not list $EXE_PATH"

missing=()
for pkg in "${REQUIRED_PACKAGES[@]}"; do
  if find "$APP_PATH/Contents" \
        \( -type d -iname "$pkg" -o -type f -iname "${pkg}.py" -o -type f -iname "${pkg}.so" \) \
        -print -quit | grep -q . ; then
    continue
  fi
  if grep -qE "^[[:space:]]+${pkg}(\.|\$)" "$PYZ_LISTING"; then
    continue
  fi
  missing+=("$pkg")
done

rm -f "$PYZ_LISTING"

if (( ${#missing[@]} > 0 )); then
  fail "Missing bundled packages: ${missing[*]}"
fi
log "All ${#REQUIRED_PACKAGES[@]} required packages found in bundle"

# ---------------------------------------------------------------------------
# 3. Code signing
# ---------------------------------------------------------------------------
log "Step 3/8 — Code signing with '$SIGNING_IDENTITY'"

sign_one() {
  codesign --force --options runtime --timestamp \
    --sign "$SIGNING_IDENTITY" "$1" >/dev/null
}

# Sign all dynamic libraries first (deepest → shallowest)
while IFS= read -r -d '' lib; do
  sign_one "$lib"
done < <(find "$APP_PATH" \( -name '*.so' -o -name '*.dylib' \) -print0)


# Sign embedded Python framework if present
PY_FRAMEWORK="$APP_PATH/Contents/Frameworks/Python.framework"
if [[ -d "$PY_FRAMEWORK" ]]; then
  while IFS= read -r -d '' bin; do
    sign_one "$bin"
  done < <(find "$PY_FRAMEWORK" -type f \( -perm +111 -o -name '*.dylib' \) -print0)
  sign_one "$PY_FRAMEWORK"
fi

# Sign main executable
sign_one "$APP_PATH/Contents/MacOS/$APP_NAME"

# Finally sign the .app bundle itself with hardened-runtime entitlements
# (Apple Events automation requires com.apple.security.automation.apple-events;
# applied only to the outer bundle, not to nested .dylibs/.so files.)
codesign --force --options runtime --timestamp \
  --entitlements "$PROJECT_ROOT/packaging/entitlements.plist" \
  --sign "$SIGNING_IDENTITY" "$APP_PATH" >/dev/null

codesign --verify --deep --strict --verbose=2 "$APP_PATH" \
  || fail "codesign verification failed"
log "App bundle signed and verified"

# ---------------------------------------------------------------------------
# 4. App launch smoke test (after signing — unsigned bundles fail to load
#    the embedded Python framework on macOS due to Team ID mismatches)
# ---------------------------------------------------------------------------
log "Step 4/8 — App launch smoke test"
LAUNCH_LOG="$(mktemp -t icp-launch.XXXXXX)"
"$APP_PATH/Contents/MacOS/$APP_NAME" >"$LAUNCH_LOG" 2>&1 &
LAUNCH_PID=$!
sleep 6
if kill -0 "$LAUNCH_PID" 2>/dev/null; then
  kill "$LAUNCH_PID" 2>/dev/null || true
  wait "$LAUNCH_PID" 2>/dev/null || true
fi
if grep -qE 'ModuleNotFoundError|ImportError|Failed to load Python shared library|dyld|Library not loaded|Symbol not found' "$LAUNCH_LOG"; then
  cat "$LAUNCH_LOG" >&2
  rm -f "$LAUNCH_LOG"
  fail "Launch smoke test failed — see log above"
fi
rm -f "$LAUNCH_LOG"
log "App launched cleanly (no import / loader errors in 6s)"

# ---------------------------------------------------------------------------
# 5. Build + sign DMG
# ---------------------------------------------------------------------------
log "Step 5/8 — Building DMG: $DMG_NAME"
rm -f "$DMG_PATH"
hdiutil create \
  -volname "$APP_NAME" \
  -srcfolder "$APP_PATH" \
  -ov -format UDZO \
  "$DMG_PATH" >/dev/null

sign_one "$DMG_PATH"
log "DMG built and signed: $DMG_PATH"

# ---------------------------------------------------------------------------
# 6. Notarize + staple
# ---------------------------------------------------------------------------
if (( SKIP_NOTARIZE )); then
  warn "Step 6/8 — Skipped (--skip-notarize)"
else
  log "Step 6/8 — Notarizing DMG (profile: $NOTARY_PROFILE)"
  xcrun notarytool submit "$DMG_PATH" \
    --keychain-profile "$NOTARY_PROFILE" \
    --wait \
    || fail "Notarization submission failed"

  log "Stapling notarization ticket"
  xcrun stapler staple "$DMG_PATH" || fail "Stapling failed"
  xcrun stapler validate "$DMG_PATH" || fail "Staple validation failed"
  spctl --assess --type open --context context:primary-signature -vv "$DMG_PATH" \
    || warn "spctl assessment reported issues — review above"
  log "Notarization complete and validated"
fi

# ---------------------------------------------------------------------------
# 7. GitHub upload
# ---------------------------------------------------------------------------
if (( SKIP_UPLOAD )); then
  warn "Step 7/8 — Skipped (--skip-upload)"
else
  log "Step 7/8 — Resolving GitHub release for tag $VERSION"

  GH_TOKEN="$(printf 'protocol=https\nhost=github.com\n\n' \
    | git credential fill 2>/dev/null \
    | awk -F= '/^password=/{print substr($0,10)}')"
  [[ -n "$GH_TOKEN" ]] || fail "Could not obtain GitHub token via 'git credential fill'"

  API="https://api.github.com/repos/$GITHUB_REPO"
  UPLOAD="https://uploads.github.com/repos/$GITHUB_REPO"

  RELEASE_ID="$(curl -fsSL \
    -H "Authorization: token $GH_TOKEN" \
    -H 'Accept: application/vnd.github+json' \
    "$API/releases/tags/$VERSION" 2>/dev/null \
    | python3 -c 'import json,sys
try: print(json.load(sys.stdin).get("id",""))
except Exception: pass' 2>/dev/null \
    || true)"

  if [[ -z "${RELEASE_ID:-}" ]]; then
    fail "Could not resolve release id for tag '$VERSION' on $GITHUB_REPO. Did you create the release first? e.g. 'gh release create $VERSION --notes-file RELEASE_NOTES.md'"
  fi

  log "Uploading to GitHub release $RELEASE_ID (tag $VERSION)"

  existing_id="$(curl -fsSL \
    -H "Authorization: token $GH_TOKEN" \
    -H 'Accept: application/vnd.github+json' \
    "$API/releases/$RELEASE_ID/assets" \
    | python3 -c "import json, sys; data=json.load(sys.stdin); name='$DMG_NAME'; print(next((str(a['id']) for a in data if a['name']==name), ''))")"

  if [[ -n "${existing_id:-}" ]]; then
    log "Deleting previous asset id=$existing_id ($DMG_NAME)"
    curl -fsSL -X DELETE \
      -H "Authorization: token $GH_TOKEN" \
      "$API/releases/assets/$existing_id" >/dev/null
  fi

  log "Uploading $DMG_NAME"
  curl -fsSL -X POST \
    -H "Authorization: token $GH_TOKEN" \
    -H 'Content-Type: application/octet-stream' \
    --data-binary "@$DMG_PATH" \
    "$UPLOAD/releases/$RELEASE_ID/assets?name=$DMG_NAME" >/dev/null
  log "Upload complete"
fi

# ---------------------------------------------------------------------------
# 8. Cleanup
# ---------------------------------------------------------------------------
log "Step 8/8 — Cleanup"
rm -f "$DMG_PATH"
log "Removed local DMG: $DMG_PATH"

log "Release pipeline finished successfully (version $VERSION)"
