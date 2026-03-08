"""Read and write macOS notification preferences."""
from dataclasses import dataclass
from pathlib import Path
import plistlib

PLIST_PATH = Path.home() / "Library/Group Containers/group.com.apple.usernoted/Library/Preferences/group.com.apple.usernoted.plist"
SYSTEM_CENTER = "_SYSTEM_CENTER_:"
SOUND_BIT = 2   # bit position
BADGES_BIT = 1  # bit position


@dataclass
class AppInfo:
    name: str
    bundle_id: str
    flags: int
    index: int  # position in the plist apps array

    @property
    def sound(self) -> bool:
        return has_flag(self.flags, SOUND_BIT)

    @property
    def badges(self) -> bool:
        return has_flag(self.flags, BADGES_BIT)


def has_flag(flags: int, bit: int) -> bool:
    return bool(flags & (1 << bit))


def _resolve_name(app: dict) -> str:
    """Extract a friendly app name from the plist entry."""
    path = app.get("path", "")
    if path and path.endswith(".app"):
        return Path(path).stem
    return app["bundle-id"]


def read_apps(plist_path: Path | None = None) -> list[AppInfo]:
    """Read all non-system apps from the usernoted plist."""
    plist_path = plist_path or PLIST_PATH
    with open(plist_path, "rb") as f:
        data = plistlib.load(f)

    apps = []
    for i, entry in enumerate(data.get("apps", [])):
        bundle_id = entry.get("bundle-id", "")
        if bundle_id.startswith(SYSTEM_CENTER):
            continue
        apps.append(AppInfo(
            name=_resolve_name(entry),
            bundle_id=bundle_id,
            flags=entry.get("flags", 0),
            index=i,
        ))

    apps.sort(key=lambda a: a.name.lower())
    return apps
