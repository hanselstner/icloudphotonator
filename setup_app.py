from py2app.build_app import py2app as _py2app
from setuptools import setup


class PatchedPy2App(_py2app):
    """Clear setuptools metadata that py2app 0.28 rejects."""

    def finalize_options(self):
        self.distribution.install_requires = []
        super().finalize_options()

APP = ["icloudphotonator/__main__.py"]
DATA_FILES = []
OPTIONS = {
    "argv_emulation": False,
    "iconfile": None,
    "plist": {
        "CFBundleName": "iCloudPhotonator",
        "CFBundleDisplayName": "iCloudPhotonator",
        "CFBundleIdentifier": "com.hanselstner.icloudphotonator",
        "CFBundleVersion": "0.1.0",
        "CFBundleShortVersionString": "0.1.0",
        "LSMinimumSystemVersion": "13.0",
        "NSHighResolutionCapable": True,
        "CFBundleDocumentTypes": [],
    },
    "packages": [
        "icloudphotonator",
        "icloudphotonator.ui",
        "customtkinter",
        "osxphotos",
        "click",
        "pydantic",
    ],
    "includes": ["sqlite3", "tkinter", "objc", "Foundation", "AppKit"],
    "excludes": ["pytest", "pytest_asyncio"],
}

setup(
    app=APP,
    data_files=DATA_FILES,
    cmdclass={"py2app": PatchedPy2App},
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
