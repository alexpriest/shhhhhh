"""CLI entry point."""
from pathlib import Path

import click

from shhhhhh.categories import group_by_category, CATEGORY_ORDER
from shhhhhh.plist import (
    PLIST_PATH as _PLIST_PATH,
    SOUND_BIT,
    BADGES_BIT,
    ALLOW_BIT,
    STYLES,
    read_apps,
    set_center,
    set_flag,
    set_lock_screen,
    set_style,
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
    "allow": ALLOW_BIT,
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
    changes = [a for a in targets if bool(a.flags & (1 << bit)) != enabled]

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
    elif setting == "allow":
        msg = f"Notifications {'on' if enabled else 'off'} for {len(changes)} apps"
    else:
        msg = f"{action} {setting} for {len(changes)} apps"

    print_logo()
    print_result(msg, "shh undo")


@click.group(invoke_without_command=True)
@click.pass_context
def main(ctx):
    """shh — silence your mac, app by app."""
    if ctx.invoked_subcommand is not None:
        if not check_access(PLIST_PATH):
            prompt_open_settings()
            ctx.exit(0)
    elif ctx.invoked_subcommand is None:
        if not check_access(PLIST_PATH):
            prompt_open_settings()
            ctx.exit(0)
            return
        apps = read_apps(PLIST_PATH)
        from shhhhhh.interactive import ShhApp
        shh_app = ShhApp(apps, PLIST_PATH, BACKUP_DIR)
        shh_app.run()
        if shh_app.applied:
            print_logo()
            changes = len([
                a for a in apps
                if shh_app.original[a.index] != shh_app.staged[a.index]
            ])
            print_result(f"Applied {changes} change{'s' if changes != 1 else ''}", "shh undo")


@main.command("list")
@click.option("--flat", is_flag=True, help="Flat alphabetical list")
@click.option("--system", "with_system", is_flag=True, help="Include Apple system daemons and agents")
def list_cmd(flat, with_system):
    """Show all apps and their notification settings."""
    everything = read_apps(PLIST_PATH)
    apps = everything if with_system else [a for a in everything if not a.system]
    print_logo()
    print_tagline()
    print_summary(apps)
    hidden = len(everything) - len(apps)
    if hidden:
        console.print(f"  {hidden} Apple system entries hidden · add --system to include them", style="color(240)")
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
main.add_command(_toggle_command("allow"))


def _shown_command(name: str, label: str, getter, setter):
    """on/off command for the inverted-bit settings (Notification Center, Lock Screen)."""

    @click.command(name)
    @click.argument("state", type=click.Choice(["on", "off"]))
    @click.argument("apps", nargs=-1)
    @click.option("--all", "all_apps", is_flag=True, help="Apply to all apps")
    @click.option("--category", "category_name", default=None, help="Apply to all apps in a category")
    @click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
    def cmd(state, apps, all_apps, category_name, yes):
        shown = state == "on"
        app_list = read_apps(PLIST_PATH)
        if all_apps:
            targets = app_list
        elif category_name:
            targets = [a for a in app_list if a.category.lower() == category_name.lower()]
        elif apps:
            targets = _match_apps(app_list, apps)
        else:
            raise click.UsageError("Specify app names, --category, or --all")
        if not targets:
            console.print()
            console.print("  No apps matched", style="color(243)")
            console.print()
            return
        changes = [a for a in targets if getter(a) != shown]
        if not changes:
            print_logo()
            print_result(f"All {len(targets)} apps already {'shown' if shown else 'hidden'} {label}")
            return
        if (all_apps or category_name) and not yes:
            click.confirm(f"  {'Show' if shown else 'Hide'} {len(changes)} apps {label}?", abort=True)
        backup_plist(PLIST_PATH, BACKUP_DIR)
        write_apps(PLIST_PATH, {a.index: setter(a.flags, shown) for a in changes})
        print_logo()
        print_result(f"{'Shown' if shown else 'Hidden'} {label} for {len(changes)} apps", "shh undo")

    cmd.help = f"Show or hide notifications {label}."
    return cmd


main.add_command(_shown_command("center", "in Notification Center", lambda a: a.center, set_center))
main.add_command(_shown_command("lockscreen", "on the Lock Screen", lambda a: a.lock_screen, set_lock_screen))


@main.command("uninstall")
@click.argument("app")
@click.option("--dry-run", is_flag=True, help="List what would be trashed and stop")
@click.option("--keep-files", is_flag=True, help="Trash the .app only; leave its Library files")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
def uninstall_cmd(app, dry_run, keep_files, yes):
    """Move an app and its Library leftovers to the Trash, and forget its notifications."""
    from shhhhhh.uninstall import UninstallError, execute, human_size, plan_uninstall, remove_from_plist

    matches = _match_apps(read_apps(PLIST_PATH), [app])
    exact = [a for a in matches if a.name.lower() == app.lower()]
    matches = exact or matches
    if not matches:
        console.print()
        console.print("  No apps matched", style="color(243)")
        console.print()
        return
    if len(matches) > 1:
        console.print()
        console.print(f"  Be specific — matched: {', '.join(a.name for a in matches)}", style="color(243)")
        console.print()
        return
    plan = plan_uninstall(matches[0])
    if plan.blocked:
        console.print()
        console.print(f"  {plan.app.name}: {plan.blocked}", style="color(243)")
        console.print()
        return
    plan.keep_files = keep_files
    home = str(Path.home())
    console.print()
    if plan.gone:
        console.print(f"  {plan.app.name} — the .app is already gone; forgetting its notification entry", style="bold color(250)")
    else:
        console.print(f"  {plan.app.name} — {len(plan.targets)} items, {human_size(plan.size)}", style="bold color(250)")
    for path in plan.targets:
        console.print(f"    {str(path).replace(home, '~')}", style="color(245)")
    if keep_files and len(plan.paths) > len(plan.targets):
        console.print(f"    (keeping {len(plan.paths) - len(plan.targets)} Library items)", style="color(240)")
    if plan.needs_admin:
        console.print("  Owned by root (an App Store install): the Finder will move it and ask for your password.", style="color(178)")
    console.print()
    if plan.running:
        console.print(f"  {plan.app.name} is running — quit it first", style="color(243)")
        console.print()
        return
    if dry_run:
        return
    if not yes:
        click.confirm("  Move all of it to the Trash?", abort=True)
    try:
        execute(plan)
    except UninstallError as exc:
        console.print()
        console.print(f"  Stopped — {exc}", style="color(178)")
        if exc.moved:
            console.print(f"  Already in the Trash: {', '.join(p.name for p in exc.moved)}; the rest untouched.", style="color(243)")
        console.print()
        return
    backup_plist(PLIST_PATH, BACKUP_DIR)
    remove_from_plist(PLIST_PATH, plan.app.bundle_id)
    print_logo()
    print_result(f"{plan.app.name} moved to the Trash", "put it back from the Finder's Trash")


@main.command("sweep")
@click.argument("bundle_id")
@click.option("--dry-run", is_flag=True, help="List what would be trashed and stop")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
def sweep_cmd(bundle_id, dry_run, yes):
    """Trash the Library leftovers of an app that is already gone, by bundle id."""
    from shhhhhh.uninstall import UninstallError, UninstallPlan, execute, human_size, library_leftovers
    from shhhhhh.plist import AppInfo

    if bundle_id.startswith("com.apple."):
        console.print()
        console.print("  Apple system software — leave it to Apple", style="color(243)")
        console.print()
        return
    name = bundle_id.rsplit(".", 1)[-1]
    paths = library_leftovers(bundle_id, name)
    if not paths:
        console.print()
        console.print(f"  Nothing left for {bundle_id}", style="color(243)")
        console.print()
        return
    plan = UninstallPlan(app=AppInfo(name=name, bundle_id=bundle_id, flags=0, index=-1), paths=paths)
    home = str(Path.home())
    console.print()
    console.print(f"  {bundle_id} — {len(paths)} items, {human_size(plan.size)}", style="bold color(250)")
    for path in paths:
        console.print(f"    {str(path).replace(home, '~')}", style="color(245)")
    console.print()
    if dry_run:
        return
    if not yes:
        click.confirm("  Move all of it to the Trash?", abort=True)
    try:
        # No .app in this plan, so the "app last" ordering has nothing to protect.
        plan.paths = [paths[0]] + paths[1:]
        execute(plan)
    except UninstallError as exc:
        console.print()
        console.print(f"  Stopped — {exc}", style="color(178)")
        console.print()
        return
    print_logo()
    print_result(f"Swept {len(paths)} items to the Trash", "put them back from the Finder's Trash")


@main.command("style")
@click.argument("style", type=click.Choice(STYLES))
@click.argument("apps", nargs=-1)
@click.option("--all", "all_apps", is_flag=True, help="Apply to all apps")
@click.option("--category", "category_name", default=None, help="Apply to all apps in a category")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
def style_cmd(style, apps, all_apps, category_name, yes):
    """Set the alert style: temporary (banner), persistent (stays), or off."""
    app_list = read_apps(PLIST_PATH)
    if all_apps:
        targets = app_list
    elif category_name:
        targets = [a for a in app_list if a.category.lower() == category_name.lower()]
    elif apps:
        targets = _match_apps(app_list, apps)
    else:
        raise click.UsageError("Specify app names, --category, or --all")

    if not targets:
        console.print()
        console.print("  No apps matched", style="color(243)")
        console.print()
        return

    changes = [a for a in targets if a.style != style]
    if not changes:
        print_logo()
        print_result(f"All {len(targets)} apps already {style}")
        return

    if (all_apps or category_name) and not yes:
        click.confirm(f"  Set alert style to {style} for {len(changes)} apps?", abort=True)

    backup_plist(PLIST_PATH, BACKUP_DIR)
    write_apps(PLIST_PATH, {a.index: set_style(a.flags, style) for a in changes})
    print_logo()
    print_result(f"Set {len(changes)} apps to {style}", "shh undo")


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
