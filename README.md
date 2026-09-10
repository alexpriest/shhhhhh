# shh

Silence your Mac, app by app.

A CLI tool for batch-managing macOS notification settings — an interactive screen to arrow through every app and toggle it, plus one-line commands for on/off, alert style, sound, and badges.

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
shh                          # interactive: arrow through apps, toggle, apply
shh list                     # show all apps + settings (grouped; --flat for A–Z, --system to include Apple daemons)
shh sound off --all          # mute everything
shh sound on Mail Messages   # unmute specific apps
shh badges off --all         # remove all badge icons
shh allow off Slack          # turn an app's notifications off entirely
shh style persistent Mail    # temporary (banner), persistent (stays), or off
shh center off --all         # hide from Notification Center
shh lockscreen off Messages  # hide on the Lock Screen
shh uninstall "Book Tracker" # app + Library leftovers to the Trash (--dry-run to just look)
shh sound off --category media
shh undo                     # restore previous settings
```

### Interactive keys

| Key | Does |
|---|---|
| `↑` `↓` / `k` `j` | move |
| `space` | notifications on / off |
| `t` | cycle alert style: temporary → persistent → off |
| `b` | badge on / off |
| `s` | sound on / off |
| `n` | show in Notification Center on / off |
| `l` | show on Lock Screen on / off |
| `S` / `B` | sound / badges for every app (mutes all if any is on, else unmutes all) |
| `/` | filter by name (`esc` clears) |
| `a` | show / hide Apple system entries (daemons and agents; hidden by default) |
| `o` | show / hide a Last used column (Spotlight's last-opened date) to spot apps you never open |
| `U` | uninstall the app under the cursor: the .app plus its Library leftovers move to the Trash after a review; Apple software and running apps are refused |
| `u` | revert the current row |
| `enter` | review and apply all staged changes (one backup, one write) |
| `esc` | discard staged changes |
| `q` | quit (asks once if changes are staged) |

Nothing is written until you confirm on `enter`; changed cells show in yellow.

"Temporary" and "Persistent" are Apple's names for the two alert styles (banners that slide away vs. alerts that stay until dismissed); "off" unchecks Desktop.

## How it works

Uninstall sweeps the way Hazel's App Sweep does: the `.app`, then `~/Library/{Application Support, Caches, Preferences, Saved Application State, HTTPStorages, Cookies, WebKit, Logs, Application Scripts, LaunchAgents, Containers, Group Containers}` entries keyed by the bundle id (and Application Support / Caches / Logs folders named exactly after the app). Everything goes to the Trash via `/usr/bin/trash`, never deleted outright, and the app's notification entry is dropped from the plist.

`shh` reads and writes macOS notification preferences directly from the `usernoted` plist, then restarts the daemon to apply changes. A backup is automatically created before every change.

Bits it touches in each app's `flags`: 1 badge, 2 sound, 3 temporary, 4 persistent, 25 allow, and the inverted "hide" bits 12 (Lock Screen) and 0+8 (Notification Center). Everything else is left exactly as found.

## Requirements

- macOS 15+ (Sequoia / Tahoe)
- Python 3.11+

## License

MIT
