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
