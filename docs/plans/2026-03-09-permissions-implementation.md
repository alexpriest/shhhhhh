# Permissions Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a friendly permission check that catches Full Disk Access errors and guides users through setup, with an option to open System Settings directly.

**Architecture:** New `permissions.py` module handles detection and display. The CLI group callback gates all subcommands. Display uses the existing Rich console and grayscale style from `display.py`.

**Tech Stack:** Python 3.11+, Click, Rich

---

### Task 1: Permission check module + tests

**Files:**
- Create: `src/shhhhhh/permissions.py`
- Create: `tests/test_permissions.py`

**Step 1: Write the failing tests**

```python
"""Tests for permission checks."""
import os
from unittest.mock import patch, MagicMock

from shhhhhh.permissions import detect_terminal, check_access


def test_detect_terminal_ghostty():
    with patch.dict(os.environ, {"TERM_PROGRAM": "ghostty"}):
        assert detect_terminal() == "Ghostty"


def test_detect_terminal_iterm():
    with patch.dict(os.environ, {"TERM_PROGRAM": "iTerm.app"}):
        assert detect_terminal() == "iTerm2"


def test_detect_terminal_apple_terminal():
    with patch.dict(os.environ, {"TERM_PROGRAM": "Apple_Terminal"}):
        assert detect_terminal() == "Terminal"


def test_detect_terminal_unknown():
    with patch.dict(os.environ, {}, clear=True):
        assert detect_terminal() == "your terminal"


def test_check_access_succeeds(tmp_path):
    """No exception when file is readable."""
    plist = tmp_path / "test.plist"
    plist.write_bytes(b"test")
    check_access(plist)  # should not raise


def test_check_access_permission_error(tmp_path):
    """Returns False and prints guidance when permission denied."""
    plist = tmp_path / "test.plist"
    plist.write_bytes(b"test")
    plist.chmod(0o000)
    try:
        result = check_access(plist)
        assert result is False
    finally:
        plist.chmod(0o644)


def test_check_access_missing_file(tmp_path):
    """Returns False when plist doesn't exist."""
    plist = tmp_path / "nonexistent.plist"
    result = check_access(plist)
    assert result is False
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_permissions.py -v`
Expected: FAIL with ImportError (module doesn't exist yet)

**Step 3: Write the implementation**

```python
"""Full Disk Access permission check and setup guidance."""
import os
import subprocess
from pathlib import Path

from rich.console import Console
from rich.text import Text

console = Console()

SETTINGS_URL = "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles"

TERMINAL_NAMES = {
    "ghostty": "Ghostty",
    "iterm.app": "iTerm2",
    "apple_terminal": "Terminal",
    "warpterm": "Warp",
    "alacritty": "Alacritty",
    "kitty": "kitty",
    "hyper": "Hyper",
    "vscode": "VS Code",
    "tmux": "tmux",
}

# Same grayscale from display.py
GRAYS = [
    "color(250)",
    "color(248)",
    "color(245)",
    "color(243)",
    "color(240)",
    "color(238)",
]


def detect_terminal() -> str:
    """Detect the user's terminal app from environment."""
    term = os.environ.get("TERM_PROGRAM", "")
    return TERMINAL_NAMES.get(term.lower(), "your terminal")


def check_access(plist_path: Path) -> bool | None:
    """Check if the plist is readable. Returns None on success, False on failure."""
    try:
        with open(plist_path, "rb") as f:
            f.read(1)
        return None
    except (PermissionError, FileNotFoundError):
        _print_permission_guide()
        return False


def _print_permission_guide():
    """Print friendly setup instructions."""
    terminal = detect_terminal()

    console.print()
    console.print("  shh needs Full Disk Access", style=f"bold {GRAYS[0]}")
    console.print()
    console.print(
        f"  {terminal} needs permission to manage notification settings.",
        style=GRAYS[3],
    )
    console.print()
    console.print("  System Settings → Privacy & Security → Full Disk Access", style=GRAYS[2])
    console.print(f"  → Enable \"{terminal}\"", style=GRAYS[2])
    console.print()
    console.print("  Then restart your terminal and run shh again.", style=GRAYS[3])
    console.print()


def prompt_open_settings() -> None:
    """Ask the user if they want to open System Settings."""
    try:
        response = console.input(f"  Open System Settings? [Y/n] ")
        if response.strip().lower() in ("", "y", "yes"):
            subprocess.run(["open", SETTINGS_URL], capture_output=True)
            console.print()
            console.print("  Opened System Settings.", style=GRAYS[3])
            console.print()
    except (EOFError, KeyboardInterrupt):
        console.print()
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_permissions.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/shhhhhh/permissions.py tests/test_permissions.py
git commit -m "Add Full Disk Access permission check with setup guidance"
```

---

### Task 2: Wire permission check into CLI

**Files:**
- Modify: `src/shhhhhh/cli.py:45-48` (the `@click.group` and `main` function)

**Step 1: Write the failing test**

Add to `tests/test_cli.py`:

```python
def test_permission_error_shows_guidance(tmp_path):
    """Permission error shows friendly message instead of traceback."""
    plist = tmp_path / "test.plist"
    plist.write_bytes(b"test")
    plist.chmod(0o000)
    runner = CliRunner()
    try:
        with patch("shhhhhh.cli.PLIST_PATH", plist):
            result = runner.invoke(main, ["list"])
        assert result.exit_code == 0
        assert "Full Disk Access" in result.output
        assert "Traceback" not in result.output
    finally:
        plist.chmod(0o644)
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_cli.py::test_permission_error_shows_guidance -v`
Expected: FAIL (currently shows traceback)

**Step 3: Modify CLI to add permission gate**

In `cli.py`, update the `main` group:

```python
from shhhhhh.permissions import check_access, prompt_open_settings

@click.group(invoke_without_command=True)
@click.pass_context
def main(ctx):
    """shh — silence your mac, app by app."""
    if ctx.invoked_subcommand is not None:
        if check_access(PLIST_PATH) is False:
            prompt_open_settings()
            ctx.exit(0)
```

**Step 4: Run all tests**

Run: `pytest tests/ -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add src/shhhhhh/cli.py tests/test_cli.py
git commit -m "Wire permission check into CLI group callback"
```

---

### Task 3: Update README

**Files:**
- Modify: `README.md`

**Step 1: Add Setup section after Install**

```markdown
## Setup

`shh` needs **Full Disk Access** to manage notification settings.

1. Open **System Settings → Privacy & Security → Full Disk Access**
2. Enable your terminal app (Terminal, iTerm2, Ghostty, etc.)
3. Restart your terminal

If you forget this step, `shh` will remind you and offer to open System Settings for you.
```

**Step 2: Commit**

```bash
git add README.md
git commit -m "Add Full Disk Access setup instructions to README"
```

---

### Task 4: Manual verification

**Step 1: Test the happy path**

Run: `shh list`
Expected: Shows app list (if Full Disk Access is enabled)

**Step 2: Test the permission error path**

Temporarily revoke Full Disk Access for your terminal, then run:
Run: `shh list`
Expected: Friendly permission message, no traceback, offers to open System Settings
