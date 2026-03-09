# Permission Check + Setup Flow

## Problem

`shh` requires Full Disk Access to read/write the macOS notification plist. Without it, users get a raw Python traceback on first run. We need a friendly permission gate that guides users through setup.

## Design

### New module: `permissions.py`

- `detect_terminal()` — reads `$TERM_PROGRAM` to identify the user's terminal (Ghostty, iTerm2, Terminal, etc.)
- `check_access()` — tries to open the plist. On `PermissionError`, shows a styled Rich message with setup instructions and offers to open System Settings directly.

### CLI integration

`check_access()` runs as a callback on the `@click.group()` — single gate before any subcommand.

### Error output

Styled Rich output with:
- Clear headline explaining what's needed
- Detected terminal name so the user knows exactly what to enable
- Step-by-step path: System Settings → Privacy & Security → Full Disk Access
- Prompt to open System Settings automatically via `open "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles"`
- Instruction to restart terminal after enabling

### README update

Add Setup section after Install documenting the Full Disk Access requirement.

### Out of scope

- No pip post-install hooks (deprecated/unreliable)
- No programmatic permission granting (macOS doesn't allow it)
