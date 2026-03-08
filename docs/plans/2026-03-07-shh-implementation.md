# shh Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build the `shh` CLI tool that batch-manages macOS notification settings (sound, badges) via the usernoted plist.

**Architecture:** Three-layer design — `plist.py` handles reading/writing the notification plist and bitmask manipulation, `display.py` handles the gradient logo and rich table output, `cli.py` wires it together with click commands. Installed as `shh` via pyproject.toml console_scripts.

**Tech Stack:** Python 3.11+, click, rich, plistlib (stdlib)

---

### Task 1: Project Scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `src/shhhhhh/__init__.py`
- Create: `src/shhhhhh/cli.py` (stub)
- Create: `src/shhhhhh/plist.py` (stub)
- Create: `src/shhhhhh/display.py` (stub)

**Step 1: Create pyproject.toml**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "shhhhhh"
version = "0.1.0"
description = "Silence your Mac, app by app"
requires-python = ">=3.11"
dependencies = [
    "click>=8.0",
    "rich>=13.0",
]

[project.scripts]
shh = "shhhhhh.cli:main"
```

**Step 2: Create stub modules**

`src/shhhhhh/__init__.py`:
```python
"""shh — silence your mac, app by app."""
__version__ = "0.1.0"
```

`src/shhhhhh/plist.py`:
```python
"""Read and write macOS notification preferences."""
```

`src/shhhhhh/display.py`:
```python
"""Terminal display: logo, tables, status output."""
```

`src/shhhhhh/cli.py`:
```python
"""CLI entry point."""
import click


@click.group()
def main():
    """shh — silence your mac, app by app."""
    pass
```

**Step 3: Install in dev mode and verify**

Run: `cd ~/Code/tools/shhhhhh && pip3 install -e .`
Run: `shh --help`
Expected: Shows click help with "shh — silence your mac, app by app."

**Step 4: Commit**

```bash
git add pyproject.toml src/
git commit -m "Scaffold project with click CLI entry point"
```

---

### Task 2: Plist Reader

**Files:**
- Create: `tests/test_plist.py`
- Modify: `src/shhhhhh/plist.py`

**Step 1: Write the failing tests**

```python
"""Tests for plist reading."""
import plistlib
import tempfile
from pathlib import Path

from shhhhhh.plist import (
    SOUND_BIT,
    BADGES_BIT,
    AppInfo,
    read_apps,
    has_flag,
)


def _make_plist(apps: list[dict], tmp_path: Path) -> Path:
    """Write a fake usernoted plist and return its path."""
    plist_path = tmp_path / "group.com.apple.usernoted.plist"
    with open(plist_path, "wb") as f:
        plistlib.dump({"apps": apps}, f)
    return plist_path


def test_read_apps_extracts_name_from_path(tmp_path):
    plist = _make_plist([
        {"bundle-id": "com.tinyspeck.slackmacgap", "flags": 14, "path": "/Applications/Slack.app"},
    ], tmp_path)
    apps = read_apps(plist)
    assert len(apps) == 1
    assert apps[0].name == "Slack"
    assert apps[0].bundle_id == "com.tinyspeck.slackmacgap"


def test_read_apps_falls_back_to_bundle_id(tmp_path):
    plist = _make_plist([
        {"bundle-id": "com.example.nopath", "flags": 14},
    ], tmp_path)
    apps = read_apps(plist)
    assert apps[0].name == "com.example.nopath"


def test_read_apps_skips_system_center(tmp_path):
    plist = _make_plist([
        {"bundle-id": "_SYSTEM_CENTER_:com.apple.something", "flags": 0},
        {"bundle-id": "com.real.app", "flags": 14, "path": "/Applications/RealApp.app"},
    ], tmp_path)
    apps = read_apps(plist)
    assert len(apps) == 1
    assert apps[0].name == "RealApp"


def test_has_flag_sound():
    assert has_flag(0b00000110, SOUND_BIT) is True   # bit 2 set
    assert has_flag(0b00000010, SOUND_BIT) is False   # bit 2 clear


def test_has_flag_badges():
    assert has_flag(0b00000110, BADGES_BIT) is True   # bit 1 set
    assert has_flag(0b00000100, BADGES_BIT) is False   # bit 1 clear


def test_read_apps_sorts_alphabetically(tmp_path):
    plist = _make_plist([
        {"bundle-id": "com.z", "flags": 14, "path": "/Applications/Zoom.app"},
        {"bundle-id": "com.a", "flags": 14, "path": "/Applications/Arc.app"},
    ], tmp_path)
    apps = read_apps(plist)
    assert apps[0].name == "Arc"
    assert apps[1].name == "Zoom"


