"""App category detection and grouping."""
from pathlib import Path
import plistlib

# Consolidated category names
MESSAGING = "Messaging"
EMAIL = "Email"
WORK = "Work"
DEVELOPER = "Developer"
MEDIA = "Media"
BROWSERS = "Browsers"
UTILITIES = "Utilities"
OTHER = "Other"

CATEGORY_ORDER = [MESSAGING, EMAIL, WORK, DEVELOPER, BROWSERS, MEDIA, UTILITIES, OTHER]

# Map Apple UTI category strings to consolidated groups
UTI_MAP: dict[str, str] = {
    "public.app-category.social-networking": MESSAGING,
    "public.app-category.business": WORK,
    "public.app-category.productivity": WORK,
    "public.app-category.finance": WORK,
    "public.app-category.education": WORK,
    "public.app-category.developer-tools": DEVELOPER,
    "public.app-category.entertainment": MEDIA,
    "public.app-category.music": MEDIA,
    "public.app-category.video": MEDIA,
    "public.app-category.photography": MEDIA,
    "public.app-category.games": MEDIA,
    "public.app-category.graphics-design": WORK,
    "public.app-category.utilities": UTILITIES,
    "public.app-category.lifestyle": UTILITIES,
    "public.app-category.weather": UTILITIES,
    "public.app-category.healthcare-fitness": UTILITIES,
    "public.app-category.health-and-fitness": UTILITIES,
    "public.app-category.travel": UTILITIES,
    "public.app-category.food-and-drink": UTILITIES,
    "public.app-category.sports": UTILITIES,
    "public.app-category.news": UTILITIES,
    "public.app-category.reference": UTILITIES,
    "public.app-category.medical": UTILITIES,
}

# Bundle ID overrides for known misses and bad categorizations
OVERRIDES: dict[str, str] = {
    # Browsers
    "com.google.Chrome": BROWSERS,
    "com.google.Chrome.canary": BROWSERS,
    "com.apple.Safari": BROWSERS,
    "org.mozilla.firefox": BROWSERS,
    "org.mozilla.firefoxdeveloperedition": BROWSERS,
    "company.thebrowser.Browser": BROWSERS,  # Arc
    "com.operasoftware.Opera": BROWSERS,
    "com.vivaldi.Vivaldi": BROWSERS,
    "com.brave.Browser": BROWSERS,
    "com.microsoft.edgemac": BROWSERS,
    # Messaging (miscategorized or missing)
    "com.hnc.Discord": MESSAGING,  # Apple says Developer Tools
    "com.tinyspeck.slackmacgap": MESSAGING,
    "ru.keepcoder.Telegram": MESSAGING,
    "net.whatsapp.WhatsApp": MESSAGING,
    "com.facebook.archon": MESSAGING,  # Messenger
    "org.signal.Signal": MESSAGING,
    "us.zoom.xos": MESSAGING,
    "com.microsoft.teams2": MESSAGING,
    # Email
    "com.apple.mail": EMAIL,
    "com.readdle.smartemail-macos": EMAIL,  # Spark
    "com.freron.MailMate": EMAIL,
    "com.mimestream.Mimestream": EMAIL,
    "com.superhuman.electron": EMAIL,
    # Work (miscategorized or missing)
    "com.figma.Desktop": WORK,
    "com.linear": WORK,
    "com.notion.id": WORK,
    "com.openai.chat": WORK,
    "com.electron.loom": WORK,
    "com.1password.1password": UTILITIES,
    # Media (missing)
    "com.spotify.client": MEDIA,
}


def resolve_category(bundle_id: str, app_path: str) -> str:
    """Resolve an app's category from override map, Info.plist, or fallback."""
    if bundle_id in OVERRIDES:
        return OVERRIDES[bundle_id]

    if app_path and app_path.endswith(".app"):
        try:
            info_plist = Path(app_path) / "Contents" / "Info.plist"
            with open(info_plist, "rb") as f:
                info = plistlib.load(f)
            uti = info.get("LSApplicationCategoryType", "")
            if uti in UTI_MAP:
                return UTI_MAP[uti]
        except Exception:
            pass

    return OTHER


def group_by_category(apps: list) -> dict[str, list]:
    """Group apps by category, ordered by CATEGORY_ORDER. Each group sorted alphabetically."""
    groups: dict[str, list] = {}
    for app in apps:
        cat = getattr(app, "category", OTHER)
        groups.setdefault(cat, []).append(app)

    # Sort apps within each group
    for cat in groups:
        groups[cat].sort(key=lambda a: a.name.lower())

    # Return in CATEGORY_ORDER, omitting empty categories
    return {cat: groups[cat] for cat in CATEGORY_ORDER if cat in groups}
