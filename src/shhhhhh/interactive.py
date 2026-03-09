"""Interactive TUI for browsing and toggling notification settings."""
from pathlib import Path

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import DataTable, Input, Static

from shhhhhh.plist import (
    AppInfo,
    SOUND_BIT,
    BADGES_BIT,
    set_flag,
    backup_plist,
    write_apps,
)


class ConfirmScreen(ModalScreen[bool]):
    """Modal showing pending changes and asking for confirmation."""

    DEFAULT_CSS = """
    ConfirmScreen {
        align: center middle;
    }
    #confirm-panel {
        width: 60;
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

    def __init__(self, changes: list[dict]) -> None:
        super().__init__()
        self.changes = changes

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-panel"):
            yield Static(f"Apply {len(self.changes)} change{'s' if len(self.changes) != 1 else ''}?", id="confirm-title")
            lines = []
            for c in self.changes:
                parts = []
                if c["sound_changed"]:
                    old = "✓" if c["orig_sound"] else "✗"
                    new = "✓" if c["new_sound"] else "✗"
                    parts.append(f"sound {old} → {new}")
                if c["badges_changed"]:
                    old = "✓" if c["orig_badges"] else "✗"
                    new = "✓" if c["new_badges"] else "✗"
                    parts.append(f"badges {old} → {new}")
                lines.append(f"  {c['name']:<30} {', '.join(parts)}")
            yield Static("\n".join(lines), id="confirm-changes")
            yield Static("enter confirm · esc cancel", id="confirm-hint")

    def action_confirm(self) -> None:
        self.dismiss(True)

    def action_cancel(self) -> None:
        self.dismiss(False)


class ShhApp(App):
    """Interactive notification settings editor."""

    TITLE = "shh"
    CSS = """
    Screen {
        background: $surface;
    }
    #header-bar {
        height: auto;
        padding: 1 2;
        color: $text-muted;
    }
    #summary {
        height: auto;
        padding: 0 2;
        color: $text;
    }
    #change-count {
        height: auto;
        padding: 0 2;
        color: $warning;
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
    }
    #footer-help {
        height: auto;
        dock: bottom;
        padding: 0 2;
        color: $text-muted;
        background: $surface;
    }
    """

    BINDINGS = []

    def __init__(
        self,
        apps: list[AppInfo],
        plist_path: Path,
        backup_dir: Path,
    ) -> None:
        super().__init__()
        self.apps = apps
        self.plist_path = plist_path
        self.backup_dir = backup_dir
        # Track original and staged state: {app.index: (sound, badges)}
        self.original: dict[int, tuple[bool, bool]] = {
            a.index: (a.sound, a.badges) for a in apps
        }
        self.staged: dict[int, tuple[bool, bool]] = dict(self.original)
        # Map visible table row indices to app list indices
        self.visible_apps: list[AppInfo] = list(apps)
        self.applied = False
        self.filter_text = ""

    def compose(self) -> ComposeResult:
        yield Static("shh — silence your mac, app by app", id="header-bar")
        yield Static(self._summary_text(), id="summary")
        yield Static("", id="change-count")
        yield Input(placeholder="Filter apps...", id="filter-input")
        yield DataTable(id="app-table", cursor_type="row")
        yield Static(self._help_text(), id="footer-help")

    def on_mount(self) -> None:
        table = self.query_one("#app-table", DataTable)
        table.add_column("App", key="app", width=32)
        table.add_column("Sound", key="sound", width=8)
        table.add_column("Badges", key="badges", width=8)
        self._populate_table()
        table.focus()

    def _summary_text(self) -> str:
        total = len(self.apps)
        with_sound = sum(1 for a in self.apps if self.staged[a.index][0])
        with_badges = sum(1 for a in self.apps if self.staged[a.index][1])
        return f"  {total} apps · {with_sound} with sound · {with_badges} with badges"

    def _help_text(self) -> str:
        return " ↑↓/jk navigate · s sound · b badges · / filter · enter apply · q quit"

    def _pending_changes(self) -> list[dict]:
        changes = []
        for app in self.apps:
            orig = self.original[app.index]
            staged = self.staged[app.index]
            if orig != staged:
                changes.append({
                    "name": app.name,
                    "index": app.index,
                    "flags": app.flags,
                    "orig_sound": orig[0],
                    "orig_badges": orig[1],
                    "new_sound": staged[0],
                    "new_badges": staged[1],
                    "sound_changed": orig[0] != staged[0],
                    "badges_changed": orig[1] != staged[1],
                })
        return changes

    def _update_change_count(self) -> None:
        count = len(self._pending_changes())
        widget = self.query_one("#change-count", Static)
        if count:
            widget.update(f"  {count} change{'s' if count != 1 else ''} staged")
        else:
            widget.update("")

    def _update_summary(self) -> None:
        self.query_one("#summary", Static).update(self._summary_text())

    def _cell_text(self, enabled: bool, is_modified: bool) -> Text:
        if is_modified:
            if enabled:
                return Text("✓", style="bold yellow")
            else:
                return Text("✗", style="yellow")
        else:
            if enabled:
                return Text("✓", style="green")
            else:
                return Text("✗", style="dim")

    def _populate_table(self) -> None:
        table = self.query_one("#app-table", DataTable)
        table.clear()
        for app in self.visible_apps:
            sound, badges = self.staged[app.index]
            orig_sound, orig_badges = self.original[app.index]
            sound_modified = sound != orig_sound
            badges_modified = badges != orig_badges
            name_text = Text(app.name, style="bold" if (sound_modified or badges_modified) else "")
            table.add_row(
                name_text,
                self._cell_text(sound, sound_modified),
                self._cell_text(badges, badges_modified),
                key=str(app.index),
            )

    def _get_selected_app(self) -> AppInfo | None:
        table = self.query_one("#app-table", DataTable)
        if not self.visible_apps:
            return None
        try:
            row_key, _ = table.coordinate_to_cell_key(table.cursor_coordinate)
            idx = int(row_key.value)
            for app in self.visible_apps:
                if app.index == idx:
                    return app
            return None
        except Exception:
            return None

    def _update_row(self, app: AppInfo) -> None:
        table = self.query_one("#app-table", DataTable)
        sound, badges = self.staged[app.index]
        orig_sound, orig_badges = self.original[app.index]
        sound_modified = sound != orig_sound
        badges_modified = badges != orig_badges
        row_key = str(app.index)
        name_text = Text(app.name, style="bold" if (sound_modified or badges_modified) else "")
        table.update_cell(row_key, "app", name_text)
        table.update_cell(row_key, "sound", self._cell_text(sound, sound_modified))
        table.update_cell(row_key, "badges", self._cell_text(badges, badges_modified))

    def _filter_is_focused(self) -> bool:
        return self.query_one("#filter-input", Input).has_class("visible")

    def on_key(self, event) -> None:
        """Handle key events, routing based on whether filter is active."""
        # Don't intercept keys when a modal screen is active
        if isinstance(self.screen, ModalScreen):
            return
        key = event.key
        if self._filter_is_focused():
            if key == "escape":
                event.prevent_default()
                self._clear_or_quit()
            return
        if key == "s":
            event.prevent_default()
            self._do_toggle_sound()
        elif key == "b":
            event.prevent_default()
            self._do_toggle_badges()
        elif key in ("j", "down"):
            event.prevent_default()
            self.query_one("#app-table", DataTable).action_cursor_down()
        elif key in ("k", "up"):
            event.prevent_default()
            self.query_one("#app-table", DataTable).action_cursor_up()
        elif key == "slash":
            event.prevent_default()
            filter_input = self.query_one("#filter-input", Input)
            filter_input.add_class("visible")
            filter_input.focus()
        elif key == "enter":
            event.prevent_default()
            self._do_apply()
        elif key == "q":
            event.prevent_default()
            self._maybe_quit()
        elif key == "escape":
            event.prevent_default()
            self._clear_or_quit()

    def _do_toggle_sound(self) -> None:
        app = self._get_selected_app()
        if not app:
            return
        sound, badges = self.staged[app.index]
        self.staged[app.index] = (not sound, badges)
        self._update_row(app)
        self._update_change_count()
        self._update_summary()

    def _do_toggle_badges(self) -> None:
        app = self._get_selected_app()
        if not app:
            return
        sound, badges = self.staged[app.index]
        self.staged[app.index] = (sound, not badges)
        self._update_row(app)
        self._update_change_count()
        self._update_summary()

    def on_input_changed(self, event: Input.Changed) -> None:
        self.filter_text = event.value.lower()
        if self.filter_text:
            self.visible_apps = [a for a in self.apps if self.filter_text in a.name.lower()]
        else:
            self.visible_apps = list(self.apps)
        self._populate_table()

    def _clear_or_quit(self) -> None:
        filter_input = self.query_one("#filter-input", Input)
        if filter_input.has_class("visible"):
            filter_input.value = ""
            filter_input.remove_class("visible")
            self.filter_text = ""
            self.visible_apps = list(self.apps)
            self._populate_table()
            self.query_one("#app-table", DataTable).focus()
        else:
            self._maybe_quit()

    def _do_apply(self) -> None:
        changes = self._pending_changes()
        if not changes:
            self.exit()
            return
        self.push_screen(ConfirmScreen(changes), self._on_confirm)

    def _maybe_quit(self) -> None:
        changes = self._pending_changes()
        if not changes:
            self.exit()
            return
        # Quit discards changes — just exit
        self.exit()

    def _on_confirm(self, confirmed: bool | None) -> None:
        if not confirmed:
            return
        changes = self._pending_changes()
        if not changes:
            self.exit()
            return
        # Build the updates dict: {plist_index: new_flags}
        updates = {}
        for c in changes:
            new_flags = c["flags"]
            new_flags = set_flag(new_flags, SOUND_BIT, c["new_sound"])
            new_flags = set_flag(new_flags, BADGES_BIT, c["new_badges"])
            updates[c["index"]] = new_flags
        backup_plist(self.plist_path, self.backup_dir)
        write_apps(self.plist_path, updates)
        self.applied = True
        self.exit()
