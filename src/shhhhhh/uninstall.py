"""Thorough uninstall: the app bundle plus everything it left in ~/Library.

Modelled on Hazel's App Sweep. Only ever *moves to the Trash* (via /usr/bin/trash),
so a mistake is recoverable from the Finder. Apple's own software is refused.
"""
from __future__ import annotations

import os
import plistlib
import shutil
import sqlite3
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

    @property
    def needs_admin(self) -> list[Path]:
        """Paths not owned by the current user (App Store installs are root:wheel);
        the Finder has to move those and will ask for the account password."""
        return [p for p in self.paths if not _owned_by_me(p)]


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


def _identities(bundle_id: str) -> list[str]:
    """The ids an app's files are keyed by: the bundle id itself and, for Mac
    Catalyst builds, the iOS id underneath ("maccatalyst.com.x.y" -> "com.x.y")."""
    ids = [bundle_id]
    if bundle_id.startswith("maccatalyst."):
        ids.append(bundle_id[len("maccatalyst."):])
    return ids


def _belongs(name: str, ids: list[str]) -> bool:
    """Exact id, or an extension of it: "<id>.widgets", "<id>.intent-handler", "group.<id>.coredata"."""
    for ident in ids:
        if name == ident or name.startswith(f"{ident}."):
            return True
        if name.startswith("group.") and (name == f"group.{ident}" or name.startswith(f"group.{ident}.")):
            return True
        if name.endswith(f".{ident}"):  # team-id prefixed group containers: ABC123.com.x.y
            return True
    return False


def library_leftovers(bundle_id: str, app_name: str) -> list[Path]:
    """Support files keyed by the app's ids (plus their extensions) or the exact app name.

    Deliberately not swept: ~/Library/Mobile Documents (iCloud documents are the
    user's data on every device) and other apps' caches that merely mention the app.
    """
    ids = _identities(bundle_id)
    found: list[Path] = []

    def add(p: Path) -> None:
        if p.exists() and p not in found:
            found.append(p)

    # Folders whose children are named by bundle id (with extension suffixes)
    for folder in (
        "Application Support", "Caches", "Caches/CloudKit", "HTTPStorages", "WebKit", "Logs",
        "Application Scripts", "Group Containers", "Saved Application State", "Cookies",
        "Preferences", "LaunchAgents",
    ):
        root = LIBRARY / folder
        if not root.is_dir():
            continue
        for entry in root.iterdir():
            stem = entry.name
            for suffix in (".plist", ".savedState", ".binarycookies"):
                if stem.endswith(suffix):
                    stem = stem[: -len(suffix)]
            if _belongs(stem, ids) or (stem.endswith(".ShipIt") and _belongs(stem[:-7], ids)):
                add(entry)

    for folder in ("Application Support", "Caches", "Logs"):
        add(LIBRARY / folder / app_name)

    # Sandbox containers are UUID directories; the bundle id sits in their metadata.
    for container in _containers(ids):
        add(container)

    # Recent-documents lists the system keeps per app
    sfl_root = LIBRARY / "Application Support" / "com.apple.sharedfilelist"
    if sfl_root.is_dir():
        for p in sfl_root.rglob("*.sfl*"):
            if _belongs(p.name.split(".sfl")[0], ids):
                add(p)
    return found


def _container_identity(entry: Path) -> str:
    meta = entry / ".com.apple.containermanagerd.metadata.plist"
    try:
        with open(meta, "rb") as f:
            return plistlib.load(f).get("MCMMetadataIdentifier") or entry.name
    except Exception:
        return entry.name


def _containers(ids: list[str]) -> list[Path]:
    root = LIBRARY / "Containers"
    if not root.exists():
        return []
    hits = []
    for entry in root.iterdir():
        meta = entry / ".com.apple.containermanagerd.metadata.plist"
        try:
            with open(meta, "rb") as f:
                ident = plistlib.load(f).get("MCMMetadataIdentifier") or entry.name
        except Exception:
            ident = entry.name
        if _belongs(ident, ids):
            hits.append(entry)
    return hits


def _owned_by_me(path: Path) -> bool:
    try:
        return path.lstat().st_uid == os.getuid()
    except OSError:
        return True


def running_executables() -> list[str]:
    """Command paths of every running process, one snapshot."""
    result = subprocess.run(["ps", "-axo", "comm="], capture_output=True, text=True)
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _is_running(bundle: Path, procs: list[str] | None = None) -> bool:
    prefix = str(bundle / "Contents" / "MacOS") + "/"
    procs = running_executables() if procs is None else procs
    return any(p.startswith(prefix) for p in procs)


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


class UninstallError(RuntimeError):
    """One path could not be moved; ``moved`` lists what already went to the Trash."""

    def __init__(self, path: Path, detail: str, moved: list[Path]) -> None:
        super().__init__(f"could not move {path.name}: {detail}")
        self.path = path
        self.moved = moved


def execute(plan: UninstallPlan) -> list[Path]:
    """Move every planned path to the Trash. Returns what was moved.

    Leftovers go first and the .app last, so a refused .app (wrong password,
    cancelled dialog) never leaves an app on disk with its data gone — the
    .app is index 0 of the plan.
    """
    if plan.blocked or plan.running:
        raise RuntimeError(plan.blocked or "app is running — quit it first")
    moved: list[Path] = []
    for path in plan.paths[1:] + plan.paths[:1]:
        try:
            if not _owned_by_me(path):
                _finder_trash(path)
            elif Path(TRASH).exists():
                subprocess.run([TRASH, str(path)], check=True, capture_output=True, text=True)
            else:
                shutil.move(str(path), str(HOME / ".Trash" / path.name))
        except subprocess.CalledProcessError as exc:
            lines = (exc.stderr or "").strip().splitlines()
            raise UninstallError(path, lines[-1] if lines else f"exit {exc.returncode}", moved) from exc
        except OSError as exc:
            raise UninstallError(path, str(exc), moved) from exc
        moved.append(path)
    return moved


