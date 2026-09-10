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

Verified against System Settings on macOS 26 on 2026-09-10 (Claude vs CleanShot X differ only in bit 25 and read "Badges, Desktop" vs "Off"; Bartleby with bit 3 reads Temporary; App Store with bit 4 still counts as Desktop).

Confirmed by clicking the three checkboxes on Bartleby's page and re-reading the plist (same day):

- Lock Screen unchecked → bit 12 set (inverted, as the old ncprefs docs say) — `l` / `shh lockscreen`
- Notification Center unchecked → bits 0 and 8 set together; bit 13 did not move — `n` / `shh center` writes both
- Desktop unchecked → bit 3 cleared and bit 6 set. Bit 6 looks like "the style was Temporary" memory so re-checking restores it (Beeper carries 3+6 and shows Desktop checked). `shh` never writes bit 6; `style off` just clears 3/4.

The terminal palette: the app runs with `ansi_color=True` and the `ansi-dark` theme, so every colour is an ANSI name and the terminal's own theme (light or dark) shows through. Component CSS on the DataTable zeroes the header/cursor backgrounds and hides the horizontal scrollbar for the same reason.

## Known gaps (v2)

- Ambiguous match warning: if you type `shh sound off Ma` and it matches both Mail and Maps, it silently applies to both. Design doc says it should show matches and ask the user to be specific.
- No `--version` flag
- No badges-specific CLI tests (shares code path with sound via factory pattern, low risk)
