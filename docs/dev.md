# Development

## Setup

Requires Python 3.11+. The system Python's pip is too old for editable installs, so use a venv:

```bash
cd ~/Code/tools/shhhhhh
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e .
pip install pytest
```

## Running

```bash
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

18 tests across 3 files: plist reader, plist writer, CLI commands.

## Architecture

Three modules:

- `src/shhhhhh/plist.py` — reads/writes the macOS `usernoted` plist, bitmask manipulation, backup/restore
- `src/shhhhhh/display.py` — gradient logo, rich tables, result messages
- `src/shhhhhh/cli.py` — click commands wiring plist + display together

## How it works

The tool reads `~/Library/Group Containers/group.com.apple.usernoted/Library/Preferences/group.com.apple.usernoted.plist`, which stores per-app notification flags as a bitmask:

- Bit 1 (value 2): badges
- Bit 2 (value 4): sound

After modifying flags, it restarts `usernoted` via `killall usernoted` to apply changes. A timestamped backup is saved to `~/.shh/` before every write.

## Known gaps (v2)

- Ambiguous match warning: if you type `shh sound off Ma` and it matches both Mail and Maps, it silently applies to both. Design doc says it should show matches and ask the user to be specific.
- No `--version` flag
- No badges-specific CLI tests (shares code path with sound via factory pattern, low risk)
