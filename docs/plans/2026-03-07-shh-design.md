# shh (shhhhhh.sh) — Design Document

## Overview

A Python CLI tool for batch-managing macOS notification settings. Reads and writes the `usernoted` plist directly, letting you toggle sound and badges for all apps or specific ones in a single command.

- **PyPI package**: `shhhhhh`
- **CLI command**: `shh`
- **Domain**: `shhhhhh.sh`

## Commands

```
shh list                     # show all apps + sound/badge status
shh sound off --all          # mute all apps
shh sound on --all           # unmute all apps
shh sound off Slack Zoom     # mute specific apps (fuzzy match)
shh sound on Mail Messages   # unmute specific apps
shh badges off --all         # remove all badge icons
shh badges on Mail Messages  # re-enable badges for specific apps
shh undo                     # restore most recent backup
```

## Branding

### Logo
Box-drawing chunky "SHH" wordmark with top-to-bottom grayscale gradient (bright to dim, like sound fading out). Uses 256-color ANSI codes, one shade per line.

```
 ███████╗██╗  ██╗██╗  ██╗
 ██╔════╝██║  ██║██║  ██║
 ███████╗███████║███████║
 ╚════██║██╔══██║██╔══██║
 ███████║██║  ██║██║  ██║
 ╚══════╝╚═╝  ╚═╝╚═╝  ╚═╝
```

### Tagline
Dim text below logo: `silence your mac, app by app`

### Colors
Grayscale palette throughout. Green checkmarks, dim crosses for status.

## Data Layer

### Source file
```
~/Library/Group Containers/group.com.apple.usernoted/Library/Preferences/group.com.apple.usernoted.plist
```

### Flags bitmask
- Bit 1 (value 2): Badge app icon
- Bit 2 (value 4): Play sound for notifications

### App name resolution
1. Extract from `path` field (e.g. `/Applications/Slack.app` -> `Slack`)
2. Fall back to `bundle-id` if no path

### Fuzzy matching
Case-insensitive substring match against friendly app names. If ambiguous, show matches and ask user to be more specific.

### System apps
Skip entries where `bundle-id` starts with `_SYSTEM_CENTER_:`.

### Write flow
1. Read current plist
2. Modify flags bitmask for targeted apps
3. Write plist back
4. Restart `usernoted` daemon via `killall usernoted`

## Output Examples

### `shh list`

```
 [gradient logo]

 silence your mac, app by app

 47 apps · 43 with sound · 45 with badges

 App                     Sound   Badges
 ────────────────────────────────────────
 Calendar                  ✓       ✓
 Chrome                    ✓       ✓
 FaceTime                  ✓       ✓
 Linear                    ✓       ✓
 Mail                      ✓       ✓
 Messages                  ✗       ✗
 Slack                     ✗       ✓
 ...
```

### `shh sound off --all`

```
 [gradient logo]

 Muted 43 apps

 To undo: shh sound on --all
```

## Safety

- Backup plist to `~/.shh/backup-<timestamp>.plist` before first write
- `shh undo` restores most recent backup
- Confirm before `--all` operations (skip with `--yes` / `-y`)

## Tech Stack

- Python 3.11+
- `rich` — colored output, tables, status indicators
- `plistlib` (stdlib) — read/write plist
- `click` — CLI argument parsing
- `subprocess` — restart usernoted after changes

## Project Structure

```
~/Code/tools/shhhhhh/
├── README.md
├── pyproject.toml
├── src/
│   └── shhhhhh/
│       ├── __init__.py
│       ├── cli.py          # click commands + banner
│       ├── plist.py         # read/write usernoted plist
│       └── display.py       # rich table + formatting
```

## Future (not v1)

- SwiftUI wrapper app (Option C from brainstorming)
- Additional settings: banners/alert type, lock screen, previews
- `shh profile save/load` — save/restore named configurations
- Homebrew formula
