# Display text for the labels the engine package (neko) and the committed stats spell in
# English. neko stays free of Django, so its labels are declared here for makemessages
# (gettext_noop) and translated where a page shows them; the values stay English, since
# the facet filters and CSS key off them.

import re

from django.utils.translation import gettext, gettext_noop, pgettext_lazy

RARITIES = (
    gettext_noop("Normal"),
    gettext_noop("Special"),
    gettext_noop("Rare"),
    gettext_noop("Super Rare"),
    gettext_noop("Uber Super Rare"),
    gettext_noop("Legend Rare"),
    gettext_noop("Unknown"),
)

# The Rolls cells' short rarity labels. Translated in context: "Legend" alone is also the
# track guide's heading.
SHORT_RARITIES = (
    pgettext_lazy("short rarity", "Rare"),
    pgettext_lazy("short rarity", "Super"),
    pgettext_lazy("short rarity", "Uber"),
    pgettext_lazy("short rarity", "Legend"),
)

TARGETS = (
    gettext_noop("Red"),
    gettext_noop("Floating"),
    gettext_noop("Black"),
    gettext_noop("Metal"),
    gettext_noop("Angel"),
    gettext_noop("Alien"),
    gettext_noop("Zombie"),
    gettext_noop("Relic"),
    gettext_noop("Aku"),
    gettext_noop("Traitless"),
    gettext_noop("Witch"),
    gettext_noop("Eva Angel"),
)

IMMUNITIES = (
    gettext_noop("Waves"),
    gettext_noop("Knockback"),
    gettext_noop("Freeze"),
    gettext_noop("Slow"),
    gettext_noop("Weaken"),
    gettext_noop("Curse"),
    gettext_noop("Toxic"),
    gettext_noop("Surges"),
)

ATTACKS = (
    gettext_noop("Single"),
    gettext_noop("Area"),
    gettext_noop("Long Distance"),
    gettext_noop("Omni Strike"),
)

ABILITIES = (
    gettext_noop("Multi-hit"),
    gettext_noop("Strong"),
    gettext_noop("Resistant"),
    gettext_noop("Insanely Tough"),
    gettext_noop("Massive Damage"),
    gettext_noop("Insane Damage"),
    gettext_noop("Metal"),
    gettext_noop("Attacks Only"),
    gettext_noop("Zombie Killer"),
    gettext_noop("Witch Killer"),
    gettext_noop("Eva Angel Killer"),
    gettext_noop("Colossus Slayer"),
    gettext_noop("Behemoth Slayer"),
    gettext_noop("Sage Slayer"),
    gettext_noop("Soul Strike"),
    gettext_noop("Base Destroyer"),
    gettext_noop("Extra Money"),
    gettext_noop("Wave Shield"),
    gettext_noop("Counter-surge"),
    gettext_noop("Critical"),
    gettext_noop("Savage Blow"),
    gettext_noop("Knockback"),
    gettext_noop("Freeze"),
    gettext_noop("Slow"),
    gettext_noop("Weaken"),
    gettext_noop("Curse"),
    gettext_noop("Wave"),
    gettext_noop("Mini-wave"),
    gettext_noop("Surge"),
    gettext_noop("Strengthen"),
    gettext_noop("Survive"),
    gettext_noop("Barrier Breaker"),
    gettext_noop("Shield Piercer"),
    gettext_noop("Warp"),
    gettext_noop("Dodge"),
)

# The plain ability chips of a stat block (neko.statsdata._FLAGS), worded as the chips are.
FLAGS = (
    gettext_noop("Strong"),
    gettext_noop("Resistant"),
    gettext_noop("Insanely tough"),
    gettext_noop("Massive damage"),
    gettext_noop("Insane damage"),
    gettext_noop("Metal"),
    gettext_noop("Attacks only targets"),
    gettext_noop("Zombie Killer"),
    gettext_noop("Witch Killer"),
    gettext_noop("Eva Angel Killer"),
    gettext_noop("Colossus Slayer"),
    gettext_noop("Behemoth Slayer"),
    gettext_noop("Sage Slayer"),
    gettext_noop("Soul Strike"),
    gettext_noop("Base Destroyer"),
    gettext_noop("Extra money"),
    gettext_noop("Wave Shield"),
    gettext_noop("Counter-surge"),
)

