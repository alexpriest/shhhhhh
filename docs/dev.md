# Development

## Setup

Requires Python 3.11+. The system Python's pip is too old for editable installs, so use a venv:

```bash
cd ~/Code/projects/shhhhhh
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e .
pip install pytest pytest-asyncio
```

## Running

```bash
shh                          # interactive screen (Textual)
shh list                     # show all apps + settings
shh sound off --all          # mute everything
shh sound on Mail Messages   # unmute specific apps
shh badges off --all         # remove all badge icons
shh undo                     # restore previous settings
```

## Tests

```bash
python3 -m pytest tests/ -v
```

78 tests across 6 files: plist reader, plist writer, permissions, categories, CLI commands, and the interactive screen (driven headlessly with Textual's pilot — no TTY needed; needs `pytest-asyncio`).

## Architecture

Three modules:

- `src/shhhhhh/plist.py` — reads/writes the macOS `usernoted` plist, bitmask manipulation, backup/restore
- `src/shhhhhh/display.py` — gradient logo, rich tables, result messages
- `src/shhhhhh/cli.py` — click commands wiring plist + display together; bare `shh` launches the TUI
- `src/shhhhhh/interactive.py` — Textual app: stages whole flag masks in `staged`, writes once after the confirm modal
- `src/shhhhhh/categories.py` — app category detection for grouped output and `--category`

## How it works

The tool reads `~/Library/Group Containers/group.com.apple.usernoted/Library/Preferences/group.com.apple.usernoted.plist`, which stores per-app notification flags as a bitmask:

- Bit 1 (value 2): badges
- Bit 2 (value 4): sound
- Bit 3 (value 8): alert style Temporary
- Bit 4 (value 16): alert style Persistent (both clear = Desktop unchecked)
- Bit 25: allow notifications (clearing it leaves every other bit in place, as System Settings does)

Verified against System Settings on macOS 26 on 2026-09-10 (Claude vs CleanShot X differ only in bit 25 and read "Badges, Desktop" vs "Off"; Bartleby with bit 3 reads Temporary; App Store with bit 4 still counts as Desktop). Documented but unverified here, so not on any write path: bit 12 lock screen (inverted), bit 13 Notification Center.

After modifying flags, it restarts `usernoted` via `killall usernoted` to apply changes. A timestamped backup is saved to `~/.shh/` before every write.

## Known gaps (v2)

- Ambiguous match warning: if you type `shh sound off Ma` and it matches both Mail and Maps, it silently applies to both. Design doc says it should show matches and ask the user to be specific.
- No `--version` flag
- No badges-specific CLI tests (shares code path with sound via factory pattern, low risk)
