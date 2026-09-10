"""Interactive TUI: arrow through every app, toggle settings, apply once."""
from pathlib import Path

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import DataTable, Input, Static

from shhhhhh.uninstall import (
    UninstallError,
    UninstallPlan,
    age_label,
    execute as execute_uninstall,
    human_size,
    last_used_many,
    plan_uninstall,
    remove_from_plist,
)
from shhhhhh.plist import (
    ALLOW_BIT,
    read_apps,
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
HELP_TEXT = " ↑↓ move · x mark · space on/off · t style · b badge · s sound · n center · l lock · S/B all · a system · o last used · U uninstall · / filter · enter apply · ? help · q quit"
COLUMN_KEYS = ("sel", "app", "on", "style", "badges", "sound", "center", "lock")
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
    "  x             mark this row (and move down); X marks or unmarks everything visible",
    "                while rows are marked, every action below applies to all of them",
    "  ↑ ↓  j k      move                      space  notifications on / off",
    "  t             cycle style               b  s   badge / sound",
    "  n  l          notif center / lock       S  B   sound / badge for every app",
    "  u             revert this row           /      filter by name (esc clears)",
    "  a             show / hide Apple system entries (daemons and agents, hidden by default)",
    "  o             show / hide a Last used column: newest of Screen Time usage, Spotlight, and the",
    "                app's own Library writes; 'running' if it is open now, 'no trace' if nothing was found",
    "  U             uninstall the app under the cursor (or every marked app): the .app plus its Library",
    "                leftovers go to the Trash after a review; f in the review keeps the Library files",
    "                (Apple software and running apps are refused; a vanished .app just forgets its entry)",
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


class UninstallScreen(ModalScreen[tuple[bool, bool]]):
    """Show what an uninstall will move to the Trash and ask once.
    Dismisses with (confirmed, keep_files)."""

    DEFAULT_CSS = """
    UninstallScreen {
        align: center middle;
    }
    #uninstall-panel {
        width: auto;
        max-width: 100%;
        height: auto;
        max-height: 90%;
        padding: 1 3;
        border: round ansi_red;
    }
    #uninstall-title {
        text-style: bold;
        margin-bottom: 1;
    }
    #uninstall-paths {
        width: auto;
        height: auto;
        max-height: 24;
        overflow-y: auto;
        margin-bottom: 1;
    }
    #uninstall-admin {
        color: ansi_yellow;
        margin-bottom: 1;
    }
    #uninstall-hint {
        color: $text-muted;
    }
    """

    BINDINGS = [
        Binding("enter", "confirm", "Uninstall", show=True, priority=True),
        Binding("escape", "cancel", "Cancel", show=True, priority=True),
        Binding("f", "toggle_files", "Keep files", show=True, priority=True),
    ]

    def __init__(self, plans: list[UninstallPlan], skipped: list[tuple[str, str]] = ()) -> None:
        super().__init__()
        self.plans = plans
        self.skipped = list(skipped)
        self.keep_files = False

    def compose(self) -> ComposeResult:
        with Vertical(id="uninstall-panel"):
            yield Static(self._title(), id="uninstall-title")
            yield Static(self._body(), id="uninstall-paths")
            if any(p.needs_admin for p in self.plans):
                yield Static(
                    "Owned by root (an App Store install), so the Finder will do the move and ask for your password.",
                    id="uninstall-admin",
                )
            yield Static(self._hint(), id="uninstall-hint")

    def _title(self) -> str:
        names = ", ".join(p.app.name for p in self.plans)
        items = sum(len(p.targets) for p in self.plans)
        size = human_size(sum(p.size for p in self.plans))
        entries = "its notification entry" if len(self.plans) == 1 else "their notification entries"
        if items == 0:
            return f"Forget {entries} for {names}? Nothing is left on disk to remove."
        return f"Uninstall {names}? Moves {items} item{'s' if items != 1 else ''} ({size}) to the Trash and forgets {entries}."

    def _body(self) -> str:
        home = str(Path.home())
        lines = []
        for plan in self.plans:
            if len(self.plans) > 1 or plan.gone:
                note = " — the .app is already gone" if plan.gone else ""
                lines.append(f"{plan.app.name}{note}")
            for path in plan.targets:
                lines.append(f"  {str(path).replace(home, '~')}")
            if self.keep_files and not plan.gone and len(plan.paths) > 1:
                lines.append(f"  (keeping {len(plan.paths) - 1} Library items)")
        for name, why in self.skipped:
            lines.append(f"{name} — skipped: {why}")
        return "\n".join(lines)

    def _hint(self) -> str:
        files = "kept (app only)" if self.keep_files else "trashed too"
        return f"enter uninstall · esc cancel · f Library files: {files} · everything lands in the Trash, so it can be put back"

    def action_toggle_files(self) -> None:
        self.keep_files = not self.keep_files
        for plan in self.plans:
            plan.keep_files = self.keep_files
        self.query_one("#uninstall-title", Static).update(self._title())
        self.query_one("#uninstall-paths", Static).update(self._body())
        self.query_one("#uninstall-hint", Static).update(self._hint())

    def action_confirm(self) -> None:
        self.dismiss((True, self.keep_files))

    def action_cancel(self) -> None:
        self.dismiss((False, self.keep_files))


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
    Toast {
        background: ansi_default;
        color: ansi_default;
        border-left: wide ansi_bright_black;
        padding: 0 1;
    }
    Toast.-information { border-left: wide ansi_green; }
    Toast.-warning { border-left: wide ansi_yellow; }
    Toast.-error { border-left: wide ansi_red; }
    Toast .toast--title { color: ansi_default; text-style: bold; }
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
        self.selected: set[int] = set()   # plist indices of marked rows
        self.show_system = False
        self.show_last_used = False
        self.last_used: dict[str, str] = {}   # bundle id -> "3d ago"
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
        table.add_column(Text(""), key="sel", width=2)
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
        if self.selected:
            line = f"{len(self.selected)} marked · " + line
        return f"{line}, {tail}" if tail else line

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

        cells = [
            Text("●" if app.index in self.selected else "", style="ansi_blue"),
            Text(app.name, style="bold" if modified else ""),
            on_cell,
            style_cell,
            check(BADGES_BIT),
            check(SOUND_BIT),
            shown(_center),
            shown(_lock),
        ]
        if self.show_last_used:
            label = self.last_used.get(app.bundle_id, "")
            cells.append(Text(label, style="dim" if label in ("no trace", "") else ("green" if label == "running" else ""), justify="right"))
        return tuple(cells)

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
        keys = COLUMN_KEYS + (("last_used",) if self.show_last_used else ())
        for column, value in zip(keys, self._cells(app)):
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
            "x": self._mark_row,
            "X": self._mark_all_visible,
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
            "o": self._toggle_last_used,
            "U": self._uninstall,
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

    def _targets(self) -> list[AppInfo]:
        """Marked rows if any are marked, else the row under the cursor."""
        if self.selected:
            return [a for a in self.apps if a.index in self.selected]
        app = self._get_selected_app()
        return [app] if app else []

    def _apply(self, getter, setter) -> None:
        """Toggle a boolean setting across the targets: a single row flips; a set
        turns on if any is off, otherwise off."""
        targets = self._targets()
        if not targets:
            return
        if len(targets) == 1:
            flags = self.staged[targets[0].index]
            self._stage(targets[0], setter(flags, not getter(flags)))
            return
        turn_on = any(not getter(self.staged[a.index]) for a in targets)
        for app in targets:
            self._stage(app, setter(self.staged[app.index], turn_on))

    def _toggle_bit(self, bit: int) -> None:
        self._apply(lambda f: has_flag(f, bit), lambda f, on: set_flag(f, bit, on))

    def _mark_row(self) -> None:
        app = self._get_selected_app()
        if not app:
            return
        self.selected.symmetric_difference_update({app.index})
        self._update_row(app)
        self._update_summary()
        self.query_one("#app-table", DataTable).action_cursor_down()

    def _mark_all_visible(self) -> None:
        visible = {a.index for a in self.visible_apps}
        if visible <= self.selected:
            self.selected -= visible
        else:
            self.selected |= visible
        self._populate_table()
        self._update_summary()

    def _clear_marks(self) -> None:
        self.selected.clear()
        self._populate_table()
        self._update_summary()

    def _toggle_center(self) -> None:
        self._apply(_center, set_center)

    def _toggle_lock_screen(self) -> None:
        self._apply(_lock, set_lock_screen)

    def _cycle_style(self) -> None:
        targets = self._targets()
        cursor = self._get_selected_app() or (targets[0] if targets else None)
        if not targets or cursor is None:
            return
        current = style_of(self.staged[cursor.index])
        nxt = STYLE_ORDER[(STYLE_ORDER.index(current) + 1) % len(STYLE_ORDER)]
        for app in targets:
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

    def _toggle_last_used(self) -> None:
        table = self.query_one("#app-table", DataTable)
        self.show_last_used = not self.show_last_used
        if self.show_last_used:
            missing = [a for a in self.apps if a.bundle_id not in self.last_used]
            if missing:
                results = last_used_many([a for a in missing if a.app_path.endswith(".app")])
                for app in missing:
                    if app.bundle_id in results:
                        when, running = results[app.bundle_id]
                        self.last_used[app.bundle_id] = age_label(when, running=running)
                    else:
                        self.last_used[app.bundle_id] = ""
            table.add_column(Text("Last\nused", justify="right"), key="last_used", width=10)
        else:
            table.remove_column("last_used")
        self._populate_table()

    def _uninstall(self) -> None:
        targets = self._targets()
        if not targets:
            return
        plans, skipped = [], []
        for app in targets:
            plan = plan_uninstall(app)
            if plan.blocked:
                skipped.append((app.name, plan.blocked))
            elif plan.running:
                skipped.append((app.name, "running — quit it first"))
            else:
                plans.append(plan)
        if not plans:
            for name, why in skipped:
                self.notify(f"{name}: {why}", severity="warning")
            return
        self.push_screen(UninstallScreen(plans, skipped), lambda result: self._on_uninstall_confirmed(plans, result))

    def _on_uninstall_confirmed(self, plans: list[UninstallPlan], result: tuple[bool, bool] | None) -> None:
        if not result or not result[0]:
            return
        done, moved_total = [], 0
        for plan in plans:
            try:
                moved_total += len(execute_uninstall(plan))
            except UninstallError as exc:
                kept = f" {len(exc.moved)} items already in the Trash; the rest untouched." if exc.moved else ""
                self.notify(f"Uninstall stopped — {exc}.{kept}", severity="error", timeout=12)
                break
            except Exception as exc:  # never take the screen down over an uninstall
                self.notify(f"Uninstall stopped: {exc}", severity="error", timeout=12)
                break
            done.append(plan)
        if not done:
            return
        backup_plist(self.plist_path, self.backup_dir)
        for plan in done[:-1]:
            remove_from_plist(self.plist_path, plan.app.bundle_id, restart=False)
        remove_from_plist(self.plist_path, done[-1].app.bundle_id)
        self.selected.clear()
        self._reload_apps()
        names = ", ".join(p.app.name for p in done)
        what = f"{moved_total} items to the Trash" if moved_total else "entry forgotten"
        self.notify(f"{names}: {what}")

    def _reload_apps(self) -> None:
        """Re-read the plist after an entry was removed; keep staged edits by bundle id."""
        staged_by_id = {a.bundle_id: self.staged[a.index] for a in self.apps}
        selected_ids = {a.bundle_id for a in self.apps if a.index in self.selected}
        self.apps = read_apps(self.plist_path)
        self.original = {a.index: a.flags for a in self.apps}
        self.staged = {a.index: staged_by_id.get(a.bundle_id, a.flags) for a in self.apps}
        self.selected = {a.index for a in self.apps if a.bundle_id in selected_ids}
        self.visible_apps = self._compute_visible()
        self._populate_table()
        self._update_change_count()
        self._update_summary()

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
        if self.selected:
            self._clear_marks()
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
