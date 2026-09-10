"""Thorough uninstall: the app bundle plus everything it left in ~/Library.

Modelled on Hazel's App Sweep. Only ever *moves to the Trash* (via /usr/bin/trash),
so a mistake is recoverable from the Finder. Apple's own software is refused.
"""
from __future__ import annotations

import plistlib
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from shhhhhh.plist import AppInfo

HOME = Path.home()
LIBRARY = HOME / "Library"
TRASH = "/usr/bin/trash"
PROTECTED_PREFIXES = ("/System/", "/usr/", "/bin/", "/sbin/", "/Library/Apple/")


@dataclass
class UninstallPlan:
    app: AppInfo
    paths: list[Path] = field(default_factory=list)
    blocked: str | None = None
    running: bool = False

    @property
    def size(self) -> int:
        return sum(_size(p) for p in self.paths)


def blocked_reason(app: AppInfo) -> str | None:
    if app.bundle_id.startswith("com.apple.") or app.system:
        return "Apple system software — leave it to Apple"
    if not app.app_path.endswith(".app"):
        return "not an app bundle (no .app on disk to remove)"
    if app.app_path.startswith(PROTECTED_PREFIXES):
        return f"lives in a protected location ({app.app_path})"
    if not Path(app.app_path).exists():
        return "the .app is already gone; only its notification entry is left"
    return None


def plan_uninstall(app: AppInfo) -> UninstallPlan:
    """Work out what an uninstall would trash, without touching anything."""
    plan = UninstallPlan(app=app, blocked=blocked_reason(app))
    if plan.blocked:
        return plan
    bundle = Path(app.app_path)
    plan.running = _is_running(bundle)
    plan.paths = [bundle] + library_leftovers(app.bundle_id, bundle.stem)
    return plan


def library_leftovers(bundle_id: str, app_name: str) -> list[Path]:
    """Support files keyed by bundle id (exact) or app name (exact directory name)."""
    found: list[Path] = []

    def add(p: Path) -> None:
        if p.exists() and p not in found:
            found.append(p)

    by_id = {
        "Application Support": (bundle_id,),
        "Caches": (bundle_id, f"{bundle_id}.ShipIt"),
        "Preferences": (f"{bundle_id}.plist",),
        "Saved Application State": (f"{bundle_id}.savedState",),
        "HTTPStorages": (bundle_id, f"{bundle_id}.binarycookies"),
        "Cookies": (f"{bundle_id}.binarycookies",),
        "WebKit": (bundle_id,),
        "Logs": (bundle_id,),
        "Application Scripts": (bundle_id,),
    }
    for folder, names in by_id.items():
        for name in names:
            add(LIBRARY / folder / name)
    for folder in ("Application Support", "Caches", "Logs"):
        add(LIBRARY / folder / app_name)

    # Preferences written under a suffix: com.example.app.helper.plist
    for p in (LIBRARY / "Preferences").glob(f"{bundle_id}.*.plist"):
        add(p)
    for p in (LIBRARY / "LaunchAgents").glob(f"{bundle_id}*.plist"):
        add(p)

    # Sandbox containers are UUID directories; the bundle id sits in their metadata.
    for container in _containers(bundle_id):
        add(container)
    for p in (LIBRARY / "Group Containers").glob(f"*.{bundle_id}"):
        add(p)
    return found


def _containers(bundle_id: str) -> list[Path]:
    root = LIBRARY / "Containers"
    if not root.exists():
        return []
    hits = []
    for entry in root.iterdir():
        meta = entry / ".com.apple.containermanagerd.metadata.plist"
        try:
            with open(meta, "rb") as f:
                ident = plistlib.load(f).get("MCMMetadataIdentifier")
        except Exception:
            ident = entry.name
        if ident == bundle_id:
            hits.append(entry)
    return hits


def _is_running(bundle: Path) -> bool:
    result = subprocess.run(["pgrep", "-f", str(bundle / "Contents/MacOS/")], capture_output=True)
    return result.returncode == 0


def _size(path: Path) -> int:
    try:
        if path.is_file():
            return path.stat().st_size
        return sum(p.stat().st_size for p in path.rglob("*") if p.is_file())
    except OSError:
        return 0


def human_size(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def execute(plan: UninstallPlan) -> list[Path]:
    """Move every planned path to the Trash. Returns what was moved."""
    if plan.blocked or plan.running:
        raise RuntimeError(plan.blocked or "app is running — quit it first")
    moved = []
    for path in plan.paths:
        if Path(TRASH).exists():
            subprocess.run([TRASH, str(path)], check=True, capture_output=True)
        else:
            dest = HOME / ".Trash" / path.name
            shutil.move(str(path), str(dest))
        moved.append(path)
    return moved


def remove_from_plist(plist_path: Path, bundle_id: str, restart: bool = True) -> None:
    """Drop the app's notification entry so it stops showing in shh and System Settings."""
    with open(plist_path, "rb") as f:
        data = plistlib.load(f)
    data["apps"] = [a for a in data.get("apps", []) if a.get("bundle-id") != bundle_id]
    with open(plist_path, "wb") as f:
        plistlib.dump(data, f)
    if restart:
        subprocess.run(["killall", "usernoted"], capture_output=True)


def last_used(app_path: str) -> datetime | None:
    """Spotlight's last-used date for an app bundle, or None if it has never been opened."""
    if not app_path.endswith(".app"):
        return None
    result = subprocess.run(["mdls", "-name", "kMDItemLastUsedDate", "-raw", app_path], capture_output=True, text=True)
    raw = result.stdout.strip()
    if result.returncode != 0 or raw in ("", "(null)"):
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%d %H:%M:%S %z")
    except ValueError:
        return None


def age_label(when: datetime | None, now: datetime | None = None) -> str:
    if when is None:
        return "never"
    now = now or datetime.now(timezone.utc)
    days = (now - when).days
    if days < 1:
        return "today"
    if days < 30:
        return f"{days}d ago"
    if days < 365:
        return f"{days // 30}mo ago"
    return f"{days // 365}y ago"
