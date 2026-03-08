"""CLI entry point."""
from pathlib import Path

import click

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
from shhhhhh.display import (
    print_logo,
    print_tagline,
    print_summary,
    print_app_table,
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


@click.group()
def main():
    """shh — silence your mac, app by app."""
    pass


@main.command("list")
def list_cmd():
    """Show all apps and their notification settings."""
    apps = read_apps(PLIST_PATH)
    print_logo()
    print_tagline()
    print_summary(apps)
    print_app_table(apps)
    console.print()


def _toggle_command(setting: str):
    """Create an on/off toggle command for a setting."""
    bit = BIT_MAP[setting]

    @click.command(setting)
    @click.argument("state", type=click.Choice(["on", "off"]))
    @click.argument("apps", nargs=-1)
    @click.option("--all", "all_apps", is_flag=True, help="Apply to all apps")
    @click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
    def cmd(state, apps, all_apps, yes):
        enabled = state == "on"
        action = "Enabled" if enabled else "Disabled"
        setting_label = setting

        app_list = read_apps(PLIST_PATH)

        if all_apps:
            targets = app_list
        elif apps:
            targets = _match_apps(app_list, apps)
        else:
            raise click.UsageError("Specify app names or use --all")

        if not targets:
            console.print()
            console.print("  No apps matched", style="color(243)")
            console.print()
            return

        # Filter to apps that would actually change
        changes = [a for a in targets if a.sound != enabled] if bit == SOUND_BIT else [a for a in targets if a.badges != enabled]

        if not changes:
            print_logo()
            print_result(f"All {len(targets)} apps already have {setting_label} {'on' if enabled else 'off'}")
            return

        if all_apps and not yes:
            click.confirm(
                f"  {action} {setting_label} for {len(changes)} apps?",
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
            msg = f"{action} {setting_label} for {len(changes)} apps"

        print_logo()
        undo = f"shh {setting} {'on' if not enabled else 'off'} --all" if all_apps else None
        print_result(msg, undo)

    return cmd


main.add_command(_toggle_command("sound"))
main.add_command(_toggle_command("badges"))


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
