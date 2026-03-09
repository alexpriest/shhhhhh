"""Tests for the interactive TUI."""
from pathlib import Path
from unittest.mock import patch

import pytest

from shhhhhh.interactive import ShhApp, ConfirmScreen
from shhhhhh.plist import AppInfo


def _make_apps():
    """Create a small list of test apps."""
    return [
        AppInfo(name="Arc", bundle_id="company.thebrowser.Browser", flags=0, index=0),
        AppInfo(name="Bear", bundle_id="net.shinyfrog.bear", flags=7, index=1),
        AppInfo(name="Slack", bundle_id="com.tinyspeck.slackmacgap", flags=7, index=2),
    ]


def _make_app(plist_path=None, backup_dir=None):
    apps = _make_apps()
    return ShhApp(
        apps,
        plist_path or Path("/tmp/test.plist"),
        backup_dir or Path("/tmp/test-backups"),
    )


@pytest.mark.asyncio
async def test_app_loads_with_apps():
    app = _make_app()
    async with app.run_test() as pilot:
        table = app.query_one("#app-table")
        assert table.row_count == 3


@pytest.mark.asyncio
async def test_toggle_sound():
    app = _make_app()
    async with app.run_test() as pilot:
        # Arc starts with sound off (flags=0)
        assert app.staged[0] == (False, False)
        await pilot.press("s")
        assert app.staged[0] == (True, False)
        # Toggle back
        await pilot.press("s")
        assert app.staged[0] == (False, False)


@pytest.mark.asyncio
async def test_toggle_badges():
    app = _make_app()
    async with app.run_test() as pilot:
        assert app.staged[0] == (False, False)
        await pilot.press("b")
        assert app.staged[0] == (False, True)


@pytest.mark.asyncio
async def test_navigate_and_toggle():
    app = _make_app()
    async with app.run_test() as pilot:
        # Move down to Bear (index 1), toggle sound off
        await pilot.press("down")
        # Bear starts with flags=7 (sound=True, badges=True)
        assert app.staged[1] == (True, True)
        await pilot.press("s")
        assert app.staged[1] == (False, True)


@pytest.mark.asyncio
async def test_j_k_navigation():
    app = _make_app()
    async with app.run_test() as pilot:
        await pilot.press("j")  # down to Bear
        await pilot.press("s")
        assert app.staged[1] == (False, True)
        await pilot.press("k")  # back to Arc
        await pilot.press("s")
        assert app.staged[0] == (True, False)


@pytest.mark.asyncio
async def test_change_count_updates():
    app = _make_app()
    async with app.run_test() as pilot:
        count_widget = app.query_one("#change-count")
        assert str(count_widget.render()) == ""
        await pilot.press("s")
        rendered = str(count_widget.render())
        assert "1 change" in rendered


@pytest.mark.asyncio
async def test_quit_no_changes():
    app = _make_app()
    async with app.run_test() as pilot:
        await pilot.press("q")
    assert not app.applied


@pytest.mark.asyncio
async def test_enter_no_changes_exits():
    app = _make_app()
    async with app.run_test() as pilot:
        await pilot.press("enter")
    assert not app.applied


@pytest.mark.asyncio
async def test_enter_with_changes_shows_confirm():
    app = _make_app()
    async with app.run_test() as pilot:
        await pilot.press("s")  # Toggle Arc sound
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, ConfirmScreen)


@pytest.mark.asyncio
async def test_confirm_and_apply():
    app = _make_app()
    with patch("shhhhhh.interactive.backup_plist") as mock_backup, \
         patch("shhhhhh.interactive.write_apps") as mock_write:
        async with app.run_test() as pilot:
            await pilot.press("s")  # Toggle Arc sound on
            await pilot.press("enter")
            await pilot.pause()
            await pilot.press("enter")  # Confirm
        assert app.applied
        mock_backup.assert_called_once()
        mock_write.assert_called_once()


@pytest.mark.asyncio
async def test_confirm_cancel():
    app = _make_app()
    async with app.run_test() as pilot:
        await pilot.press("s")  # Toggle Arc sound
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("escape")  # Cancel
        await pilot.pause()
        assert not isinstance(app.screen, ConfirmScreen)
        assert not app.applied
