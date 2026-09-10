"""Uninstall planning and execution against a fake home."""
import plistlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from shhhhhh import uninstall
from shhhhhh.plist import AppInfo


def _fake_home(tmp_path: Path, monkeypatch) -> Path:
    home = tmp_path / "home"
    lib = home / "Library"
    monkeypatch.setattr(uninstall, "HOME", home)
    monkeypatch.setattr(uninstall, "LIBRARY", lib)
    monkeypatch.setattr(uninstall, "TRASH", str(tmp_path / "no-such-trash"))  # force the shutil fallback
    (home / ".Trash").mkdir(parents=True)
    return home


def _app(tmp_path: Path) -> AppInfo:
    bundle = tmp_path / "Applications" / "Widget.app"
    (bundle / "Contents" / "MacOS").mkdir(parents=True)
    (bundle / "Contents" / "MacOS" / "Widget").write_bytes(b"x" * 100)
    return AppInfo(name="Widget", bundle_id="com.example.widget", flags=0, index=0, app_path=str(bundle))


def _scatter(lib: Path) -> list[Path]:
    paths = [
        lib / "Application Support" / "Widget",
        lib / "Caches" / "com.example.widget",
        lib / "Preferences" / "com.example.widget.plist",
        lib / "Preferences" / "com.example.widget.helper.plist",
        lib / "Saved Application State" / "com.example.widget.savedState",
        lib / "HTTPStorages" / "com.example.widget.binarycookies",
        lib / "LaunchAgents" / "com.example.widget.agent.plist",
        lib / "Group Containers" / "ABC123.com.example.widget",
    ]
    for p in paths:
        if p.suffix in (".plist", ".binarycookies"):
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b"data")
        else:
            p.mkdir(parents=True)
            (p / "file").write_bytes(b"data")
    container = lib / "Containers" / "0C4E-UUID"
    container.mkdir(parents=True)
    with open(container / ".com.apple.containermanagerd.metadata.plist", "wb") as f:
        plistlib.dump({"MCMMetadataIdentifier": "com.example.widget"}, f)
    other = lib / "Containers" / "1D5F-UUID"
    other.mkdir()
    with open(other / ".com.apple.containermanagerd.metadata.plist", "wb") as f:
        plistlib.dump({"MCMMetadataIdentifier": "com.example.other"}, f)
    # Decoys that must NOT be swept
    (lib / "Application Support" / "Widgets Pro").mkdir()
    (lib / "Preferences" / "com.example.widgetry.plist").write_bytes(b"x")
    return paths + [container]


def test_plan_finds_bundle_and_every_leftover_but_no_decoys(tmp_path, monkeypatch):
    home = _fake_home(tmp_path, monkeypatch)
    expected = _scatter(home / "Library")
    app = _app(tmp_path)
    with patch("shhhhhh.uninstall._is_running", return_value=False):
        plan = uninstall.plan_uninstall(app)
    assert plan.blocked is None
    assert plan.paths[0] == Path(app.app_path)
    assert set(plan.paths[1:]) == set(expected)
    assert plan.size > 100


def test_plan_refuses_apple_and_non_bundles(tmp_path, monkeypatch):
    _fake_home(tmp_path, monkeypatch)
    apple = AppInfo(name="Mail", bundle_id="com.apple.mail", flags=0, index=0, app_path="/System/Applications/Mail.app")
    assert "Apple" in uninstall.plan_uninstall(apple).blocked
    agent = AppInfo(name="thing", bundle_id="com.example.thing", flags=0, index=1, app_path="")
    assert "no .app" in uninstall.plan_uninstall(agent).blocked
    gone = AppInfo(name="Gone", bundle_id="com.example.gone", flags=0, index=2, app_path=str(tmp_path / "Gone.app"))
    assert "already gone" in uninstall.plan_uninstall(gone).blocked


def test_execute_moves_everything_to_trash_and_refuses_running(tmp_path, monkeypatch):
    home = _fake_home(tmp_path, monkeypatch)
    _scatter(home / "Library")
    app = _app(tmp_path)
    with patch("shhhhhh.uninstall._is_running", return_value=True):
        plan = uninstall.plan_uninstall(app)
    with pytest.raises(RuntimeError):
        uninstall.execute(plan)
    plan.running = False
    moved = uninstall.execute(plan)
    assert len(moved) == len(plan.paths)
    assert not any(p.exists() for p in plan.paths)
    assert (home / ".Trash" / "Widget.app").exists()
    assert (home / "Library" / "Application Support" / "Widgets Pro").exists()


def test_remove_from_plist_drops_only_that_entry(tmp_path):
    plist = tmp_path / "usernoted.plist"
    with open(plist, "wb") as f:
        plistlib.dump({"apps": [{"bundle-id": "com.example.widget", "flags": 1}, {"bundle-id": "com.other", "flags": 2}]}, f)
    with patch("shhhhhh.uninstall.subprocess"):
        uninstall.remove_from_plist(plist, "com.example.widget")
    with open(plist, "rb") as f:
        assert [a["bundle-id"] for a in plistlib.load(f)["apps"]] == ["com.other"]


def test_age_label():
    now = datetime(2026, 9, 10, tzinfo=timezone.utc)
    assert uninstall.age_label(None) == "never"
    assert uninstall.age_label(now - timedelta(hours=3), now) == "today"
    assert uninstall.age_label(now - timedelta(days=8), now) == "8d ago"
    assert uninstall.age_label(now - timedelta(days=70), now) == "2mo ago"
    assert uninstall.age_label(now - timedelta(days=800), now) == "2y ago"