def test_read_apps_handles_bundle_path(tmp_path):
    """Apps in .bundle directories should extract the name before .bundle."""
    plist = _make_plist([
        {"bundle-id": "com.apple.iCal", "flags": 14,
         "path": "/System/Library/UserNotifications/Bundles/com.apple.iCal.bundle"},
    ], tmp_path)
    apps = read_apps(plist)
    assert apps[0].name == "com.apple.iCal"  # bundle paths use bundle-id
```

**Step 2: Run tests to verify they fail**

Run: `cd ~/Code/tools/shhhhhh && python3 -m pytest tests/test_plist.py -v`
Expected: FAIL — cannot import `read_apps`, `AppInfo`, etc.

**Step 3: Implement plist.py**

```python
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
```

**Step 4: Run tests to verify they pass**

Run: `cd ~/Code/tools/shhhhhh && python3 -m pytest tests/test_plist.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/shhhhhh/plist.py tests/test_plist.py
git commit -m "Add plist reader with app name resolution and flag parsing"
```

---

### Task 3: Plist Writer

**Files:**
- Create: `tests/test_plist_write.py`
- Modify: `src/shhhhhh/plist.py`

**Step 1: Write the failing tests**

```python
"""Tests for plist writing."""
import plistlib
from pathlib import Path

from shhhhhh.plist import (
    SOUND_BIT,
    BADGES_BIT,
    read_apps,
    set_flag,
    write_apps,
    backup_plist,
)


def _make_plist(apps: list[dict], tmp_path: Path) -> Path:
    plist_path = tmp_path / "group.com.apple.usernoted.plist"
    with open(plist_path, "wb") as f:
        plistlib.dump({"apps": apps}, f)
    return plist_path


def _read_raw_flags(plist_path: Path, index: int) -> int:
    with open(plist_path, "rb") as f:
        data = plistlib.load(f)
    return data["apps"][index]["flags"]


def test_set_flag_enables_bit():
    assert set_flag(0b00000010, SOUND_BIT, True) == 0b00000110


def test_set_flag_disables_bit():
    assert set_flag(0b00000110, SOUND_BIT, False) == 0b00000010


def test_set_flag_noop_if_already_set():
    assert set_flag(0b00000110, SOUND_BIT, True) == 0b00000110


def test_write_apps_modifies_flags(tmp_path):
    plist = _make_plist([
        {"bundle-id": "com.test.app", "flags": 0b00000110, "path": "/Applications/Test.app"},
    ], tmp_path)
    apps = read_apps(plist)
    # Disable sound
    updates = {apps[0].index: set_flag(apps[0].flags, SOUND_BIT, False)}
    write_apps(plist, updates, restart=False)
    assert _read_raw_flags(plist, 0) == 0b00000010


def test_write_apps_preserves_other_flags(tmp_path):
    original_flags = 0x001080200e  # Spotify-like flags with many high bits
    plist = _make_plist([
        {"bundle-id": "com.test.app", "flags": original_flags, "path": "/Applications/Test.app"},
    ], tmp_path)
    apps = read_apps(plist)
    # Disable sound (bit 2)
    new_flags = set_flag(apps[0].flags, SOUND_BIT, False)
    updates = {apps[0].index: new_flags}
    write_apps(plist, updates, restart=False)
    result = _read_raw_flags(plist, 0)
    # Sound bit should be off, everything else preserved
    assert result & (1 << SOUND_BIT) == 0
    assert result & ~(1 << SOUND_BIT) == original_flags & ~(1 << SOUND_BIT)


def test_backup_plist(tmp_path):
    plist = _make_plist([{"bundle-id": "com.test", "flags": 6}], tmp_path)
    backup_dir = tmp_path / ".shh"
    backup_path = backup_plist(plist, backup_dir)
    assert backup_path.exists()
    with open(backup_path, "rb") as f:
        data = plistlib.load(f)
    assert data["apps"][0]["flags"] == 6
```

**Step 2: Run tests to verify they fail**

Run: `cd ~/Code/tools/shhhhhh && python3 -m pytest tests/test_plist_write.py -v`
Expected: FAIL — cannot import `set_flag`, `write_apps`, `backup_plist`

**Step 3: Implement write functions in plist.py**

Add to `src/shhhhhh/plist.py`:

```python
import shutil
import subprocess
from datetime import datetime


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
    """Write updated flags back to the plist.

    Args:
        plist_path: Path to the plist file.
        updates: Dict mapping app index -> new flags value.
        restart: Whether to restart usernoted after writing.
    """
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
```

**Step 4: Run tests to verify they pass**

Run: `cd ~/Code/tools/shhhhhh && python3 -m pytest tests/ -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/shhhhhh/plist.py tests/test_plist_write.py
git commit -m "Add plist writer with backup and restore support"
```

---

### Task 4: Display Module (Logo + Table)

**Files:**
- Modify: `src/shhhhhh/display.py`

**Step 1: Implement display.py**

No TDD for this task — it's pure visual output. Verify manually.

```python
"""Terminal display: logo, tables, status output."""
from rich.console import Console
from rich.table import Table
from rich.text import Text

