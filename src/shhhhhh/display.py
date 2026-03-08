"""Terminal display: logo, tables, status output."""
from rich.console import Console
from rich.table import Table
from rich.text import Text

from shhhhhh.plist import AppInfo

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
    console.print()
    console.print(
        f"  {total} apps · {with_sound} with sound · {with_badges} with badges",
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
    table.add_column("Sound", justify="center", min_width=7)
    table.add_column("Badges", justify="center", min_width=7)

    for app in apps:
        sound = Text("✓", style="green") if app.sound else Text("✗", style="color(240)")
        badges = Text("✓", style="green") if app.badges else Text("✗", style="color(240)")
        table.add_row(app.name, sound, badges)

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
