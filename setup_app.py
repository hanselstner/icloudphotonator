from setuptools import setup

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
    "packages": ["icloudphotonator"],
    "includes": ["customtkinter", "osxphotos", "click", "pydantic"],
    "excludes": ["pytest", "pytest_asyncio"],
}

setup(
    app=APP,
    data_files=DATA_FILES,
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)