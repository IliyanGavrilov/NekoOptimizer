# What search engines and link previews read off a page: its title and description, the
# one URL it is filed under, and the structured data behind rich results. Titles lead with
# the words players search ("Battle Cats ... tier list"), the brand trails.

import json
from dataclasses import dataclass

from django.conf import settings
from django.utils.safestring import mark_safe

BRAND = "Neko Optimizer"

# json.dumps leaves these alone, and inside a <script> a "</script>" would end it early.
_SCRIPT_SAFE = str.maketrans({"<": "\\u003c", ">": "\\u003e", "&": "\\u0026"})


@dataclass(frozen=True, slots=True)
class PageMeta:
    """A page's search listing, and whether to keep it out of the index altogether."""

    title: str
    description: str
    noindex: bool = False


DEFAULT_META = PageMeta(
    BRAND,
    "Free Battle Cats gacha planner: track your seed, see every upcoming roll and get the "
    "cheapest path in tickets and catfood to the Ubers you want.",
)

PAGE_META = {
    "planner": PageMeta(
        f"Battle Cats Gacha Planner & Seed Tracker | {BRAND}",
        "Plan your Battle Cats rare gacha pulls from your seed: every upcoming roll on both "
        "tracks, and the cheapest path in tickets and catfood to the Ubers you want.",
    ),
    "normal_capsules": PageMeta(
        f"Battle Cats Normal Capsule Seed Tracker | {BRAND}",
        "Predict the Battle Cats Normal Cat Capsule from your normal seed: the Catfruit, "
        "Catseye and Lucky Ticket machines in one table, with the pulls worth taking.",
    ),
    "collection": PageMeta(
        f"Battle Cats Cat Guide & Collection Tracker | {BRAND}",
        "Track every Battle Cats unit you own and want in Cat Guide order. Import your "
        "collection from in-game screenshots and filter by abilities, combos and talents.",
    ),
    "resources": PageMeta(
        f"Battle Cats Evolution, Talent & Cannon Calculator | {BRAND}",
        "Total the catfruit, behemoth stones, XP, NP and cannon materials you need to evolve "
        "your Battle Cats units, unlock their talents and build your Cat Base cannons.",
    ),
    "tier_list": PageMeta(
        f"Battle Cats Uber Tier List: Best Ubers & Legend Rares | {BRAND}",
        "Every permanent Battle Cats Uber and Legend Rare ranked tier by tier, with Ultra "
        "Form and Ultra Talent placements - plus a tier list for every gacha set.",
    ),
    "seed_finder": PageMeta(
        f"Battle Cats Seed Finder: Find Your Gacha Seed | {BRAND}",
        "Don't know your Battle Cats seed? Enter the cats from a few rolls and the finder "
        "checks all 4.3 billion seeds in your browser for the one that matches.",
    ),
    "guides": PageMeta(
        f"Battle Cats Gacha Guides: Seeds, Tracks & Planning | {BRAND}",
        "Step-by-step Battle Cats guides: find your gacha seed, read the A/B roll tracks, "
        "plan your pulls for the Ubers you want and predict the Normal Capsules.",
    ),
    "about": PageMeta(
        f"About | {BRAND}",
        "Who built Neko Optimizer, the tech behind its Battle Cats gacha planner, and the "
        "community tools and data it credits.",
    ),
    "signup": PageMeta(f"Sign up | {BRAND}", DEFAULT_META.description, noindex=True),
    "login": PageMeta(f"Log in | {BRAND}", DEFAULT_META.description, noindex=True),
}

