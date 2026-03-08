"""Tests for plist writing."""
import plistlib
from pathlib import Path

from shhhhhh.plist import (
    SOUND_BIT,
    BADGES_BIT,
    read_apps,
    set_flag,
    write_apps,
    backup_plist,
)


def _make_plist(apps: list[dict], tmp_path: Path) -> Path:
    plist_path = tmp_path / "group.com.apple.usernoted.plist"
    with open(plist_path, "wb") as f:
        plistlib.dump({"apps": apps}, f)
    return plist_path


def _read_raw_flags(plist_path: Path, index: int) -> int:
    with open(plist_path, "rb") as f:
        data = plistlib.load(f)
    return data["apps"][index]["flags"]


def test_set_flag_enables_bit():
    assert set_flag(0b00000010, SOUND_BIT, True) == 0b00000110


def test_set_flag_disables_bit():
    assert set_flag(0b00000110, SOUND_BIT, False) == 0b00000010


def test_set_flag_noop_if_already_set():
    assert set_flag(0b00000110, SOUND_BIT, True) == 0b00000110


def test_write_apps_modifies_flags(tmp_path):
    plist = _make_plist([
        {"bundle-id": "com.test.app", "flags": 0b00000110, "path": "/Applications/Test.app"},
    ], tmp_path)
    apps = read_apps(plist)
    # Disable sound
    updates = {apps[0].index: set_flag(apps[0].flags, SOUND_BIT, False)}
    write_apps(plist, updates, restart=False)
    assert _read_raw_flags(plist, 0) == 0b00000010


def test_write_apps_preserves_other_flags(tmp_path):
    original_flags = 0x001080200e  # Spotify-like flags with many high bits
    plist = _make_plist([
        {"bundle-id": "com.test.app", "flags": original_flags, "path": "/Applications/Test.app"},
    ], tmp_path)
    apps = read_apps(plist)
    # Disable sound (bit 2)
    new_flags = set_flag(apps[0].flags, SOUND_BIT, False)
    updates = {apps[0].index: new_flags}
    write_apps(plist, updates, restart=False)
    result = _read_raw_flags(plist, 0)
    # Sound bit should be off, everything else preserved
    assert result & (1 << SOUND_BIT) == 0
    assert result & ~(1 << SOUND_BIT) == original_flags & ~(1 << SOUND_BIT)


def test_backup_plist(tmp_path):
    plist = _make_plist([{"bundle-id": "com.test", "flags": 6}], tmp_path)
    backup_dir = tmp_path / ".shh"
    backup_path = backup_plist(plist, backup_dir)
    assert backup_path.exists()
    with open(backup_path, "rb") as f:
        data = plistlib.load(f)
    assert data["apps"][0]["flags"] == 6