from shhhhhh.plist import AppInfo

console = Console()

LOGO_LINES = [
    " ███████╗██╗  ██╗██╗  ██╗",
    " ██╔════╝██║  ██║██║  ██║",
    " ███████╗███████║███████║",
    " ╚════██║██╔══██║██╔══██║",
    " ███████║██║  ██║██║  ██║",
    " ╚══════╝╚═╝  ╚═╝╚═╝  ╚═╝",
]

# Grayscale gradient: bright -> dim (like sound fading)
GRAYS = [
    "color(250)",
    "color(248)",
    "color(245)",
    "color(243)",
    "color(240)",
    "color(238)",
]


def print_logo():
    """Print the gradient SHH logo."""
    console.print()
    for line, color in zip(LOGO_LINES, GRAYS):
        console.print(line, style=color, highlight=False)


def print_tagline():
    """Print the tagline below the logo."""
    console.print()
    console.print("  silence your mac, app by app", style="color(243)")


def print_summary(apps: list[AppInfo]):
    """Print the summary stats line."""
    total = len(apps)
    with_sound = sum(1 for a in apps if a.sound)
    with_badges = sum(1 for a in apps if a.badges)
    console.print()
    console.print(
        f"  {total} apps · {with_sound} with sound · {with_badges} with badges",
        style="color(245)",
    )


def print_app_table(apps: list[AppInfo]):
    """Print the app status table."""
    table = Table(
        show_header=True,
        header_style="bold color(250)",
        box=None,
        padding=(0, 2),
        pad_edge=True,
    )
    table.add_column("App", style="color(250)", min_width=28)
    table.add_column("Sound", justify="center", min_width=7)
    table.add_column("Badges", justify="center", min_width=7)

    for app in apps:
        sound = Text("✓", style="green") if app.sound else Text("✗", style="color(240)")
        badges = Text("✓", style="green") if app.badges else Text("✗", style="color(240)")
        table.add_row(app.name, sound, badges)

    console.print()
    console.print(table)


def print_result(message: str, undo_hint: str | None = None):
    """Print a result message after a change."""
    console.print()
    console.print(f"  {message}", style="bold color(250)")
    if undo_hint:
        console.print()
        console.print(f"  To undo: {undo_hint}", style="color(243)")
    console.print()
```

**Step 2: Quick visual test**

Run: `cd ~/Code/tools/shhhhhh && python3 -c "from shhhhhh.display import print_logo, print_tagline; print_logo(); print_tagline()"`
Expected: Gradient SHH logo appears in terminal with dim tagline below.

**Step 3: Commit**

```bash
git add src/shhhhhh/display.py
git commit -m "Add gradient logo and rich table display"
```

---

### Task 5: CLI Commands

**Files:**
- Modify: `src/shhhhhh/cli.py`
- Create: `tests/test_cli.py`

**Step 1: Write the failing tests**

```python
"""Tests for CLI commands."""
import plistlib
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from shhhhhh.cli import main


def _make_plist(apps: list[dict], tmp_path: Path) -> Path:
    plist_path = tmp_path / "group.com.apple.usernoted.plist"
    with open(plist_path, "wb") as f:
        plistlib.dump({"apps": apps}, f)
    return plist_path


SAMPLE_APPS = [
    {"bundle-id": "com.tinyspeck.slackmacgap", "flags": 0b00000010, "path": "/Applications/Slack.app"},  # sound OFF, badges ON
    {"bundle-id": "com.linear", "flags": 0b00000110, "path": "/Applications/Linear.app"},  # sound ON, badges ON
    {"bundle-id": "_SYSTEM_CENTER_:com.apple.something", "flags": 0},  # should be skipped
]


def test_list_shows_apps(tmp_path):
    plist = _make_plist(SAMPLE_APPS, tmp_path)
    runner = CliRunner()
    with patch("shhhhhh.cli.PLIST_PATH", plist):
        result = runner.invoke(main, ["list"])
    assert result.exit_code == 0
    assert "Slack" in result.output
    assert "Linear" in result.output
    assert "_SYSTEM_CENTER_" not in result.output