# The how-to guides by slug, in reading order; each body is planner/guides/<slug>.html.
GUIDES = {
    "find-your-seed": PageMeta(
        f"How to Find Your Battle Cats Seed (Step by Step) | {BRAND}",
        "Find your Battle Cats gacha seed from a few rolls: which banner to use, how to "
        "record your cats, the guaranteed-Uber trap, and what to do when several seeds match.",
    ),
    "read-the-tracks": PageMeta(
        f"Battle Cats Seed Tracker: How to Read Tracks A and B | {BRAND}",
        "How Battle Cats rare gacha rolls work from your seed: tracks A and B, duplicate "
        "rerolls that switch tracks, guaranteed 11-draws and how to step to the cat you want.",
    ),
    "plan-your-rolls": PageMeta(
        f"How to Plan Battle Cats Gacha Rolls for the Ubers You Want | {BRAND}",
        "Use your seed to get the Ubers you want for the fewest tickets and catfood: pick "
        "targets and banners, set your budget, follow the plan and apply it when you've rolled.",
    ),
    "normal-capsules": PageMeta(
        f"Battle Cats Normal Capsule Seed Guide: Catfruit & Catseyes | {BRAND}",
        "The Battle Cats Normal Capsules run on their own seed. Find it, predict the "
        "Catfruit, Catseye and Lucky Ticket machines, and plan your normal tickets.",
    ),
    "keep-your-seed": PageMeta(
        f"Never Lose Your Battle Cats Seed | {BRAND}",
        "Where Neko Optimizer keeps your Battle Cats seeds, how to carry them to another "
        "device, and the one-minute backup that makes losing them impossible.",
    ),
}

# The pages whose content is the game version's own (its catalogue, banners, tier
# names), so each version has a URL of its own for them. The rest - about, the guides,
# the account forms - read the same everywhere and are filed under the English URL.
REGION_PAGES = frozenset(
    {
        "planner",
        "normal_capsules",
        "collection",
        "resources",
        "tier_list",
        "tier_list_page",
        "seed_finder",
    }
)

# Each version's hreflang: the language its game data (cat and banner names) is in.
HREFLANG = {"en": "en", "jp": "ja", "tw": "zh-TW", "kr": "ko"}

# The pages worth a search listing, by URL name, for the sitemap.
INDEXED_PAGES = tuple(name for name, meta in PAGE_META.items() if not meta.noindex)


def page_meta(url_name: str | None) -> PageMeta:
    """The listing for the page a URL name resolves to; the site's own for any other."""
    return PAGE_META.get(url_name, DEFAULT_META)


def tier_set_meta(label: str) -> PageMeta:
    """The listing for one gacha set's tier list."""
    return PageMeta(
        f"Battle Cats {label} Tier List | {BRAND}",
        f"The Battle Cats {label} tier list: every unit in the set ranked tier by tier, with "
        "Ultra Form and Ultra Talent placements and each cat's forms.",
    )


def ld_json(data: dict) -> str:
    """Structured data, ready to drop into a <script type="application/ld+json">."""
    # Safe: _SCRIPT_SAFE escapes every character that could end the script or open a tag.
    return mark_safe(json.dumps(data, ensure_ascii=False).translate(_SCRIPT_SAFE))  # nosec B308 B703


def home_graph() -> dict:
    """The site and the app it is, for the home page."""
    return {
        "@context": "https://schema.org",
        "@graph": [
            {"@type": "WebSite", "name": BRAND, "url": f"{settings.SITE_URL}/"},
            {
                "@type": "WebApplication",
                "name": BRAND,
                "url": f"{settings.SITE_URL}/",
                "description": PAGE_META["planner"].description,
                "applicationCategory": "GameApplication",
                "operatingSystem": "Any",
                "browserRequirements": "Requires JavaScript and WebAssembly",
                "offers": {"@type": "Offer", "price": "0", "priceCurrency": "USD"},
            },
        ],
    }


def breadcrumbs(*trail: tuple[str, str]) -> dict:
    """A breadcrumb trail of (name, path) pairs, home first."""
    return {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {
                "@type": "ListItem",
                "position": position,
                "name": name,
                "item": f"{settings.SITE_URL}{path}",
            }
            for position, (name, path) in enumerate(trail, 1)
        ],
    }
