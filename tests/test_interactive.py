"""Tests for the interactive TUI."""
from pathlib import Path
from unittest.mock import patch

import pytest

from shhhhhh.interactive import ShhApp, ConfirmScreen, HelpScreen, UninstallScreen, describe_change
from shhhhhh.plist import ALLOW_BIT, BADGES_BIT, SOUND_BIT, AppInfo, style_of

ON = 1 << ALLOW_BIT
SOUND = 1 << SOUND_BIT
BADGE = 1 << BADGES_BIT
TEMP = 1 << 3


def _make_apps():
    return [
        AppInfo(name="tccd", bundle_id="com.apple.tccd", flags=ON | TEMP | BADGE, index=3),
        AppInfo(name="Arc", bundle_id="company.thebrowser.Browser", flags=0, index=0),          # off, style off, no badge, no sound
        AppInfo(name="Bear", bundle_id="net.shinyfrog.bear", flags=ON | TEMP | BADGE | SOUND, index=1),
        AppInfo(name="Slack", bundle_id="com.tinyspeck.slackmacgap", flags=ON | TEMP | BADGE | SOUND, index=2),
    ]


def _make_app(plist_path=None, backup_dir=None):
    return ShhApp(_make_apps(), plist_path or Path("/tmp/test.plist"), backup_dir or Path("/tmp/test-backups"))


@pytest.mark.asyncio
async def test_app_loads_with_apps():
    app = _make_app()
    async with app.run_test() as pilot:
        assert app.query_one("#app-table").row_count == 3


@pytest.mark.asyncio
async def test_toggle_sound():
    app = _make_app()
    async with app.run_test() as pilot:
        await pilot.press("s")
        assert app.staged[0] == SOUND
        await pilot.press("s")
        assert app.staged[0] == 0


@pytest.mark.asyncio
async def test_toggle_badges():
    app = _make_app()
    async with app.run_test() as pilot:
        await pilot.press("b")
        assert app.staged[0] == BADGE


@pytest.mark.asyncio
async def test_space_toggles_allow_only():
    app = _make_app()
    async with app.run_test() as pilot:
        await pilot.press("down", "space")   # Bear: on -> off, everything else intact
        assert app.staged[1] == TEMP | BADGE | SOUND
        await pilot.press("space")
        assert app.staged[1] == ON | TEMP | BADGE | SOUND


@pytest.mark.asyncio
async def test_t_cycles_alert_style():
    app = _make_app()
    async with app.run_test() as pilot:
        await pilot.press("down", "t")
        assert style_of(app.staged[1]) == "persistent"
        await pilot.press("t")
        assert style_of(app.staged[1]) == "off"
        await pilot.press("t")
        assert style_of(app.staged[1]) == "temporary"
        assert app.staged[1] == app.original[1]


@pytest.mark.asyncio
async def test_uppercase_s_and_b_hit_every_app():
    app = _make_app()
    async with app.run_test() as pilot:
        await pilot.press("S")   # some have sound -> mute all
        assert not any(f & SOUND for f in app.staged.values())
        await pilot.press("S")   # none has sound -> unmute all
        assert all(f & SOUND for f in app.staged.values())
        await pilot.press("B")
        assert not any(f & BADGE for f in app.staged.values())


@pytest.mark.asyncio
async def test_u_reverts_row_and_escape_discards_all():
    app = _make_app()
    async with app.run_test() as pilot:
        await pilot.press("s", "b", "down", "s", "k", "u")
        assert app.staged[0] == app.original[0]
        assert app.staged[1] != app.original[1]
        await pilot.press("escape")
        await pilot.pause()
        assert app.staged == app.original
        assert app.is_running


@pytest.mark.asyncio
async def test_navigate_and_toggle():
    app = _make_app()
    async with app.run_test() as pilot:
        await pilot.press("down", "s")
        assert app.staged[1] == ON | TEMP | BADGE


@pytest.mark.asyncio
async def test_j_k_navigation():
    app = _make_app()
    async with app.run_test() as pilot:
        await pilot.press("j", "s")
        assert app.staged[1] == ON | TEMP | BADGE
        await pilot.press("k", "s")
        assert app.staged[0] == SOUND


@pytest.mark.asyncio
async def test_change_count_updates():
    app = _make_app()
    async with app.run_test() as pilot:
        count_widget = app.query_one("#change-count")
        assert str(count_widget.render()) == ""
        await pilot.press("s")
        assert "1 change" in str(count_widget.render())


@pytest.mark.asyncio
async def test_filter_then_escape_clears_it():
    app = _make_app()
    async with app.run_test() as pilot:
        await pilot.press("slash", "s", "l")
        await pilot.pause()
        assert [a.name for a in app.visible_apps] == ["Slack"]
        await pilot.press("escape")
        await pilot.pause()
        assert len(app.visible_apps) == 3
        assert app.is_running


@pytest.mark.asyncio
async def test_quit_no_changes():
    app = _make_app()
    async with app.run_test() as pilot:
        await pilot.press("q")
    assert not app.applied


@pytest.mark.asyncio
async def test_quit_with_changes_warns_then_quits():
    app = _make_app()
    async with app.run_test() as pilot:
        await pilot.press("s", "q")
        await pilot.pause()
        assert app.is_running
        await pilot.press("q")
        await pilot.pause()
    assert not app.is_running and not app.applied


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
        await pilot.press("s", "enter")
        await pilot.pause()
        assert isinstance(app.screen, ConfirmScreen)