def _finder_trash(path: Path) -> None:
    """Ask the Finder to move a path to the Trash. For root-owned items the Finder
    puts up its usual administrator-password dialog; cancelling it raises here."""
    script = f'tell application "Finder" to delete POSIX file "{str(path)}"'
    subprocess.run(["osascript", "-e", script], check=True, capture_output=True, text=True)


def remove_from_plist(plist_path: Path, bundle_id: str, restart: bool = True) -> None:
    """Drop the app's notification entry so it stops showing in shh and System Settings."""
    with open(plist_path, "rb") as f:
        data = plistlib.load(f)
    data["apps"] = [a for a in data.get("apps", []) if a.get("bundle-id") != bundle_id]
    with open(plist_path, "wb") as f:
        plistlib.dump(data, f)
    if restart:
        subprocess.run(["killall", "usernoted"], capture_output=True)


KNOWLEDGE_DB = LIBRARY / "Application Support" / "Knowledge" / "knowledgeC.db"
_COCOA_EPOCH = 978307200  # 2001-01-01 in Unix seconds


def usage_from_knowledge() -> dict[str, datetime]:
    """Last app-usage start per bundle id from Screen Time's knowledgeC.db (about the
    last four weeks; needs Full Disk Access, which shh already has). {} if unreadable."""
    if not KNOWLEDGE_DB.exists():
        return {}
    try:
        con = sqlite3.connect(f"file:{KNOWLEDGE_DB}?mode=ro", uri=True)
        rows = con.execute(
            "SELECT ZVALUESTRING, MAX(ZSTARTDATE) FROM ZOBJECT "
            "WHERE ZSTREAMNAME = '/app/usage' AND ZVALUESTRING IS NOT NULL GROUP BY ZVALUESTRING"
        ).fetchall()
        con.close()
    except sqlite3.Error:
        return {}
    return {bid: datetime.fromtimestamp(when + _COCOA_EPOCH, tz=timezone.utc) for bid, when in rows if when}


def spotlight_last_used(app_path: str) -> datetime | None:
    """Spotlight's kMDItemLastUsedDate. Often null for apps launched by login items,
    Spotlight, or the Dock, so it is one signal among several."""
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


def _container_dir(bundle_id: str) -> Path | None:
    direct = LIBRARY / "Containers" / bundle_id
    if direct.exists():
        return direct
    hits = [h for h in _containers([bundle_id]) if _container_identity(h) == bundle_id]
    return hits[0] if hits else None


def library_last_touched(bundle_id: str, app_name: str) -> datetime | None:
    """Newest write among files only the app itself produces when it runs: its
    preferences plist, its saved window state, its own HTTP storage — inside its
    sandbox container when it has one. Deliberately ignores updaters, CloudKit sync
    caches, widget and extension containers, and directory mtimes, all of which
    move without the app being opened."""
    roots = [LIBRARY]
    container = _container_dir(bundle_id)
    if container is not None:
        roots.append(container / "Data" / "Library")
    files: list[Path] = []
    for root in roots:
        files.append(root / "Preferences" / f"{bundle_id}.plist")
        state = root / "Saved Application State" / f"{bundle_id}.savedState"
        if state.is_dir():
            files += [f for f in state.iterdir() if f.is_file()]
        files.append(root / "HTTPStorages" / f"{bundle_id}.binarycookies")
        storage = root / "HTTPStorages" / bundle_id
        if storage.is_dir():
            files += [f for f in storage.iterdir() if f.is_file()]
    newest: float | None = None
    for f in files:
        try:
            m = f.lstat().st_mtime
        except OSError:
            continue
        if newest is None or m > newest:
            newest = m
    return datetime.fromtimestamp(newest, tz=timezone.utc) if newest else None


def last_used(
    app: AppInfo,
    knowledge: dict[str, datetime] | None = None,
    procs: list[str] | None = None,
) -> tuple[datetime | None, bool]:
    """(best last-used estimate, running now). The estimate is the newest of Screen
    Time's usage record, Spotlight's last-used date, and the app's own Library writes.
    Pass ``knowledge`` and ``procs`` when calling for many apps so each is read once."""
    if not app.app_path.endswith(".app"):
        return None, False
    running = _is_running(Path(app.app_path), procs)
    knowledge = usage_from_knowledge() if knowledge is None else knowledge
    signals = [
        knowledge.get(app.bundle_id),
        spotlight_last_used(app.app_path),
        library_last_touched(app.bundle_id, Path(app.app_path).stem),
    ]
    dated = [d for d in signals if d is not None]
    return (max(dated) if dated else None), running


def age_label(when: datetime | None, now: datetime | None = None, running: bool = False) -> str:
    if running:
        return "running"
    if when is None:
        return "no trace"
    now = now or datetime.now(timezone.utc)
    days = (now - when).days
    if days < 1:
        return "today"
    if days < 30:
        return f"{days}d ago"
    if days < 365:
        return f"{days // 30}mo ago"
    return f"{days // 365}y ago"