def test_sound_off_all(tmp_path):
    plist = _make_plist(SAMPLE_APPS, tmp_path)
    runner = CliRunner()
    backup_dir = tmp_path / ".shh"
    with patch("shhhhhh.cli.PLIST_PATH", plist), \
         patch("shhhhhh.cli.BACKUP_DIR", backup_dir), \
         patch("shhhhhh.plist.subprocess"):
        result = runner.invoke(main, ["sound", "off", "--all", "--yes"])
    assert result.exit_code == 0
    # Verify flags in plist
    with open(plist, "rb") as f:
        data = plistlib.load(f)
    # Slack: was 0b010, sound bit cleared -> 0b010 (was already off)
    assert data["apps"][0]["flags"] & 0b100 == 0
    # Linear: was 0b110, sound bit cleared -> 0b010
    assert data["apps"][1]["flags"] & 0b100 == 0
    assert data["apps"][1]["flags"] & 0b010 == 0b010  # badges preserved


def test_sound_on_specific_app(tmp_path):
    plist = _make_plist(SAMPLE_APPS, tmp_path)
    runner = CliRunner()
    backup_dir = tmp_path / ".shh"
    with patch("shhhhhh.cli.PLIST_PATH", plist), \
         patch("shhhhhh.cli.BACKUP_DIR", backup_dir), \
         patch("shhhhhh.plist.subprocess"):
        result = runner.invoke(main, ["sound", "on", "Slack"])
    assert result.exit_code == 0
    with open(plist, "rb") as f:
        data = plistlib.load(f)
    assert data["apps"][0]["flags"] & 0b100 == 0b100  # sound now ON


def test_sound_off_no_match(tmp_path):
    plist = _make_plist(SAMPLE_APPS, tmp_path)
    runner = CliRunner()
    with patch("shhhhhh.cli.PLIST_PATH", plist):
        result = runner.invoke(main, ["sound", "off", "NonExistent"])
    assert result.exit_code == 0
    assert "No apps matched" in result.output


def test_undo_restores_backup(tmp_path):
    plist = _make_plist(SAMPLE_APPS, tmp_path)
    backup_dir = tmp_path / ".shh"
    runner = CliRunner()
    # First, make a change to create a backup
    with patch("shhhhhh.cli.PLIST_PATH", plist), \
         patch("shhhhhh.cli.BACKUP_DIR", backup_dir), \
         patch("shhhhhh.plist.subprocess"):
        runner.invoke(main, ["sound", "off", "--all", "--yes"])
    # Now undo
    with patch("shhhhhh.cli.PLIST_PATH", plist), \
         patch("shhhhhh.cli.BACKUP_DIR", backup_dir), \
         patch("shhhhhh.plist.subprocess"):
        result = runner.invoke(main, ["undo"])
    assert result.exit_code == 0
    # Original flags should be restored
    with open(plist, "rb") as f:
        data = plistlib.load(f)
    assert data["apps"][1]["flags"] == 0b00000110  # Linear restored
```

**Step 2: Run tests to verify they fail**

Run: `cd ~/Code/tools/shhhhhh && python3 -m pytest tests/test_cli.py -v`
Expected: FAIL

**Step 3: Implement cli.py**

```python
"""CLI entry point."""
from pathlib import Path

import click

from shhhhhh.plist import (
    PLIST_PATH as _PLIST_PATH,
    SOUND_BIT,
    BADGES_BIT,
    read_apps,
    set_flag,
    write_apps,
    backup_plist,
    get_latest_backup,
    restore_backup,
)
from shhhhhh.display import (
    print_logo,
    print_tagline,
    print_summary,
    print_app_table,
    print_result,
    console,
)

# Module-level so tests can patch
PLIST_PATH = _PLIST_PATH
BACKUP_DIR = Path.home() / ".shh"

BIT_MAP = {
    "sound": SOUND_BIT,
    "badges": BADGES_BIT,
}


def _match_apps(apps, names):
    """Match app names using case-insensitive substring."""
    matched = []
    for name in names:
        found = [a for a in apps if name.lower() in a.name.lower()]
        matched.extend(found)
    return list({a.index: a for a in matched}.values())  # dedupe by index


@click.group()
def main():
    """shh — silence your mac, app by app."""
    pass


@main.command("list")
def list_cmd():
    """Show all apps and their notification settings."""
    apps = read_apps(PLIST_PATH)
    print_logo()
    print_tagline()
    print_summary(apps)
    print_app_table(apps)
    console.print()


