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
