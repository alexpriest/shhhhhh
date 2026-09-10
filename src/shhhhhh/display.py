"""Terminal display: logo, tables, status output."""
from rich.console import Console
from rich.table import Table
from rich.text import Text

from shhhhhh.plist import AppInfo


def _on(app: AppInfo) -> Text:
    return Text("●", style="green") if app.allowed else Text("○", style="color(240)")


def _style(app: AppInfo) -> Text:
    return Text(app.style, style="color(250)" if app.style != "off" else "color(240)")


def _check(enabled: bool) -> Text:
    return Text("✓", style="green") if enabled else Text("✗", style="color(240)")

console = Console()

LOGO_LINES = [
    " ███████╗██╗  ██╗██╗  ██╗",
    " ██╔════╝██║  ██║██║  ██║",
    " ███████╗███████║███████║",
    " ╚════██║██╔══██║██╔══██║",
    " ███████║██║  ██║██║  ██║",
    " ╚══════╝╚═╝  ╚═╝╚═╝  ╚═╝",
]

# Grayscale gradient: bright -> dim (like sound fading)
GRAYS = [
    "color(250)",
    "color(248)",
    "color(245)",
    "color(243)",
    "color(240)",
    "color(238)",
]


def print_logo():
    """Print the gradient SHH logo."""
    console.print()
    for line, color in zip(LOGO_LINES, GRAYS):
        console.print(line, style=color, highlight=False)


def print_tagline():
    """Print the tagline below the logo."""
    console.print()
    console.print("  silence your mac, app by app", style="color(243)")


def print_summary(apps: list[AppInfo]):
    """Print the summary stats line."""
    total = len(apps)
    with_sound = sum(1 for a in apps if a.sound)
    with_badges = sum(1 for a in apps if a.badges)
    allowed = sum(1 for a in apps if a.allowed)
    console.print()
    console.print(
        f"  {total} apps · {allowed} on · {with_sound} with sound · {with_badges} with badges",
        style="color(245)",
    )


def print_app_table(apps: list[AppInfo]):
    """Print the app status table."""
    table = Table(
        show_header=True,
        header_style="bold color(250)",
        box=None,
        padding=(0, 2),
        pad_edge=True,
    )
    table.add_column("App", style="color(250)", min_width=28)
    table.add_column("On", justify="center", min_width=4)
    table.add_column("Style", min_width=10)
    table.add_column("Badges", justify="center", min_width=7)
    table.add_column("Sound", justify="center", min_width=7)

    for app in apps:
        table.add_row(app.name, _on(app), _style(app), _check(app.badges), _check(app.sound))

    console.print()
    console.print(table)


def print_grouped_table(groups: dict[str, list[AppInfo]]):
    """Print apps grouped by category with styled headers."""
    table = Table(
        show_header=True,
        header_style="bold color(250)",
        box=None,
        padding=(0, 2),
        pad_edge=True,
    )
    table.add_column("App", style="color(250)", min_width=28)
    table.add_column("On", justify="center", min_width=4)
    table.add_column("Style", min_width=10)
    table.add_column("Badges", justify="center", min_width=7)
    table.add_column("Sound", justify="center", min_width=7)

    first = True
    for category, apps in groups.items():
        if not first:
            table.add_row("", "", "", "", "")  # spacer
        first = False
        table.add_row(Text(category.upper(), style="bold color(245)"), Text(""), Text(""), Text(""), Text(""))
        for app in apps:
            table.add_row(f"  {app.name}", _on(app), _style(app), _check(app.badges), _check(app.sound))

    console.print()
    console.print(table)


def print_category_summary(groups: dict[str, list[AppInfo]]):
    """Print category overview: name, app count, sound/badge status."""
    table = Table(
        show_header=True,
        header_style="bold color(250)",
        box=None,
        padding=(0, 2),
        pad_edge=True,
    )
    table.add_column("Category", style="color(250)", min_width=14)
    table.add_column("Apps", justify="right", min_width=5)
    table.add_column("Sound On", justify="right", min_width=9)
    table.add_column("Badges On", justify="right", min_width=10)

    for category, apps in groups.items():
        count = len(apps)
        sound_on = sum(1 for a in apps if a.sound)
        badges_on = sum(1 for a in apps if a.badges)
        table.add_row(
            category,
            str(count),
            f"{sound_on}/{count}",
            f"{badges_on}/{count}",
        )

    console.print()
    console.print(table)


def print_result(message: str, undo_hint: str | None = None):
    """Print a result message after a change."""
    console.print()
    console.print(f"  {message}", style="bold color(250)")
    if undo_hint:
        console.print()
        console.print(f"  To undo: {undo_hint}", style="color(243)")
    console.print()