def _toggle_command(setting: str):
    """Create an on/off toggle command for a setting."""
    bit = BIT_MAP[setting]

    @click.command(setting)
    @click.argument("state", type=click.Choice(["on", "off"]))
    @click.argument("apps", nargs=-1)
    @click.option("--all", "all_apps", is_flag=True, help="Apply to all apps")
    @click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
    def cmd(state, apps, all_apps, yes):
        enabled = state == "on"
        action = "Enabled" if enabled else "Disabled"
        setting_label = setting

        app_list = read_apps(PLIST_PATH)

        if all_apps:
            targets = app_list
        elif apps:
            targets = _match_apps(app_list, apps)
        else:
            raise click.UsageError("Specify app names or use --all")

        if not targets:
            console.print()
            console.print("  No apps matched", style="color(243)")
            console.print()
            return

        # Filter to apps that would actually change
        changes = [a for a in targets if a.sound != enabled] if bit == SOUND_BIT else [a for a in targets if a.badges != enabled]

        if not changes:
            print_logo()
            print_result(f"All {len(targets)} apps already have {setting_label} {'on' if enabled else 'off'}")
            return

        if all_apps and not yes:
            click.confirm(
                f"  {action} {setting_label} for {len(changes)} apps?",
                abort=True,
            )

        backup_plist(PLIST_PATH, BACKUP_DIR)

        updates = {a.index: set_flag(a.flags, bit, enabled) for a in changes}
        write_apps(PLIST_PATH, updates)

        verb = "Muted" if setting == "sound" and not enabled else f"{action} {setting_label} for"
        if setting == "sound" and not enabled:
            msg = f"Muted {len(changes)} apps"
        elif setting == "sound" and enabled:
            msg = f"Unmuted {len(changes)} apps"
        else:
            msg = f"{action} {setting_label} for {len(changes)} apps"

        print_logo()
        undo = f"shh {setting} {'on' if not enabled else 'off'} --all" if all_apps else None
        print_result(msg, undo)

    return cmd


main.add_command(_toggle_command("sound"))
main.add_command(_toggle_command("badges"))


@main.command()
def undo():
    """Restore the most recent backup."""
    backup = get_latest_backup(BACKUP_DIR)
    if not backup:
        console.print()
        console.print("  No backups found", style="color(243)")
        console.print()
        return

    restore_backup(backup, PLIST_PATH)
    print_logo()
    print_result("Restored from backup", f"backup: {backup.name}")
```

**Step 4: Run all tests**

Run: `cd ~/Code/tools/shhhhhh && python3 -m pytest tests/ -v`
Expected: All PASS

**Step 5: Manual smoke test against real plist**

Run: `shh list`
Expected: Shows gradient logo, tagline, summary stats, app table with real apps

**Step 6: Commit**

```bash
git add src/shhhhhh/cli.py tests/test_cli.py
git commit -m "Add CLI commands: list, sound, badges, undo"
```

---

### Task 6: README + GitHub Repo

**Files:**
- Create: `README.md`
- Create: `.gitignore`

**Step 1: Create .gitignore**

```
__pycache__/
*.egg-info/
dist/
build/
.eggs/
*.pyc
```

**Step 2: Create README.md**

```markdown
# shh

Silence your Mac, app by app.

A CLI tool for batch-managing macOS notification settings — toggle sound and badges for all apps or specific ones in a single command.

## Install

```bash
pip install shhhhhh
```

## Usage

```bash
shh list                     # show all apps + settings
shh sound off --all          # mute everything
shh sound on Mail Messages   # unmute specific apps
shh badges off --all         # remove all badge icons
shh undo                     # restore previous settings
```

## How it works

`shh` reads and writes macOS notification preferences directly from the `usernoted` plist, then restarts the daemon to apply changes. A backup is automatically created before every change.

## Requirements

- macOS 15+ (Sequoia / Tahoe)
- Python 3.11+

## License

MIT
```

**Step 3: Create GitHub repo and push**

Run: `cd ~/Code/tools/shhhhhh && gh repo create shhhhhh --private --source . --push`

**Step 4: Commit**

```bash
git add README.md .gitignore
git commit -m "Add README and .gitignore"
git push
```

---

### Task 7: Final Integration Test

**Step 1: Fresh install and full smoke test**

Run: `cd ~/Code/tools/shhhhhh && pip3 install -e . && shh list`
Expected: Logo + table with real apps from your Mac

Run: `shh sound off --all` (will prompt for confirmation)
Expected: Backs up plist, mutes all apps, shows result

Run: `shh undo`
Expected: Restores backup, confirms restoration

Run: `shh sound off Slack Zoom`
Expected: Mutes only Slack and Zoom

Run: `python3 -m pytest tests/ -v`
Expected: All tests pass
