"""Tests for plist reading."""
import plistlib
import tempfile
from pathlib import Path

from shhhhhh.plist import (
    SOUND_BIT,
    BADGES_BIT,
    AppInfo,
    read_apps,
    has_flag,
    _humanize_bundle_id,
    _resolve_name,
)


def _make_plist(apps: list[dict], tmp_path: Path) -> Path:
    """Write a fake usernoted plist and return its path."""
    plist_path = tmp_path / "group.com.apple.usernoted.plist"
    with open(plist_path, "wb") as f:
        plistlib.dump({"apps": apps}, f)
    return plist_path


def test_read_apps_extracts_name_from_path(tmp_path):
    plist = _make_plist([
        {"bundle-id": "com.tinyspeck.slackmacgap", "flags": 14, "path": "/Applications/Slack.app"},
    ], tmp_path)
    apps = read_apps(plist)
    assert len(apps) == 1
    assert apps[0].name == "Slack"
    assert apps[0].bundle_id == "com.tinyspeck.slackmacgap"


def test_read_apps_falls_back_to_bundle_id(tmp_path):
    plist = _make_plist([
        {"bundle-id": "com.example.nopath", "flags": 14},
    ], tmp_path)
    apps = read_apps(plist)
    assert apps[0].name == "com.example.nopath"


def test_read_apps_skips_system_center(tmp_path):
    plist = _make_plist([
        {"bundle-id": "_SYSTEM_CENTER_:com.apple.something", "flags": 0},
        {"bundle-id": "com.real.app", "flags": 14, "path": "/Applications/RealApp.app"},
    ], tmp_path)
    apps = read_apps(plist)
    assert len(apps) == 1
    assert apps[0].name == "RealApp"


def test_has_flag_sound():
    assert has_flag(0b00000110, SOUND_BIT) is True   # bit 2 set
    assert has_flag(0b00000010, SOUND_BIT) is False   # bit 2 clear


def test_has_flag_badges():
    assert has_flag(0b00000110, BADGES_BIT) is True   # bit 1 set
    assert has_flag(0b00000100, BADGES_BIT) is False   # bit 1 clear


def test_read_apps_sorts_alphabetically(tmp_path):
    plist = _make_plist([
        {"bundle-id": "com.z", "flags": 14, "path": "/Applications/Zoom.app"},
        {"bundle-id": "com.a", "flags": 14, "path": "/Applications/Arc.app"},
    ], tmp_path)
    apps = read_apps(plist)
    assert apps[0].name == "Arc"
    assert apps[1].name == "Zoom"


def test_read_apps_handles_bundle_path(tmp_path):
    """Apps in .bundle directories should use friendly name lookup."""
    plist = _make_plist([
        {"bundle-id": "com.apple.iCal", "flags": 14,
         "path": "/System/Library/UserNotifications/Bundles/com.apple.iCal.bundle"},
    ], tmp_path)
    apps = read_apps(plist)
    assert apps[0].name == "Calendar"  # explicit friendly name


def test_friendly_name_overrides(tmp_path):
    """Known bundle IDs should use explicit friendly names."""
    plist = _make_plist([
        {"bundle-id": "com.apple.iChat", "flags": 14},
        {"bundle-id": "com.apple.Passbook", "flags": 14},
    ], tmp_path)
    apps = read_apps(plist)
    names = {a.bundle_id: a.name for a in apps}
    assert names["com.apple.iChat"] == "Messages"
    assert names["com.apple.Passbook"] == "Wallet"


def test_auto_humanize_apple_bundle_ids(tmp_path):
    """Apple bundle IDs without explicit mappings get auto-humanized."""
    plist = _make_plist([
        {"bundle-id": "com.apple.FamilyNotifications", "flags": 14},
        {"bundle-id": "com.apple.AppStore", "flags": 14},
        {"bundle-id": "com.apple.Home", "flags": 14},
    ], tmp_path)
    apps = read_apps(plist)
    names = {a.bundle_id: a.name for a in apps}
    assert names["com.apple.FamilyNotifications"] == "Family"
    assert names["com.apple.AppStore"] == "App Store"
    assert names["com.apple.Home"] == "Home"


