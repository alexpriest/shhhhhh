# shh

Silence your Mac, app by app.

A CLI tool for batch-managing macOS notification settings — toggle sound and badges for all apps or specific ones in a single command.

## Install

```bash
brew install alexpriest/tap/shh
```

Or with pip:

```bash
pip install shhhhhh
```

## Setup

`shh` needs **Full Disk Access** to manage notification settings.

1. Open **System Settings → Privacy & Security → Full Disk Access**
2. Enable your terminal app (Terminal, iTerm2, Ghostty, etc.)
3. Restart your terminal

If you skip this step, `shh` will guide you through it on first run.

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
