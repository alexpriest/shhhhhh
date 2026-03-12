"""Tests for CLI commands."""
import plistlib
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from shhhhhh.cli import main


def _make_plist(apps: list[dict], tmp_path: Path) -> Path:
    plist_path = tmp_path / "group.com.apple.usernoted.plist"
    with open(plist_path, "wb") as f:
        plistlib.dump({"apps": apps}, f)
    return plist_path


SAMPLE_APPS = [
    {"bundle-id": "com.tinyspeck.slackmacgap", "flags": 0b00000010, "path": "/Applications/Slack.app"},  # sound OFF, badges ON
    {"bundle-id": "com.linear", "flags": 0b00000110, "path": "/Applications/Linear.app"},  # sound ON, badges ON
    {"bundle-id": "_SYSTEM_CENTER_:com.apple.something", "flags": 0},  # should be skipped
]


def test_permission_error_shows_guidance(tmp_path):
    """Permission error shows friendly message instead of traceback."""
    plist = tmp_path / "test.plist"
    plist.write_bytes(b"test")
    plist.chmod(0o000)
    runner = CliRunner()
    try:
        with patch("shhhhhh.cli.PLIST_PATH", plist), \
             patch("shhhhhh.cli.prompt_open_settings") as mock_prompt:
            result = runner.invoke(main, ["list"])
        assert result.exit_code == 0
        assert "Full Disk Access" in result.output
        assert "Traceback" not in result.output
        mock_prompt.assert_called_once()
    finally:
        plist.chmod(0o644)


def test_list_shows_apps(tmp_path):
    plist = _make_plist(SAMPLE_APPS, tmp_path)
    runner = CliRunner()
    with patch("shhhhhh.cli.PLIST_PATH", plist):
        result = runner.invoke(main, ["list"])
    assert result.exit_code == 0
    assert "Slack" in result.output
    assert "Linear" in result.output
    assert "_SYSTEM_CENTER_" not in result.output


def test_sound_off_all(tmp_path):
    plist = _make_plist(SAMPLE_APPS, tmp_path)
    runner = CliRunner()
    backup_dir = tmp_path / ".shh"
    with patch("shhhhhh.cli.PLIST_PATH", plist), \
         patch("shhhhhh.cli.BACKUP_DIR", backup_dir), \
         patch("shhhhhh.plist.subprocess"):
        result = runner.invoke(main, ["sound", "off", "--all", "--yes"])
    assert result.exit_code == 0
    # Verify flags in plist
    with open(plist, "rb") as f:
        data = plistlib.load(f)
    # Slack: was 0b010, sound bit cleared -> 0b010 (was already off)
    assert data["apps"][0]["flags"] & 0b100 == 0
    # Linear: was 0b110, sound bit cleared -> 0b010
    assert data["apps"][1]["flags"] & 0b100 == 0
    assert data["apps"][1]["flags"] & 0b010 == 0b010  # badges preserved


def test_sound_on_specific_app(tmp_path):
    plist = _make_plist(SAMPLE_APPS, tmp_path)
    runner = CliRunner()
    backup_dir = tmp_path / ".shh"
    with patch("shhhhhh.cli.PLIST_PATH", plist), \
         patch("shhhhhh.cli.BACKUP_DIR", backup_dir), \
         patch("shhhhhh.plist.subprocess"):
        result = runner.invoke(main, ["sound", "on", "Slack"])
    assert result.exit_code == 0
    with open(plist, "rb") as f:
        data = plistlib.load(f)
    assert data["apps"][0]["flags"] & 0b100 == 0b100  # sound now ON


def test_sound_off_no_match(tmp_path):
    plist = _make_plist(SAMPLE_APPS, tmp_path)
    runner = CliRunner()
    with patch("shhhhhh.cli.PLIST_PATH", plist):
        result = runner.invoke(main, ["sound", "off", "NonExistent"])
    assert result.exit_code == 0
    assert "No apps matched" in result.output


def test_undo_restores_backup(tmp_path):
    plist = _make_plist(SAMPLE_APPS, tmp_path)
    backup_dir = tmp_path / ".shh"
    runner = CliRunner()
    # First, make a change to create a backup
    with patch("shhhhhh.cli.PLIST_PATH", plist), \
         patch("shhhhhh.cli.BACKUP_DIR", backup_dir), \
         patch("shhhhhh.plist.subprocess"):
        runner.invoke(main, ["sound", "off", "--all", "--yes"])
    # Now undo
    with patch("shhhhhh.cli.PLIST_PATH", plist), \
         patch("shhhhhh.cli.BACKUP_DIR", backup_dir), \
         patch("shhhhhh.plist.subprocess"):
        result = runner.invoke(main, ["undo"])
    assert result.exit_code == 0
    # Original flags should be restored
    with open(plist, "rb") as f:
        data = plistlib.load(f)
    assert data["apps"][1]["flags"] == 0b00000110  # Linear restored