# The stat block's numbered chips (neko.statsdata._effects), each matched off its English
# wording and re-worded with the same numbers.
_EFFECTS = (
    (r"(?P<n>\d+) hits \((?P<hits>.+)\)", gettext_noop("%(n)s hits (%(hits)s)")),
    (r"Critical hit (?P<p>\d+)%", gettext_noop("Critical hit %(p)s%%")),
    (
        r"Savage blow (?P<p>\d+)% \(\+(?P<boost>\d+)%\)",
        gettext_noop("Savage blow %(p)s%% (+%(boost)s%%)"),
    ),
    (r"Knockback (?P<p>\d+)%", gettext_noop("Knockback %(p)s%%")),
    (r"Freeze (?P<p>\d+)% for (?P<t>[\d.]+)s", gettext_noop("Freeze %(p)s%% for %(t)ss")),
    (r"Slow (?P<p>\d+)% for (?P<t>[\d.]+)s", gettext_noop("Slow %(p)s%% for %(t)ss")),
    (
        r"Weaken (?P<p>\d+)% to (?P<to>\d+)% for (?P<t>[\d.]+)s",
        gettext_noop("Weaken %(p)s%% to %(to)s%% for %(t)ss"),
    ),
    (r"Curse (?P<p>\d+)% for (?P<t>[\d.]+)s", gettext_noop("Curse %(p)s%% for %(t)ss")),
    (r"Mini-wave (?P<p>\d+)% \(Lv (?P<lv>\d+)\)", gettext_noop("Mini-wave %(p)s%% (Lv %(lv)s)")),
    (r"Wave (?P<p>\d+)% \(Lv (?P<lv>\d+)\)", gettext_noop("Wave %(p)s%% (Lv %(lv)s)")),
    (
        r"Surge (?P<p>\d+)% \(Lv (?P<lv>\d+), (?P<range>-?\d+~-?\d+)\)",
        gettext_noop("Surge %(p)s%% (Lv %(lv)s, %(range)s)"),
    ),
    (r"Attack \+(?P<p>\d+)% at (?P<hp>\d+)% HP", gettext_noop("Attack +%(p)s%% at %(hp)s%% HP")),
    (r"Survives a lethal strike (?P<p>\d+)%", gettext_noop("Survives a lethal strike %(p)s%%")),
    (r"Breaks barriers (?P<p>\d+)%", gettext_noop("Breaks barriers %(p)s%%")),
    (r"Pierces shields (?P<p>\d+)%", gettext_noop("Pierces shields %(p)s%%")),
    (r"Warp (?P<p>\d+)%", gettext_noop("Warp %(p)s%%")),
    (r"Dodge (?P<p>\d+)% for (?P<t>[\d.]+)s", gettext_noop("Dodge %(p)s%% for %(t)ss")),
    (r"Omni strike (?P<range>-?\d+~-?\d+)", gettext_noop("Omni strike %(range)s")),
    (r"Long distance (?P<range>-?\d+~-?\d+)", gettext_noop("Long distance %(range)s")),
)
_EFFECT_PATTERNS = tuple((re.compile(pattern), message) for pattern, message in _EFFECTS)


def effect(text: str) -> str:
    """One stat-block chip in the interface language: a numbered one re-worded around its
    numbers, a plain one looked up whole."""
    for pattern, message in _EFFECT_PATTERNS:
        match = pattern.fullmatch(text)
        if match:
            return gettext(message) % match.groupdict()

    return gettext(text)


def stat_forms(forms: list[dict]) -> list[dict]:
    """A unit's stat blocks with their trait, ability and immunity chips translated."""
    chips = {"targets": gettext, "effects": effect, "immune": gettext}

    return [
        {
            **form,
            **{
                key: [word(text) for text in form[key]]
                for key, word in chips.items()
                if key in form
            },
            # The traits by their English names too, which the page colours them by.
            **({"trait_keys": form["targets"]} if "targets" in form else {}),
        }
        for form in forms
    ]
