"""Read and write macOS notification preferences."""
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import plistlib
import re
import shutil
import subprocess

from shhhhhh.categories import resolve_category

PLIST_PATH = Path.home() / "Library/Group Containers/group.com.apple.usernoted/Library/Preferences/group.com.apple.usernoted.plist"
SYSTEM_CENTER = "_SYSTEM_CENTER_:"
# Bit positions in each app's ``flags`` mask. Verified against System Settings
# on macOS 26 (2026-09-10): Claude vs CleanShot X differ only in bit 25 and read
# "Badges, Desktop" vs "Off"; Bartleby (bit 3) reads Temporary; App Store (bit 4)
# still counts as Desktop. Bits 12/13 (lock screen, Notification Center) are
# documented but unverified here, so nothing writes them.
BADGES_BIT = 1
SOUND_BIT = 2
TEMPORARY_BIT = 3    # Alert style: Temporary (a banner that goes away)
PERSISTENT_BIT = 4   # Alert style: Persistent (stays until dismissed)
ALLOW_BIT = 25       # Allow notifications
STYLES = ("off", "temporary", "persistent")

# Bundle IDs where the auto-extracted name would be wrong or unclear
FRIENDLY_NAMES: dict[str, str] = {
    "com.apple.iChat": "Messages",
    "com.apple.Passbook": "Wallet",
    "com.apple.BTNotificationAgent": "Bluetooth",
    "com.apple.BTUserNotifications": "Bluetooth Notifications",
    "com.apple.MobileSMS": "Messages",
    "com.apple.iCal": "Calendar",
    "com.apple.mdmclient.usernotifications.v2": "MDM Client",
    "com.apple.appfirewall.agent": "App Firewall",
    "com.apple.identityservicesd.firewall": "Identity Services Firewall",
    "com.apple.iBird.usernotification": "Game Center",
    "com.apple.PlatformSSO.notifications": "Platform SSO",
}

# Suffixes to strip when auto-extracting names from bundle IDs
_STRIP_SUFFIXES = [
    ".notifications", ".usernotification", ".usernotifications",
    ".agent", ".engagement",
]


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

    @property
    def allowed(self) -> bool:
        return has_flag(self.flags, ALLOW_BIT)

    @property
    def style(self) -> str:
        return style_of(self.flags)


def has_flag(flags: int, bit: int) -> bool:
    return bool(flags & (1 << bit))


def _humanize_bundle_id(bundle_id: str) -> str:
    """Turn a bundle ID into a human-readable name.

    Extracts the last component, strips known suffixes, and inserts
    spaces before capital letters (e.g. FamilyNotifications → Family Notifications).
    """
    # Take the last dotted component that is not itself just a suffix
    # ("com.apple.ecosystem.notifications" -> "ecosystem", not "").
    parts = bundle_id.split(".")
    bare = {suffix.lstrip(".").lower() for suffix in _STRIP_SUFFIXES}
    while len(parts) > 1 and parts[-1].lower() in bare:
        parts.pop()
    name = parts[-1]
    # Strip known suffixes (case-insensitive check on the lowered tail)
    for suffix in _STRIP_SUFFIXES:
        if name.lower().endswith(suffix.lstrip(".").lower()):
            name = name[: len(name) - len(suffix.lstrip("."))]
            break
    # Insert spaces before uppercase runs: "AppStore" → "App Store"
    name = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", name)
    # Also split acronym boundaries: "BTUser" → "BT User"
    name = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", " ", name)
    return name


def _resolve_name(app: dict) -> str:
    """Extract a friendly app name from the plist entry."""
    bundle_id = app.get("bundle-id", "")
    path = app.get("path", "")
    if path and path.endswith(".app"):
        return Path(path).stem
    if bundle_id in FRIENDLY_NAMES:
        return FRIENDLY_NAMES[bundle_id]
    if bundle_id.startswith("com.apple."):
        return _humanize_bundle_id(bundle_id)
    return bundle_id


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


def style_of(flags: int) -> str:
    """Alert style encoded in the flags: off, temporary, or persistent."""
    if has_flag(flags, PERSISTENT_BIT):
        return "persistent"
    if has_flag(flags, TEMPORARY_BIT):
        return "temporary"
    return "off"


def set_style(flags: int, style: str) -> int:
    """Clear both style bits, then set the one that matches ``style``."""
    if style not in STYLES:
        raise ValueError(f"unknown alert style {style!r}; expected one of {STYLES}")
    flags &= ~((1 << TEMPORARY_BIT) | (1 << PERSISTENT_BIT))
    if style == "temporary":
        flags |= 1 << TEMPORARY_BIT
    elif style == "persistent":
        flags |= 1 << PERSISTENT_BIT
    return flags


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
