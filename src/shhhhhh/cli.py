"""CLI entry point."""
from pathlib import Path

import click

from shhhhhh.categories import group_by_category, CATEGORY_ORDER
from shhhhhh.plist import (
    PLIST_PATH as _PLIST_PATH,
    SOUND_BIT,
    BADGES_BIT,
    read_apps,
    set_flag,
    write_apps,
    backup_plist,
    get_latest_backup,
    restore_backup,
)
from shhhhhh.permissions import check_access, prompt_open_settings
from shhhhhh.display import (
    print_logo,
    print_tagline,
    print_summary,
    print_app_table,
    print_grouped_table,
    print_category_summary,
    print_result,
    console,
)

# Module-level so tests can patch
PLIST_PATH = _PLIST_PATH
BACKUP_DIR = Path.home() / ".shh"

BIT_MAP = {
    "sound": SOUND_BIT,
    "badges": BADGES_BIT,
}


def _match_apps(apps, names):
    """Match app names using case-insensitive substring."""
    matched = []
    for name in names:
        found = [a for a in apps if name.lower() in a.name.lower()]
        matched.extend(found)
    return list({a.index: a for a in matched}.values())  # dedupe by index


def _apply_toggle(targets, bit, enabled, setting, confirm_all=False, yes=False):
    """Apply a sound/badges toggle to a list of target apps."""
    action = "Enabled" if enabled else "Disabled"

    # Filter to apps that would actually change
    if bit == SOUND_BIT:
        changes = [a for a in targets if a.sound != enabled]
    else:
        changes = [a for a in targets if a.badges != enabled]

    if not changes:
        print_logo()
        print_result(f"All {len(targets)} apps already have {setting} {'on' if enabled else 'off'}")
        return

    if confirm_all and not yes:
        click.confirm(
            f"  {action} {setting} for {len(changes)} apps?",
            abort=True,
        )

    backup_plist(PLIST_PATH, BACKUP_DIR)

    updates = {a.index: set_flag(a.flags, bit, enabled) for a in changes}
    write_apps(PLIST_PATH, updates)

    if setting == "sound" and not enabled:
        msg = f"Muted {len(changes)} apps"
    elif setting == "sound" and enabled:
        msg = f"Unmuted {len(changes)} apps"
    else:
        msg = f"{action} {setting} for {len(changes)} apps"

    print_logo()
    print_result(msg)


@click.group(invoke_without_command=True)
@click.pass_context
def main(ctx):
    """shh — silence your mac, app by app."""
    if ctx.invoked_subcommand is not None:
        if not check_access(PLIST_PATH):
            prompt_open_settings()
            ctx.exit(0)


@main.command("list")
@click.option("--flat", is_flag=True, help="Flat alphabetical list")
def list_cmd(flat):
    """Show all apps and their notification settings."""
    apps = read_apps(PLIST_PATH)
    print_logo()
    print_tagline()
    print_summary(apps)
    if flat:
        print_app_table(apps)
    else:
        groups = group_by_category(apps)
        print_grouped_table(groups)
    console.print()


def _toggle_command(setting: str):
    """Create an on/off toggle command for a setting."""
    bit = BIT_MAP[setting]

    @click.command(setting)
    @click.argument("state", type=click.Choice(["on", "off"]))
    @click.argument("apps", nargs=-1)
    @click.option("--all", "all_apps", is_flag=True, help="Apply to all apps")
    @click.option("--category", "category_name", default=None, help="Apply to all apps in a category")
    @click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
    def cmd(state, apps, all_apps, category_name, yes):
        enabled = state == "on"
        app_list = read_apps(PLIST_PATH)

        if all_apps:
            targets = app_list
        elif category_name:
            targets = [a for a in app_list if a.category.lower() == category_name.lower()]
            if not targets:
                console.print()
                console.print(f"  No apps in category '{category_name}'", style="color(243)")
                console.print()
                valid = [c for c in CATEGORY_ORDER if any(a.category == c for a in app_list)]
                if valid:
                    console.print(f"  Categories: {', '.join(c.lower() for c in valid)}", style="color(240)")
                    console.print()
                return
        elif apps:
            targets = _match_apps(app_list, apps)
        else:
            raise click.UsageError("Specify app names, --category, or --all")

        if not targets:
            console.print()
            console.print("  No apps matched", style="color(243)")
            console.print()
            return

        _apply_toggle(targets, bit, enabled, setting, confirm_all=all_apps or bool(category_name), yes=yes)

    return cmd


main.add_command(_toggle_command("sound"))
main.add_command(_toggle_command("badges"))


@main.group()
def category():
    """Manage apps by category."""
    pass


@category.command("list")
def category_list():
    """Show categories with app counts and status."""
    apps = read_apps(PLIST_PATH)
    groups = group_by_category(apps)
    print_logo()
    print_category_summary(groups)
    console.print()


@category.command("mute")
@click.argument("name")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
def category_mute(name, yes):
    """Mute all apps in a category."""
    app_list = read_apps(PLIST_PATH)
    targets = [a for a in app_list if a.category.lower() == name.lower()]
    if not targets:
        console.print()
        console.print(f"  No apps in category '{name}'", style="color(243)")
        console.print()
        return
    _apply_toggle(targets, SOUND_BIT, False, "sound", confirm_all=True, yes=yes)


@category.command("unmute")
@click.argument("name")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
def category_unmute(name, yes):
    """Unmute all apps in a category."""
    app_list = read_apps(PLIST_PATH)
    targets = [a for a in app_list if a.category.lower() == name.lower()]
    if not targets:
        console.print()
        console.print(f"  No apps in category '{name}'", style="color(243)")
        console.print()
        return
    _apply_toggle(targets, SOUND_BIT, True, "sound", confirm_all=True, yes=yes)


@main.command()
def undo():
    """Restore the most recent backup."""
    backup = get_latest_backup(BACKUP_DIR)
    if not backup:
        console.print()
        console.print("  No backups found", style="color(243)")
        console.print()
        return

    restore_backup(backup, PLIST_PATH)
    print_logo()
    print_result("Restored from backup", f"backup: {backup.name}")
