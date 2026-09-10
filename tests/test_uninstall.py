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
    assert uninstall.age_label(None) == "no trace"
    assert uninstall.age_label(None, running=True) == "running"
    assert uninstall.age_label(now - timedelta(hours=3), now) == "today"
    assert uninstall.age_label(now - timedelta(days=8), now) == "8d ago"
    assert uninstall.age_label(now - timedelta(days=70), now) == "2mo ago"
    assert uninstall.age_label(now - timedelta(days=800), now) == "2y ago"


def test_root_owned_paths_go_through_the_finder_and_the_app_goes_last(tmp_path, monkeypatch):
    home = _fake_home(tmp_path, monkeypatch)
    _scatter(home / "Library")
    app = _app(tmp_path)
    bundle = Path(app.app_path)
    with patch("shhhhhh.uninstall._is_running", return_value=False):
        plan = uninstall.plan_uninstall(app)
    calls = []
    with patch("shhhhhh.uninstall._owned_by_me", side_effect=lambda p: p != bundle), \
         patch("shhhhhh.uninstall._finder_trash", side_effect=lambda p: calls.append(p)):
        assert plan.needs_admin == [bundle]
        moved = uninstall.execute(plan)
    assert calls == [bundle]                 # only the root-owned .app went via the Finder
    assert moved[-1] == bundle               # and it went last
    assert bundle.exists()                   # the fake Finder did not touch disk


def test_trash_failure_is_reported_not_raised_raw(tmp_path, monkeypatch):
    import subprocess
    home = _fake_home(tmp_path, monkeypatch)
    _scatter(home / "Library")
    app = _app(tmp_path)
    with patch("shhhhhh.uninstall._is_running", return_value=False):
        plan = uninstall.plan_uninstall(app)
    err = subprocess.CalledProcessError(5, ["trash"], stderr="trash[1] # Error attempting to move /Applications/Widget.app: Operation not permitted")
    with patch("shhhhhh.uninstall._owned_by_me", return_value=False), \
         patch("shhhhhh.uninstall._finder_trash", side_effect=err):
        with pytest.raises(uninstall.UninstallError) as info:
            uninstall.execute(plan)
    assert "Operation not permitted" in str(info.value)
    assert info.value.moved == []            # first path failed, nothing else attempted


def test_sweep_catches_extensions_catalyst_ids_and_recent_lists_but_not_icloud(tmp_path, monkeypatch):
    home = _fake_home(tmp_path, monkeypatch)
    lib = home / "Library"
    bundle = tmp_path / "Applications" / "Book Tracker.app"
    (bundle / "Contents" / "MacOS").mkdir(parents=True)
    app = AppInfo(name="Book Tracker", bundle_id="maccatalyst.com.dev.booktrack", flags=0, index=0, app_path=str(bundle))
    wanted = [
        lib / "Application Scripts" / "maccatalyst.com.dev.booktrack.booktrack-widgets",
        lib / "Application Scripts" / "maccatalyst.com.dev.booktrack.intent-handler",
        lib / "Application Scripts" / "group.com.dev.booktrack.coredata",
        lib / "Group Containers" / "group.com.dev.booktrack.coredata",
        lib / "Caches" / "CloudKit" / "maccatalyst.com.dev.booktrack",
        lib / "Application Support" / "com.apple.sharedfilelist" / "com.apple.LSSharedFileList.ApplicationRecentDocuments" / "maccatalyst.com.dev.booktrack.sfl4",
    ]
    for w in wanted:
        if w.suffix == ".sfl4":
            w.parent.mkdir(parents=True, exist_ok=True); w.write_bytes(b"x")
        else:
            w.mkdir(parents=True)
    ext_container = lib / "Containers" / "UUID-1"
    ext_container.mkdir(parents=True)
    with open(ext_container / ".com.apple.containermanagerd.metadata.plist", "wb") as f:
        plistlib.dump({"MCMMetadataIdentifier": "maccatalyst.com.dev.booktrack.booktrack-liveactivities"}, f)
    wanted.append(ext_container)
    # must be left alone
    icloud = lib / "Mobile Documents" / "iCloud~com~dev~booktrack"; icloud.mkdir(parents=True)
    other_cache = lib / "Application Support" / "DeckApp" / "IconCache"; other_cache.mkdir(parents=True)
    (other_cache / "app_maccatalyst_com_dev_booktrack.b64").write_bytes(b"x")
    lookalike = lib / "Application Support" / "com.dev.booktrackpro"; lookalike.mkdir()
    with patch("shhhhhh.uninstall._is_running", return_value=False):
        plan = uninstall.plan_uninstall(app)
    assert set(plan.paths[1:]) == set(wanted)


def test_last_used_takes_the_newest_signal(tmp_path, monkeypatch):
    import os, sqlite3, time
    home = _fake_home(tmp_path, monkeypatch)
    lib = home / "Library"
    app = _app(tmp_path)
    # Screen Time record: 20 days ago
    db = lib / "Application Support" / "Knowledge" / "knowledgeC.db"
    db.parent.mkdir(parents=True)
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE ZOBJECT (ZSTREAMNAME TEXT, ZVALUESTRING TEXT, ZSTARTDATE REAL)")
    twenty_days_ago = time.time() - 20 * 86400 - uninstall._COCOA_EPOCH
    con.execute("INSERT INTO ZOBJECT VALUES ('/app/usage', 'com.example.widget', ?)", (twenty_days_ago,))
    con.execute("INSERT INTO ZOBJECT VALUES ('/app/usage', 'com.other', ?)", (twenty_days_ago + 86400,))
    con.commit(); con.close()
    monkeypatch.setattr(uninstall, "KNOWLEDGE_DB", db)
    # A preferences write 3 days ago beats it
    prefs = lib / "Preferences" / "com.example.widget.plist"
    prefs.parent.mkdir(parents=True); prefs.write_bytes(b"x")
    three_days_ago = time.time() - 3 * 86400
    os.utime(prefs, (three_days_ago, three_days_ago))
    with patch("shhhhhh.uninstall.spotlight_last_used", return_value=None), \
         patch("shhhhhh.uninstall._is_running", return_value=False):
        when, running = uninstall.last_used(app)
    assert not running
    assert uninstall.age_label(when) == "3d ago"
    # Spotlight newer still wins
    with patch("shhhhhh.uninstall.spotlight_last_used", return_value=datetime.now(timezone.utc)), \
         patch("shhhhhh.uninstall._is_running", return_value=True):
        when, running = uninstall.last_used(app)
    assert running and uninstall.age_label(when, running=running) == "running"


def test_last_used_with_no_signals_is_none(tmp_path, monkeypatch):
    _fake_home(tmp_path, monkeypatch)
    monkeypatch.setattr(uninstall, "KNOWLEDGE_DB", tmp_path / "missing.db")
    app = _app(tmp_path)
    with patch("shhhhhh.uninstall.spotlight_last_used", return_value=None), \
         patch("shhhhhh.uninstall._is_running", return_value=False):
        assert uninstall.last_used(app) == (None, False)


def test_is_running_matches_the_bundle_executable_prefix(tmp_path):
    bundle = tmp_path / "Widget.app"
    procs = [str(bundle / "Contents" / "MacOS" / "Widget"), "/usr/sbin/cfprefsd"]
    assert uninstall._is_running(bundle, procs)
    assert not uninstall._is_running(tmp_path / "Other.app", procs)
