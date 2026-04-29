# -*- mode: python ; coding: utf-8 -*-
import os
from pathlib import Path

import customtkinter
from PyInstaller.utils.hooks import collect_all

APP_NAME = "iCloudPhotonator"
APP_VERSION = "1.0.1"
BUNDLE_IDENTIFIER = "com.hanselstner.icloudphotonator"
PROJECT_ROOT = Path(SPECPATH)
ENTRYPOINT = PROJECT_ROOT / "icloudphotonator" / "__main__.py"
CUSTOMTKINTER_PATH = Path(customtkinter.__file__).resolve().parent


def _dedupe(items):
    seen = set()
    result = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


datas = [
    (str(CUSTOMTKINTER_PATH), "customtkinter"),
    (os.path.join("icloudphotonator", "locales"), "locales"),  # i18n translations
    (str(PROJECT_ROOT / "assets" / "icon_512.png"), "assets"),
]
binaries = []
hiddenimports = [
    "customtkinter",
    "osxphotos",
    "click",
    "pydantic",
    "icloudphotonator",
    "icloudphotonator.ui",
    "icloudphotonator.ui.app",
    "icloudphotonator.ui.bridge",
    "icloudphotonator.ui.onboarding",
    "icloudphotonator.ui.settings_dialog",
    "icloudphotonator.ui.stats_card",
    "icloudphotonator.ui.log_view",
    "icloudphotonator.importer",
    "icloudphotonator.scanner",
    "icloudphotonator.orchestrator",
    "icloudphotonator.db",
    "icloudphotonator.job",
    "icloudphotonator.state",
    "icloudphotonator.staging",
    "icloudphotonator.throttle",
    "icloudphotonator.resilience",
    "icloudphotonator.dedup",
    "sqlite3",
    "wurlitzer",
    "applescript",
    "bitstring",
    "bitarray",
    "bpylist2",
    "cgmetadata",
    "osxmetadata",
    "photoscript",
    "makelive",
    "xattr",
    "objc",
    "Foundation",
    "AppKit",
    "CoreFoundation",
    "CoreServices",
    "CoreMedia",
    "CoreAudio",
    "CoreLocation",
    "CoreML",
    "AVFoundation",
    "AVFAudio",
    "Contacts",
    "FSEvents",
    "Metal",
    "Photos",
    "Quartz",
    "Vision",
    "ScriptingBridge",
    "UniformTypeIdentifiers",
    "tenacity",
    "wrapt",
    "more_itertools",
    "shortuuid",
    "toml",
    "yaml",
    "rich",
    "blessed",
    "certifi",
    "psutil",
    "pytimeparse2",
    "strpdatetime",
    "textx",
    "arpeggio",
    "markdown2",
    "mako",
    "mako.template",
    "mako.runtime",
    "markupsafe",
    "cffi",
    "PIL",
    "xdg_base_dirs",
    "bs4",
    "soupsieve",
    "bitmath",
    "mac_alias",
    "objexplore",
    "packaging",
    "packaging.version",
    "packaging.specifiers",
    "pathvalidate",
    "ptpython",
    "darkdetect",
    "annotated_types",
    "appdirs",
]

for package_name in (
    "osxphotos",
    "customtkinter",
    "bitstring",
    "utitools",
    "osxmetadata",
    "photoscript",
    "cgmetadata",
    "makelive",
    "strpdatetime",
    "textx",
    "arpeggio",
    "bpylist2",
    "PIL",
    "xdg_base_dirs",
    "bs4",
    "soupsieve",
    "bitmath",
    "mac_alias",
    "mako",
    "markdown2",
    "more_itertools",
    "packaging",
    "pathvalidate",
    "pytimeparse2",
    "shortuuid",
    "tenacity",
    "wurlitzer",
    "objexplore",
    "ptpython",
    "darkdetect",
    "annotated_types",
    "cffi",
    "appdirs",
):
    package_datas, package_binaries, package_hiddenimports = collect_all(package_name)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hiddenimports

datas = _dedupe(datas)
binaries = _dedupe(binaries)
hiddenimports = _dedupe(hiddenimports)


a = Analysis(
    [str(ENTRYPOINT)],
    pathex=[str(PROJECT_ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity='iCloudPhotonator Dev',
    entitlements_file=str(PROJECT_ROOT / "packaging" / "entitlements.plist"),
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name=APP_NAME,
)
app = BUNDLE(
    coll,
    name=f'{APP_NAME}.app',
    icon=str(PROJECT_ROOT / 'assets' / 'iCloudPhotonator.icns'),
    bundle_identifier=BUNDLE_IDENTIFIER,
    version=APP_VERSION,
    info_plist={
        'CFBundleDisplayName': APP_NAME,
        'CFBundleName': APP_NAME,
        'CFBundleVersion': APP_VERSION,
        'CFBundleShortVersionString': APP_VERSION,
        'LSMinimumSystemVersion': '13.0',
        'NSHighResolutionCapable': True,
        'NSAppleEventsUsageDescription': 'iCloudPhotonator needs access to the Photos app to import photos and videos.',
        'NSPhotoLibraryUsageDescription': 'iCloudPhotonator needs access to your photo library to import photos and videos.',
        'CFBundleDocumentTypes': [],
    },
)
