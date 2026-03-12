"""Tests for app category detection and grouping."""
import plistlib
from pathlib import Path

from shhhhhh.categories import (
    resolve_category,
    group_by_category,
    CATEGORY_ORDER,
    MESSAGING,
    WORK,
    BROWSERS,
    OTHER,
)
from shhhhhh.plist import AppInfo


def _app(name: str, category: str = OTHER) -> AppInfo:
    return AppInfo(name=name, bundle_id=f"com.test.{name.lower()}", flags=7, index=0, category=category)


class TestResolveCategory:
    def test_override_hit(self):
        assert resolve_category("com.google.Chrome", "/Applications/Google Chrome.app") == BROWSERS

    def test_override_takes_priority_over_plist(self, tmp_path):
        """Override map wins even if the app has a valid UTI in its Info.plist."""
        app = tmp_path / "Discord.app" / "Contents"
        app.mkdir(parents=True)
        with open(app / "Info.plist", "wb") as f:
            plistlib.dump({"LSApplicationCategoryType": "public.app-category.developer-tools"}, f)
        assert resolve_category("com.hnc.Discord", str(tmp_path / "Discord.app")) == MESSAGING

    def test_valid_uti_from_plist(self, tmp_path):
        app = tmp_path / "Notion.app" / "Contents"
        app.mkdir(parents=True)
        with open(app / "Info.plist", "wb") as f:
            plistlib.dump({"LSApplicationCategoryType": "public.app-category.productivity"}, f)
        assert resolve_category("com.example.notion", str(tmp_path / "Notion.app")) == WORK

    def test_missing_plist(self):
        assert resolve_category("com.example.missing", "/nonexistent/App.app") == OTHER

    def test_unknown_uti(self, tmp_path):
        app = tmp_path / "Weird.app" / "Contents"
        app.mkdir(parents=True)
        with open(app / "Info.plist", "wb") as f:
            plistlib.dump({"LSApplicationCategoryType": "public.app-category.something-new"}, f)
        assert resolve_category("com.example.weird", str(tmp_path / "Weird.app")) == OTHER

    def test_no_path(self):
        assert resolve_category("com.example.nopath", "") == OTHER

    def test_no_uti_in_plist(self, tmp_path):
        app = tmp_path / "Simple.app" / "Contents"
        app.mkdir(parents=True)
        with open(app / "Info.plist", "wb") as f:
            plistlib.dump({"CFBundleName": "Simple"}, f)
        assert resolve_category("com.example.simple", str(tmp_path / "Simple.app")) == OTHER


class TestGroupByCategory:
    def test_groups_ordered_by_category_order(self):
        apps = [
            _app("Xcode", "Developer"),
            _app("Slack", "Messaging"),
            _app("Mail", "Email"),
        ]
        groups = group_by_category(apps)
        assert list(groups.keys()) == ["Messaging", "Email", "Developer"]

    def test_apps_sorted_within_groups(self):
        apps = [
            _app("Zoom", "Messaging"),
            _app("Discord", "Messaging"),
            _app("Slack", "Messaging"),
        ]
        groups = group_by_category(apps)
        names = [a.name for a in groups["Messaging"]]
        assert names == ["Discord", "Slack", "Zoom"]

    def test_empty_categories_omitted(self):
        apps = [_app("Chrome", "Browsers")]
        groups = group_by_category(apps)
        assert list(groups.keys()) == ["Browsers"]

    def test_all_categories_present(self):
        apps = [_app(f"App{i}", cat) for i, cat in enumerate(CATEGORY_ORDER)]
        groups = group_by_category(apps)
        assert list(groups.keys()) == CATEGORY_ORDER