@pytest.mark.asyncio
async def test_confirm_and_apply_writes_whole_masks():
    app = _make_app()
    with patch("shhhhhh.interactive.backup_plist") as mock_backup, \
         patch("shhhhhh.interactive.write_apps") as mock_write:
        async with app.run_test() as pilot:
            await pilot.press("s", "down", "t", "enter")
            await pilot.pause()
            await pilot.press("enter")
        assert app.applied
        mock_backup.assert_called_once()
        mock_write.assert_called_once_with(Path("/tmp/test.plist"), {0: SOUND, 1: ON | (1 << 4) | BADGE | SOUND})


@pytest.mark.asyncio
async def test_confirm_cancel():
    app = _make_app()
    async with app.run_test() as pilot:
        await pilot.press("s", "enter")
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, ConfirmScreen)
        assert not app.applied


def test_describe_change_names_every_field():
    line = describe_change("Bear", ON | TEMP | BADGE | SOUND, (1 << 4) | SOUND)
    assert "notifications off" in line
    assert "style temporary → persistent" in line
    assert "badges ✓ → ✗" in line
    assert "sound" not in line


@pytest.mark.asyncio
async def test_n_and_l_toggle_center_and_lock_screen_inverted_bits():
    app = _make_app()
    async with app.run_test() as pilot:
        await pilot.press("down", "n")
        assert app.staged[1] & (1 << 0) and app.staged[1] & (1 << 8)   # hidden from Notification Center
        await pilot.press("l")
        assert app.staged[1] & (1 << 12)                              # hidden on Lock Screen
        await pilot.press("n", "l")
        assert app.staged[1] == app.original[1]


@pytest.mark.asyncio
async def test_question_mark_opens_help_and_any_key_closes_it():
    app = _make_app()
    async with app.run_test() as pilot:
        await pilot.press("question_mark")
        await pilot.pause()
        assert isinstance(app.screen, HelpScreen)
        await pilot.press("s")
        await pilot.pause()
        assert not isinstance(app.screen, HelpScreen)
        assert app.staged == app.original   # the closing key does not toggle anything


@pytest.mark.asyncio
async def test_system_entries_hidden_until_a():
    app = _make_app()
    async with app.run_test() as pilot:
        assert [a.name for a in app.visible_apps] == ["Arc", "Bear", "Slack"]
        assert "1 system entries hidden · a to show" in app._summary_text()
        await pilot.press("a")
        assert sorted(a.name for a in app.visible_apps) == ["Arc", "Bear", "Slack", "tccd"]
        assert "a to hide" in app._summary_text()
        await pilot.press("a")
        assert len(app.visible_apps) == 3


@pytest.mark.asyncio
async def test_o_adds_last_used_column_from_spotlight():
    app = _make_app()
    with patch("shhhhhh.interactive.last_used", return_value=None):
        async with app.run_test() as pilot:
            await pilot.press("o")
            await pilot.pause()
            table = app.query_one("#app-table")
            assert "last_used" in [str(c.key.value) for c in table.columns.values()]
            assert set(app.last_used.values()) == {""}   # no .app paths in the fixture -> nothing looked up
            await pilot.press("o")
            await pilot.pause()
            assert "last_used" not in [str(c.key.value) for c in table.columns.values()]


@pytest.mark.asyncio
async def test_U_refuses_apple_and_non_bundles_with_a_warning():
    app = _make_app()
    async with app.run_test() as pilot:
        await pilot.press("U")          # Arc has no app_path in the fixture
        await pilot.pause()
        assert not isinstance(app.screen, UninstallScreen)
        assert app.is_running


@pytest.mark.asyncio
async def test_U_reviews_then_trashes_and_drops_the_entry(tmp_path):
    import plistlib
    plist = tmp_path / "usernoted.plist"
    bundle = tmp_path / "Widget.app"
    (bundle / "Contents" / "MacOS").mkdir(parents=True)
    with open(plist, "wb") as f:
        plistlib.dump({"apps": [
            {"bundle-id": "com.example.widget", "flags": ON | TEMP | BADGE, "path": str(bundle)},
            {"bundle-id": "com.example.zed", "flags": ON | TEMP, "path": "/Applications/Zed.app"},
        ]}, f)
    from shhhhhh.plist import read_apps
    app = ShhApp(read_apps(plist), plist, tmp_path / ".shh")
    with patch("shhhhhh.uninstall._is_running", return_value=False), \
         patch("shhhhhh.interactive.execute_uninstall", return_value=[bundle]) as ex, \
         patch("shhhhhh.uninstall.subprocess"):
        async with app.run_test() as pilot:
            await pilot.press("down", "s")       # stage something on Zed first; it must survive
            await pilot.press("up", "U")
            await pilot.pause()
            assert isinstance(app.screen, UninstallScreen)
            await pilot.press("enter")
            await pilot.pause()
            assert ex.called
            assert [a.name for a in app.apps] == ["Zed"]
            zed = app.apps[0]
            assert app.staged[zed.index] == ON | TEMP | SOUND   # staged edit carried across the reload
    with open(plist, "rb") as f:
        assert [a["bundle-id"] for a in plistlib.load(f)["apps"]] == ["com.example.zed"]
