# dmgbuild settings for iCloudPhotonator release DMG.
#
# Invoked from scripts/build_release.sh:
#   uv run dmgbuild -s scripts/dmg_settings.py "iCloudPhotonator $VERSION" "$DMG_PATH"
#
# The volume name is supplied via the CLI positional arg (not hardcoded here),
# so the same settings file works for any version.

format = "UDZO"

files = ["dist/iCloudPhotonator.app"]

symlinks = {"Applications": "/Applications"}

icon = "assets/iCloudPhotonator.icns"
badge_icon = "assets/iCloudPhotonator.icns"

window_rect = ((200, 200), (600, 400))

icon_locations = {
    "iCloudPhotonator.app": (150, 200),
    "Applications": (450, 200),
}

icon_size = 100
text_size = 14

background = "builtin-arrow"

default_view = "icon-view"
show_icon_preview = False
include_icon_view_settings = "auto"
include_list_view_settings = "auto"
