"""Full Disk Access permission check and setup guidance."""
import os
import subprocess
from pathlib import Path

from shhhhhh.display import console, GRAYS

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


def detect_terminal() -> str:
    """Detect the user's terminal app from environment."""
    term = os.environ.get("TERM_PROGRAM", "")
    return TERMINAL_NAMES.get(term.lower(), "your terminal")


def check_access(plist_path: Path) -> bool:
    """Check if the plist is readable. Returns True on success, False on failure."""
    try:
        with open(plist_path, "rb") as f:
            f.read(1)
        return True
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
        response = console.input("  Open System Settings? [Y/n] ")
        if response.strip().lower() in ("", "y", "yes"):
            subprocess.run(["open", SETTINGS_URL], capture_output=True)
            console.print()
            console.print("  Opened System Settings.", style=GRAYS[3])
            console.print()
    except (EOFError, KeyboardInterrupt):
        console.print()
