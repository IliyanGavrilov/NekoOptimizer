# The community tools we point at rather than scrape. They are calculators, trackers and
# wikis, not data feeds - nothing here is fetched or committed, so a link is the whole
# integration: a curated few per page, plus the per-unit deep links the cat popup shows.

from dataclasses import dataclass

from planner.services import wiki_url

# battlecatsinfo's unit page takes the same unit id the catalogue and its icons use.
INFO_UNIT = "https://battlecatsinfo.github.io/unit.html?id={unit_id}"
# battlecatsstats numbers its units from 1, so its id is ours plus one; the trailing
# segment is the form, and 0 (the base form) is the one every unit has.
STATS_UNIT = "https://battlecatsstats.com/unit/{unit_id}/0"


@dataclass(frozen=True, slots=True)
class Link:
    """One outbound link: what to call it, where it goes, and what it's good for."""

    label: str
    url: str
    note: str = ""


GODFAT = Link(
    "godfat's seed tracker",
    "https://bc.godfat.org/",
    "The canonical tracker; our roll engine is validated against it.",
)
AMPURI = Link(
    "Normal Cat seed tracking",
    "https://ampuri.github.io/bc-normal-seed-tracking/",
    "A tracker built around the Normal Capsule pools.",
)
TRACKER_UTIL = Link(
    "BC Seed Tracker Util",
    "https://greasyfork.org/en/scripts/480239-bc-seed-tracker-util",
    "Userscript overlaying godfat with paths to the cats you want.",
)
FEANOR = Link(
    "thanksfeanor",
    "https://thanksfeanor.pythonanywhere.com/",
    "A hosted grab-bag of Battle Cats utilities.",
)
INFO = Link(
    "battlecatsinfo",
    "https://battlecatsinfo.github.io/",
    "All-in-one unit database, stage info and calculators.",
)
INFO_GACHA = Link(
    "battlecatsinfo: Gacha",
    "https://battlecatsinfo.github.io/gachas.html",
    "Every banner's pool and per-unit drop odds.",
)
INFO_GUIDE = Link(
    "battlecatsinfo: Cat Guide",
    "https://battlecatsinfo.github.io/cat_guide.html",
    "The picture-book listing, in the game's own order.",
)
INFO_COMPARE = Link(
    "battlecatsinfo: Cat Comparison",
    "https://battlecatsinfo.github.io/compare.html",
    "Line up two cats' stats side by side.",
)
INFO_OTOTO = Link(
    "battlecatsinfo: Ototo",
    "https://battlecatsinfo.github.io/ototo.html",
    "Cat Cannon recipes and upgrade costs.",
)
INFO_MATERIALS = Link(
    "battlecatsinfo: Materials",
    "https://battlecatsinfo.github.io/materials.html",
    "Which stages drop which evolution materials.",
)
INFO_TREASURES = Link(
    "battlecatsinfo: Treasures",
    "https://battlecatsinfo.github.io/treasure_list.html",
    "Treasure locations and the stat bonuses they carry.",
)
STATS = Link(
    "battlecatsstats",
    "https://battlecatsstats.com/",
    "True-damage and DPS calculators, range graphs, matchups.",
)
MARKS = Link(
    "Stat calculator",
    "https://production.matthewmarks.com/battle-cats-stat-calculator/",
    "Level-by-level stat breakdowns.",
)
STATS_TOOL = Link(
    "Cat Stats Tool",
    "https://battlecats.miraheze.org/wiki/Cat_Stats_Tool",
    "The wiki's own filterable stat table, with form and talent toggles.",
)
TIER_SITE = Link(
    "The Battle Cats Tier List",
    "https://www.battlecatstierlist.com/",
    "Where our rankings come from - plus DPS graphs and matchup charts.",
)
UPCOMING = Link(
    "Upcoming events",
    "https://docs.google.com/document/d/1ENv1edzJAcsmk3gjLpvhqVFxoQ4Lpde1K5dRTNxH8sA/edit",
    "Community-maintained schedule of banners still to come.",
)
GAMATOTO = Link(
    "mygamatoto",
    "https://mygamatoto.com/",
    "Account and collection manager with an event calendar.",
)
CALC = Link(
    "battlecats-calc",
    "https://battlecats-calc.com/",
    "Tick off the cats you own and browse them as a set.",
)
WIKI = Link(
    "The Battle Cats Wiki",
    "https://battlecats.miraheze.org/",
    "The Miraheze wiki every other tool links back to.",
)
ART_ARCHIVE = Link(
    "Uber & collab art archive",
    "https://drive.google.com/drive/folders/12Iu_dv8AZWfU3ekRoA_km0dbJA9klNdC",
    "Community gallery of every Uber, collabs included.",
)

_TIER_LINKS = (TIER_SITE, STATS, INFO_COMPARE)

# Keyed by URL name, so a page picks up its links without the view knowing about them.
PAGE_LINKS = {
    "planner": (GODFAT, INFO_GACHA, UPCOMING),
    "normal_capsules": (AMPURI, GODFAT),
    "collection": (GAMATOTO, CALC, INFO_GUIDE),
    "materials": (INFO_OTOTO, INFO_MATERIALS, INFO_TREASURES),
    "tier_list": _TIER_LINKS,
    "tier_list_page": _TIER_LINKS,
    "seed_finder": (GODFAT, AMPURI, TRACKER_UTIL),
}

# The full directory, for the About page.
TOOL_DIRECTORY = (
    ("Seed trackers", (GODFAT, AMPURI, TRACKER_UTIL, FEANOR)),
    ("Stats, calculators & databases", (INFO, STATS, STATS_TOOL, MARKS)),
    ("Tier lists", (TIER_SITE,)),
    ("Schedules & collections", (UPCOMING, GAMATOTO, CALC)),
    ("Wikis & assets", (WIKI, ART_ARCHIVE)),
)


def unit_links(unit_id: int, name: str, rarity: str = "") -> list[Link]:
    """Where to read up on one catalogue unit, for the cat popup."""
    return [
        Link("Battle Cats Wiki", wiki_url(name, rarity), "Full page: forms, talents, lore."),
        Link("battlecatsinfo", INFO_UNIT.format(unit_id=unit_id), "Stats, animations, drop rates."),
        Link("battlecatsstats", STATS_UNIT.format(unit_id=unit_id + 1), "DPS and matchup graphs."),
    ]
