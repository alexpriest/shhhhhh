"""Interactive TUI: arrow through every app, toggle settings, apply once."""
from pathlib import Path

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import DataTable, Input, Static

from shhhhhh.plist import (
    ALLOW_BIT,
    BADGES_BIT,
    CENTER_HIDE_BITS,
    LOCK_SCREEN_HIDE_BIT,
    SOUND_BIT,
    AppInfo,
    backup_plist,
    has_flag,
    set_center,
    set_flag,
    set_lock_screen,
    set_style,
    style_of,
    write_apps,
)

STYLE_ORDER = ("temporary", "persistent", "off")
HELP_TEXT = " ↑↓ move · space on/off · t style · b badge · s sound · n center · l lock · S/B all · a system entries · / filter · enter apply · ? help · q quit"
COLUMN_KEYS = ("app", "on", "style", "badges", "sound", "center", "lock")
TOGGLE_WIDTH = 8
HELP_LINES = [
    "Columns",
    "  On            notifications allowed at all (the master switch)",
    "  Style         temporary = a banner that slides away · persistent = an alert that stays",
    "                off = nothing appears on the desktop (badge, sound, and the rest still apply)",
    "  Badge         red count on the Dock icon",
    "  Sound         plays a sound",
    "  Notif Center  kept in Notification Center after it appears",
    "  Lock Screen   shown while the Mac is locked",
    "",
    "Keys",
    "  ↑ ↓  j k      move                      space  notifications on / off",
    "  t             cycle style               b  s   badge / sound",
    "  n  l          notif center / lock       S  B   sound / badge for every app",
    "  u             revert this row           /      filter by name (esc clears)",
    "  a             show / hide Apple system entries (daemons and agents, hidden by default)",
    "  enter         review and apply          esc    discard staged changes",
    "  q             quit                      ?      this help",
    "",
    "Nothing is written until you confirm on enter. Yellow = staged, not yet applied.",
]


def _mark(on: bool) -> str:
    return "✓" if on else "✗"


def describe_change(name: str, old: int, new: int) -> str:
    """One line for the confirm modal: what changed for this app."""
    parts = []
    if has_flag(old, ALLOW_BIT) != has_flag(new, ALLOW_BIT):
        parts.append(f"notifications {'on' if has_flag(new, ALLOW_BIT) else 'off'}")
    if style_of(old) != style_of(new):
        parts.append(f"style {style_of(old)} → {style_of(new)}")
    if has_flag(old, BADGES_BIT) != has_flag(new, BADGES_BIT):
        parts.append(f"badges {_mark(has_flag(old, BADGES_BIT))} → {_mark(has_flag(new, BADGES_BIT))}")
    if has_flag(old, SOUND_BIT) != has_flag(new, SOUND_BIT):
        parts.append(f"sound {_mark(has_flag(old, SOUND_BIT))} → {_mark(has_flag(new, SOUND_BIT))}")
    if _center(old) != _center(new):
        parts.append(f"notification center {_mark(_center(old))} → {_mark(_center(new))}")
    if _lock(old) != _lock(new):
        parts.append(f"lock screen {_mark(_lock(old))} → {_mark(_lock(new))}")
    return f"  {name:<30} {', '.join(parts)}"


def _center(flags: int) -> bool:
    return not any(has_flag(flags, b) for b in CENTER_HIDE_BITS)


def _lock(flags: int) -> bool:
    return not has_flag(flags, LOCK_SCREEN_HIDE_BIT)