def test_list_grouped_by_default(tmp_path):
    plist = _make_plist(SAMPLE_APPS, tmp_path)
    runner = CliRunner()
    with patch("shhhhhh.cli.PLIST_PATH", plist):
        result = runner.invoke(main, ["list"])
    assert result.exit_code == 0
    # Category headers should appear (Slack=Messaging, Linear=Work)
    assert "MESSAGING" in result.output
    assert "WORK" in result.output


def test_list_flat_flag(tmp_path):
    plist = _make_plist(SAMPLE_APPS, tmp_path)
    runner = CliRunner()
    with patch("shhhhhh.cli.PLIST_PATH", plist):
        result = runner.invoke(main, ["list", "--flat"])
    assert result.exit_code == 0
    assert "Slack" in result.output
    # Flat mode should NOT show category headers
    assert "MESSAGING" not in result.output


def test_sound_off_by_category(tmp_path):
    plist = _make_plist(SAMPLE_APPS, tmp_path)
    runner = CliRunner()
    backup_dir = tmp_path / ".shh"
    with patch("shhhhhh.cli.PLIST_PATH", plist), \
         patch("shhhhhh.cli.BACKUP_DIR", backup_dir), \
         patch("shhhhhh.plist.subprocess"):
        result = runner.invoke(main, ["sound", "off", "--category", "work", "--yes"])
    assert result.exit_code == 0
    with open(plist, "rb") as f:
        data = plistlib.load(f)
    # Linear (Work) should have sound off
    assert data["apps"][1]["flags"] & 0b100 == 0
    # Slack (Messaging) should be unchanged
    assert data["apps"][0]["flags"] == 0b00000010


def test_sound_off_unknown_category(tmp_path):
    plist = _make_plist(SAMPLE_APPS, tmp_path)
    runner = CliRunner()
    with patch("shhhhhh.cli.PLIST_PATH", plist):
        result = runner.invoke(main, ["sound", "off", "--category", "nonexistent"])
    assert result.exit_code == 0
    assert "No apps in category" in result.output


def test_category_list(tmp_path):
    plist = _make_plist(SAMPLE_APPS, tmp_path)
    runner = CliRunner()
    with patch("shhhhhh.cli.PLIST_PATH", plist):
        result = runner.invoke(main, ["category", "list"])
    assert result.exit_code == 0
    assert "Messaging" in result.output
    assert "Work" in result.output


def test_category_mute(tmp_path):
    plist = _make_plist(SAMPLE_APPS, tmp_path)
    runner = CliRunner()
    backup_dir = tmp_path / ".shh"
    with patch("shhhhhh.cli.PLIST_PATH", plist), \
         patch("shhhhhh.cli.BACKUP_DIR", backup_dir), \
         patch("shhhhhh.plist.subprocess"):
        result = runner.invoke(main, ["category", "mute", "work", "--yes"])
    assert result.exit_code == 0
    with open(plist, "rb") as f:
        data = plistlib.load(f)
    # Linear (Work, index 1) should have sound off
    assert data["apps"][1]["flags"] & 0b100 == 0
    assert data["apps"][1]["flags"] & 0b010 == 0b010  # badges preserved


def test_category_unmute(tmp_path):
    # First mute, then unmute
    apps = [
        {"bundle-id": "com.tinyspeck.slackmacgap", "flags": 0b00000010, "path": "/Applications/Slack.app"},  # sound OFF
    ]
    plist = _make_plist(apps, tmp_path)
    runner = CliRunner()
    backup_dir = tmp_path / ".shh"
    with patch("shhhhhh.cli.PLIST_PATH", plist), \
         patch("shhhhhh.cli.BACKUP_DIR", backup_dir), \
         patch("shhhhhh.plist.subprocess"):
        result = runner.invoke(main, ["category", "unmute", "messaging", "--yes"])
    assert result.exit_code == 0
    with open(plist, "rb") as f:
        data = plistlib.load(f)
    assert data["apps"][0]["flags"] & 0b100 == 0b100  # sound now ON


def test_category_mute_unknown(tmp_path):
    plist = _make_plist(SAMPLE_APPS, tmp_path)
    runner = CliRunner()
    with patch("shhhhhh.cli.PLIST_PATH", plist):
        result = runner.invoke(main, ["category", "mute", "nonexistent"])
    assert result.exit_code == 0
    assert "No apps in category" in result.output
