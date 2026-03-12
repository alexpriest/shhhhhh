"""Read and write macOS notification preferences."""
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import plistlib
import shutil
import subprocess

from shhhhhh.categories import resolve_category

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
    app_path: str = ""
    category: str = "Other"

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
        app_path = entry.get("path", "")
        apps.append(AppInfo(
            name=_resolve_name(entry),
            bundle_id=bundle_id,
            flags=entry.get("flags", 0),
            index=i,
            app_path=app_path,
            category=resolve_category(bundle_id, app_path),
        ))

    apps.sort(key=lambda a: a.name.lower())
    return apps


def set_flag(flags: int, bit: int, enabled: bool) -> int:
    """Set or clear a specific bit in the flags bitmask."""
    if enabled:
        return flags | (1 << bit)
    else:
        return flags & ~(1 << bit)


def backup_plist(plist_path: Path | None = None, backup_dir: Path | None = None) -> Path:
    """Backup the plist before modifying it."""
    plist_path = plist_path or PLIST_PATH
    backup_dir = backup_dir or Path.home() / ".shh"
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = backup_dir / f"backup-{timestamp}.plist"
    shutil.copy2(plist_path, backup_path)
    return backup_path


def write_apps(plist_path: Path | None = None, updates: dict[int, int] | None = None, restart: bool = True) -> None:
    """Write updated flags back to the plist."""
    plist_path = plist_path or PLIST_PATH
    if not updates:
        return

    with open(plist_path, "rb") as f:
        data = plistlib.load(f)

    for index, new_flags in updates.items():
        data["apps"][index]["flags"] = new_flags

    with open(plist_path, "wb") as f:
        plistlib.dump(data, f)

    if restart:
        subprocess.run(["killall", "usernoted"], capture_output=True)


def get_latest_backup(backup_dir: Path | None = None) -> Path | None:
    """Return the most recent backup file, or None."""
    backup_dir = backup_dir or Path.home() / ".shh"
    if not backup_dir.exists():
        return None
    backups = sorted(backup_dir.glob("backup-*.plist"), reverse=True)
    return backups[0] if backups else None


def restore_backup(backup_path: Path, plist_path: Path | None = None, restart: bool = True) -> None:
    """Restore a backup plist."""
    plist_path = plist_path or PLIST_PATH
    shutil.copy2(backup_path, plist_path)
    if restart:
        subprocess.run(["killall", "usernoted"], capture_output=True)