class HelpScreen(ModalScreen[None]):
    """What the columns mean and what the keys do. Any key closes it."""

    DEFAULT_CSS = """
    HelpScreen {
        align: center middle;
    }
    #help-panel {
        width: auto;
        max-width: 100%;
        height: auto;
        padding: 1 3;
        border: round ansi_bright_black;
    }
    #help-text {
        width: auto;
        height: auto;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="help-panel"):
            yield Static("\n".join(HELP_LINES), id="help-text")

    def on_key(self, event) -> None:
        event.prevent_default()
        event.stop()
        self.dismiss(None)


class ConfirmScreen(ModalScreen[bool]):
    """Modal showing pending changes and asking for confirmation."""

    DEFAULT_CSS = """
    ConfirmScreen {
        align: center middle;
    }
    #confirm-panel {
        width: 80;
        max-height: 80%;
        background: $surface;
        padding: 1 2;
        border: thick $accent;
    }
    #confirm-title {
        text-style: bold;
        margin-bottom: 1;
    }
    #confirm-changes {
        margin-bottom: 1;
        max-height: 20;
        overflow-y: auto;
    }
    #confirm-hint {
        color: $text-muted;
    }
    """

    BINDINGS = [
        Binding("enter", "confirm", "Apply", show=True, priority=True),
        Binding("escape", "cancel", "Cancel", show=True, priority=True),
    ]

    def __init__(self, lines: list[str]) -> None:
        super().__init__()
        self.lines = lines

    def compose(self) -> ComposeResult:
        n = len(self.lines)
        with Vertical(id="confirm-panel"):
            yield Static(f"Apply {n} change{'s' if n != 1 else ''}?", id="confirm-title")
            yield Static("\n".join(self.lines), id="confirm-changes")
            yield Static("enter confirm · esc cancel", id="confirm-hint")

    def action_confirm(self) -> None:
        self.dismiss(True)

    def action_cancel(self) -> None:
        self.dismiss(False)


class ShhApp(App):
    """Interactive notification settings editor."""

    TITLE = "shh"
    CSS = """
    #header-bar {
        height: auto;
        padding: 1 2 0 2;
        color: $text-muted;
    }
    #summary {
        height: auto;
        padding: 1 2;
        color: $text;
    }
    #change-count {
        height: auto;
        padding: 0 2;
        color: $warning;
        display: none;
    }
    #change-count.visible {
        display: block;
    }
    #filter-input {
        display: none;
        margin: 0 2;
    }
    #filter-input.visible {
        display: block;
    }
    DataTable {
        height: 1fr;
        margin: 0 1;
        scrollbar-size-horizontal: 0;
        scrollbar-size-vertical: 1;
        scrollbar-background: ansi_default;
        scrollbar-background-hover: ansi_default;
        scrollbar-background-active: ansi_default;
        scrollbar-color: ansi_bright_black;
        scrollbar-color-hover: ansi_bright_black;
        scrollbar-color-active: ansi_bright_black;
    }
    DataTable > .datatable--header {
        background: ansi_default;
        color: ansi_default;
        text-style: bold;
    }
    DataTable > .datatable--header-hover,
    DataTable > .datatable--header-cursor {
        background: ansi_default;
        color: ansi_default;
        text-style: bold;
    }
    DataTable > .datatable--cursor {
        background: ansi_default;
        color: ansi_default;
        text-style: reverse;
    }
    DataTable > .datatable--hover {
        background: ansi_default;
    }
    #footer-help {
        height: auto;
        dock: bottom;
        padding: 0 2;
        color: $text-muted;
    }
    """

    BINDINGS = []

    def __init__(self, apps: list[AppInfo], plist_path: Path, backup_dir: Path) -> None:
        # ansi_color makes Textual draw with the terminal's own palette and
        # background, so the screen follows whatever theme the terminal is using.
        super().__init__(ansi_color=True)
        self.theme = "ansi-dark"
        self.apps = apps
        self.plist_path = plist_path
        self.backup_dir = backup_dir
        # Whole flag masks, keyed by plist index: what is on disk vs what the user has staged.
        self.original: dict[int, int] = {a.index: a.flags for a in apps}
        self.staged: dict[int, int] = dict(self.original)
        self.show_system = False
        self.filter_text = ""
        self.visible_apps: list[AppInfo] = self._compute_visible()
        self.applied = False
        self._quit_armed = False

    def _compute_visible(self) -> list[AppInfo]:
        apps = self.apps if self.show_system else [a for a in self.apps if not a.system]
        if self.filter_text:
            apps = [a for a in apps if self.filter_text in a.name.lower()]
        return apps

    # ---- layout -----------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Static("shh — silence your mac, app by app", id="header-bar")
        yield Static(self._summary_text(), id="summary")
        yield Static("", id="change-count")
        yield Input(placeholder="Filter apps...", id="filter-input")
        yield DataTable(id="app-table", cursor_type="row", header_height=2)
        yield Static(HELP_TEXT, id="footer-help")

    def on_mount(self) -> None:
        table = self.query_one("#app-table", DataTable)
        table.add_column(Text("\nApp"), key="app", width=32)
        table.add_column(Text("\nOn", justify="center"), key="on", width=TOGGLE_WIDTH)
        table.add_column(Text("\nStyle"), key="style", width=11)
        table.add_column(Text("\nBadge", justify="center"), key="badges", width=TOGGLE_WIDTH)
        table.add_column(Text("\nSound", justify="center"), key="sound", width=TOGGLE_WIDTH)
        table.add_column(Text("Notif\nCenter", justify="center"), key="center", width=TOGGLE_WIDTH)
        table.add_column(Text("Lock\nScreen", justify="center"), key="lock", width=TOGGLE_WIDTH)
        self._populate_table()
        table.focus()

    # ---- state ------------------------------------------------------------

    def _summary_text(self) -> str:
        shown = self.apps if self.show_system else [a for a in self.apps if not a.system]
        flags = [self.staged[a.index] for a in shown]
        on = sum(1 for f in flags if has_flag(f, ALLOW_BIT))
        with_sound = sum(1 for f in flags if has_flag(f, SOUND_BIT))
        with_badges = sum(1 for f in flags if has_flag(f, BADGES_BIT))
        hidden = len(self.apps) - len(shown)
        tail = (
            f"{hidden} system entries hidden · a to show" if hidden
            else ("showing system entries · a to hide" if self.show_system else "")
        )
        line = f"{len(shown)} apps · {on} on · {with_sound} with sound · {with_badges} with badges"
        return f"{line}   ·   {tail}" if tail else line

    def _pending_changes(self) -> list[tuple[AppInfo, int, int]]:
        return [
            (app, self.original[app.index], self.staged[app.index])
            for app in self.apps
            if self.original[app.index] != self.staged[app.index]
        ]

    def _stage(self, app: AppInfo, new_flags: int) -> None:
        self.staged[app.index] = new_flags
        self._quit_armed = False
        self._update_row(app)
        self._update_change_count()
        self._update_summary()

    def _update_change_count(self) -> None:
        count = len(self._pending_changes())
        widget = self.query_one("#change-count", Static)
        widget.update(f"  {count} change{'s' if count != 1 else ''} staged — enter to apply" if count else "")
        widget.set_class(bool(count), "visible")

    def _update_summary(self) -> None:
        self.query_one("#summary", Static).update(self._summary_text())

    # ---- table ------------------------------------------------------------

    def _cells(self, app: AppInfo) -> tuple[Text, ...]:
        old, new = self.original[app.index], self.staged[app.index]
        modified = old != new

        def check(bit: int) -> Text:
            on = has_flag(new, bit)
            changed = has_flag(old, bit) != on
            if changed:
                return Text("✓", style="bold yellow", justify="center") if on else Text("✗", style="yellow", justify="center")
            return Text("✓", style="green", justify="center") if on else Text("✗", style="dim", justify="center")

        allowed = has_flag(new, ALLOW_BIT)
        allow_changed = has_flag(old, ALLOW_BIT) != allowed
        on_cell = Text("●" if allowed else "○", style="bold yellow" if allow_changed else ("green" if allowed else "dim"), justify="center")
        style = style_of(new)
        style_cell = Text(style, style="bold yellow" if style_of(old) != style else ("" if style != "off" else "dim"))
        def shown(fn) -> Text:
            on = fn(new)
            if fn(old) != on:
                return Text("✓", style="bold yellow", justify="center") if on else Text("✗", style="yellow", justify="center")
            return Text("✓", style="green", justify="center") if on else Text("✗", style="dim", justify="center")

        return (
            Text(app.name, style="bold" if modified else ""),
            on_cell,
            style_cell,
            check(BADGES_BIT),
            check(SOUND_BIT),
            shown(_center),
            shown(_lock),
        )

    def _populate_table(self) -> None:
        table = self.query_one("#app-table", DataTable)
        table.clear()
        for app in self.visible_apps:
            table.add_row(*self._cells(app), key=str(app.index))

    def _update_row(self, app: AppInfo) -> None:
        if app not in self.visible_apps:
            return
        table = self.query_one("#app-table", DataTable)
        row_key = str(app.index)
        for column, value in zip(COLUMN_KEYS, self._cells(app)):
            table.update_cell(row_key, column, value)

    def _get_selected_app(self) -> AppInfo | None:
        table = self.query_one("#app-table", DataTable)
        if not self.visible_apps:
            return None
        try:
            row_key, _ = table.coordinate_to_cell_key(table.cursor_coordinate)
            idx = int(row_key.value)
            return next((a for a in self.visible_apps if a.index == idx), None)
        except Exception:
            return None

    def _filter_is_focused(self) -> bool:
        return self.query_one("#filter-input", Input).has_class("visible")

    # ---- keys -------------------------------------------------------------

    def on_key(self, event) -> None:
        """Handle key events, routing based on whether filter is active."""
        if isinstance(self.screen, ModalScreen):
            return
        key = event.key
        if self._filter_is_focused():
            if key == "escape":
                event.prevent_default()
                self._clear_filter()
            elif key == "enter":
                event.prevent_default()
                self.query_one("#filter-input", Input).remove_class("visible")
                self.query_one("#app-table", DataTable).focus()
            return
        table = self.query_one("#app-table", DataTable)
        actions = {
            "s": lambda: self._toggle_bit(SOUND_BIT),
            "b": lambda: self._toggle_bit(BADGES_BIT),
            "space": lambda: self._toggle_bit(ALLOW_BIT),
            "t": self._cycle_style,
            "n": self._toggle_center,
            "l": self._toggle_lock_screen,
            "S": lambda: self._set_all(SOUND_BIT),
            "B": lambda: self._set_all(BADGES_BIT),
            "u": self._revert_row,
            "a": self._toggle_system,
            "j": table.action_cursor_down,
            "down": table.action_cursor_down,
            "k": table.action_cursor_up,
            "up": table.action_cursor_up,
            "slash": self._open_filter,
            "enter": self._do_apply,
            "q": self._maybe_quit,
            "question_mark": lambda: self.push_screen(HelpScreen()),
            "escape": self._discard_or_quit,
        }
        action = actions.get(key)
        if action:
            event.prevent_default()
            action()

    def _toggle_bit(self, bit: int) -> None:
        app = self._get_selected_app()
        if app:
            flags = self.staged[app.index]
            self._stage(app, set_flag(flags, bit, not has_flag(flags, bit)))

    def _toggle_center(self) -> None:
        app = self._get_selected_app()
        if app:
            flags = self.staged[app.index]
            self._stage(app, set_center(flags, not _center(flags)))

    def _toggle_lock_screen(self) -> None:
        app = self._get_selected_app()
        if app:
            flags = self.staged[app.index]
            self._stage(app, set_lock_screen(flags, not _lock(flags)))

    def _cycle_style(self) -> None:
        app = self._get_selected_app()
        if app:
            current = style_of(self.staged[app.index])
            nxt = STYLE_ORDER[(STYLE_ORDER.index(current) + 1) % len(STYLE_ORDER)]
            self._stage(app, set_style(self.staged[app.index], nxt))

    def _set_all(self, bit: int) -> None:
        """If any app has the bit, clear it everywhere; otherwise set it everywhere."""
        any_on = any(has_flag(f, bit) for f in self.staged.values())
        for app in self.apps:
            self._stage(app, set_flag(self.staged[app.index], bit, not any_on))

    def _revert_row(self) -> None:
        app = self._get_selected_app()
        if app:
            self._stage(app, self.original[app.index])

    def _open_filter(self) -> None:
        filter_input = self.query_one("#filter-input", Input)
        filter_input.add_class("visible")
        filter_input.focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        self.filter_text = event.value.lower()
        self.visible_apps = self._compute_visible()
        self._populate_table()

    def _toggle_system(self) -> None:
        self.show_system = not self.show_system
        self.visible_apps = self._compute_visible()
        self._populate_table()
        self._update_summary()

    def _clear_filter(self) -> None:
        filter_input = self.query_one("#filter-input", Input)
        filter_input.value = ""
        filter_input.remove_class("visible")
        self.filter_text = ""
        self.visible_apps = self._compute_visible()
        self._populate_table()
        self.query_one("#app-table", DataTable).focus()

    def _discard_or_quit(self) -> None:
        if self.filter_text:
            self._clear_filter()
            return
        if self._pending_changes():
            self.staged = dict(self.original)
            self._populate_table()
            self._update_change_count()
            self._update_summary()
            self.notify("Discarded staged changes", severity="warning")
            return
        self.exit()

    def _do_apply(self) -> None:
        changes = self._pending_changes()
        if not changes:
            self.exit()
            return
        self.push_screen(ConfirmScreen([describe_change(a.name, o, n) for a, o, n in changes]), self._on_confirm)

    def _maybe_quit(self) -> None:
        if self._pending_changes() and not self._quit_armed:
            self._quit_armed = True
            self.notify("Staged changes will be lost — enter to apply, esc to discard, q again to quit", severity="warning")
            return
        self.exit()

    def _on_confirm(self, confirmed: bool | None) -> None:
        if not confirmed:
            return
        changes = self._pending_changes()
        if not changes:
            self.exit()
            return
        backup_plist(self.plist_path, self.backup_dir)
        write_apps(self.plist_path, {a.index: new for a, _, new in changes})
        self.applied = True
        self.exit()
