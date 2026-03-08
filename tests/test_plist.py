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
    """Apps in .bundle directories should extract the name before .bundle."""
    plist = _make_plist([
        {"bundle-id": "com.apple.iCal", "flags": 14,
         "path": "/System/Library/UserNotifications/Bundles/com.apple.iCal.bundle"},
    ], tmp_path)
    apps = read_apps(plist)
    assert apps[0].name == "com.apple.iCal"  # bundle paths use bundle-id
