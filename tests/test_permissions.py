"""Tests for permission checks."""
import os
from unittest.mock import patch, MagicMock

from shhhhhh.permissions import detect_terminal, check_access


def test_detect_terminal_ghostty():
    with patch.dict(os.environ, {"TERM_PROGRAM": "ghostty"}):
        assert detect_terminal() == "Ghostty"


def test_detect_terminal_iterm():
    with patch.dict(os.environ, {"TERM_PROGRAM": "iTerm.app"}):
        assert detect_terminal() == "iTerm2"


def test_detect_terminal_apple_terminal():
    with patch.dict(os.environ, {"TERM_PROGRAM": "Apple_Terminal"}):
        assert detect_terminal() == "Terminal"


def test_detect_terminal_unknown():
    with patch.dict(os.environ, {}, clear=True):
        assert detect_terminal() == "your terminal"


def test_check_access_succeeds(tmp_path):
    """No exception when file is readable."""
    plist = tmp_path / "test.plist"
    plist.write_bytes(b"test")
    assert check_access(plist) is True


def test_check_access_permission_error(tmp_path):
    """Returns False and prints guidance when permission denied."""
    plist = tmp_path / "test.plist"
    plist.write_bytes(b"test")
    plist.chmod(0o000)
    try:
        result = check_access(plist)
        assert result is False
    finally:
        plist.chmod(0o644)


def test_check_access_missing_file(tmp_path):
    """Returns False when plist doesn't exist."""
    plist = tmp_path / "nonexistent.plist"
    result = check_access(plist)
    assert result is False