def test_humanize_strips_suffixes():
    """_humanize_bundle_id strips known suffixes and inserts spaces."""
    assert _humanize_bundle_id("com.apple.FamilyNotifications") == "Family"
    assert _humanize_bundle_id("com.apple.ReplayKitNotifications") == "Replay Kit"
    assert _humanize_bundle_id("com.apple.TimeMachineNotifications") == "Time Machine"
    assert _humanize_bundle_id("com.apple.controlcenter.notifications.foo") == "foo"


def test_humanize_inserts_spaces():
    assert _humanize_bundle_id("com.apple.AppStore") == "App Store"
    assert _humanize_bundle_id("com.apple.BTUserNotifications") == "BT User"


def test_non_apple_bundle_id_unchanged(tmp_path):
    """Non-Apple bundle IDs without paths stay as raw bundle IDs."""
    plist = _make_plist([
        {"bundle-id": "com.example.nopath", "flags": 14},
    ], tmp_path)
    apps = read_apps(plist)
    assert apps[0].name == "com.example.nopath"


# --- allow / alert style (verified against System Settings on macOS 26, 2026-09-10) ---
import pytest
from shhhhhh.plist import ALLOW_BIT, TEMPORARY_BIT, PERSISTENT_BIT, set_style

CLAUDE_FLAGS = 310386698      # bits 1,3,13,23,25,28 -> "Badges, Desktop", Temporary
CLEANSHOT_FLAGS = 276832266   # same minus bit 25 -> "Off"
APPSTORE_FLAGS = 1946222618   # bits 1,4,19,23,25,28,29,30 -> Persistent


def test_allowed_is_bit_25():
    assert ALLOW_BIT == 25
    assert AppInfo("Claude", "c", CLAUDE_FLAGS, 0).allowed is True
    assert AppInfo("CleanShot", "c", CLEANSHOT_FLAGS, 0).allowed is False


def test_style_temporary_persistent_off():
    assert (TEMPORARY_BIT, PERSISTENT_BIT) == (3, 4)
    assert AppInfo("Claude", "c", CLAUDE_FLAGS, 0).style == "temporary"
    assert AppInfo("App Store", "a", APPSTORE_FLAGS, 0).style == "persistent"
    assert AppInfo("Off", "o", CLAUDE_FLAGS & ~(1 << 3), 0).style == "off"


def test_style_survives_allow_off():
    """Turning notifications off leaves the style bits alone, like System Settings does."""
    assert AppInfo("CleanShot", "c", CLEANSHOT_FLAGS, 0).style == "temporary"


def test_set_style_clears_both_then_sets_one():
    assert set_style(CLAUDE_FLAGS, "persistent") == (CLAUDE_FLAGS & ~(1 << 3)) | (1 << 4)
    assert set_style(APPSTORE_FLAGS, "temporary") == (APPSTORE_FLAGS & ~(1 << 4)) | (1 << 3)
    off = set_style(CLAUDE_FLAGS, "off")
    assert off & 0b11000 == 0
    assert off | 0b11000 == CLAUDE_FLAGS | 0b11000  # nothing else touched


def test_set_style_rejects_unknown():
    with pytest.raises(ValueError):
        set_style(CLAUDE_FLAGS, "loud")


def test_humanize_does_not_return_empty_for_bare_suffix_component():
    from shhhhhh.plist import _humanize_bundle_id
    assert _humanize_bundle_id("com.apple.ecosystem.notifications") == "ecosystem"
    assert _humanize_bundle_id("com.apple.ScreenTimeEnabledNotifications") == "Screen Time Enabled"


def test_lock_screen_and_center_are_inverted_bits():
    from shhhhhh.plist import set_center, set_lock_screen
    on = AppInfo("Bartleby", "b", CLAUDE_FLAGS, 0)
    assert on.lock_screen and on.center
    hidden = AppInfo("Bartleby", "b", CLAUDE_FLAGS | (1 << 12) | (1 << 0) | (1 << 8), 0)
    assert not hidden.lock_screen and not hidden.center
    assert set_lock_screen(hidden.flags, True) == CLAUDE_FLAGS | (1 << 0) | (1 << 8)
    assert set_center(hidden.flags, True) == CLAUDE_FLAGS | (1 << 12)
    assert set_center(set_lock_screen(CLAUDE_FLAGS, False), False) == hidden.flags
