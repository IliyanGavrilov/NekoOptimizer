# The text the page's engine (neko.wasm) renders: the Rolls table, the plans and the Normal
# Capsules tables. Every engine request carries it in the interface language, keyed by the
# English the Rust spells it in, and the reference templates translate the same strings, so
# both renderers still agree. test_engine_text.py keeps this list in step with the Rust.

from django.utils.translation import gettext, gettext_noop, ngettext, pgettext

ENGINE_TEXT = (
    # The Rolls table.
    gettext_noop("%(hits)s of them turn up in these rolls"),
    gettext_noop("&ldquo;I rolled this cell&rdquo; &mdash; jumps the seed to just after it"),
    gettext_noop(", jumps to %(to)s"),
    gettext_noop("Add future ubers"),
    gettext_noop("An uber not released yet - a stand-in for whatever joins the pool next"),
    gettext_noop(
        "An uber not released yet - a stand-in for whatever joins this banner's pool next"
    ),
    gettext_noop("Debuts with this banner &mdash; this is its first event anywhere"),
    gettext_noop("Doesn't turn up in the first %(rolls)s rolls"),
    gettext_noop(
        "Every cat you're searching for - the targets you picked, your wishlist (when that "
        "search is on), and any future ubers you've toggled - with its next spot in these "
        "rolls. Click a position to jump to its cell."
    ),
    gettext_noop(
        "Following the track dupes here: the previous pull obtains this same cat, so this "
        "cell rerolls into the branch value and jumps tracks"
    ),
    gettext_noop("Future Uber %(n)s"),
    gettext_noop("Got %(name)s here? Jump the seed to just after that reroll"),
    gettext_noop("Guaranteed"),
    gettext_noop(
        "If this guaranteed multi's first roll comes up as a dupe, it rerolls and the multi "
        "ends on a different cell - you get this uber instead"
    ),
    gettext_noop("Jump the seed to just after %(name)s"),
    gettext_noop("Jump to %(pos)s in the track"),
    gettext_noop("Legend"),
    gettext_noop("No rolls for this seed and banner selection."),
    gettext_noop(
        "Only when the arriving pull already holds this cell's cat (a bounce path, or your "
        "remembered last pull): it rerolls into the branch value and jumps tracks"
    ),
    gettext_noop(
        "Pad this banner's uber pool with expected-but-unreleased ubers (godfat's Count of "
        "future ubers) - its uber cells land as if those units were already in the pool; drag "
        "the box up/down to adjust"
    ),
    gettext_noop("Remove %(name)s from your targets"),
    gettext_noop("Remove target"),
    gettext_noop(
        "Rolled this guaranteed multi (its first roll duped)? Jump the seed to just after "
        "its final draw"
    ),
    gettext_noop("Rolled this guaranteed multi? Jump the seed to just after its final draw"),
    gettext_noop(
        "Rolled this? Jump the seed to just after this clean pull (a dupe's branch has its "
        "own dice)"
    ),
    gettext_noop("Search for %(label)s on %(banners)s"),
    gettext_noop("See it in the tier list"),
    gettext_noop("Stop searching for this future uber"),
    gettext_noop("Targets"),
    gettext_noop(
        "This step of the plan can be rolled on this banner instead - you'd get this cat, and "
        "the rest of the plan still works"
    ),
    gettext_noop(
        "Toggle a future uber to search for it - it joins your Targets above and glows on "
        "this banner's cells"
    ),
    gettext_noop("Track A"),
    gettext_noop("Track B"),
    gettext_noop("Uber debuting with this banner (its first event anywhere)"),
    gettext_noop("Uber/Legend not in your collection"),
    gettext_noop("Won't drop on the selected banners"),
    gettext_noop(
        "Won't drop on the selected banners: %(banners)s. Add a banner that carries it, or "
        "remove it."
    ),
    gettext_noop(
        "You land here next: the first cat another roll on this banner would give after the "
        "highlighted draws"
    ),
    gettext_noop(
        "a capsule banner &mdash; its pulls spend that scarce ticket, not rare tickets or catfood"
    ),
    gettext_noop(
        "a target you picked &mdash; gold here, and its next spot shows in <em>Targets</em> above"
    ),
    gettext_noop("alternate timelines; a dupe rerolls and switches track"),
    gettext_noop("an expected-but-unreleased Uber padding the pool"),
    gettext_noop("another banner this plan step can roll on instead"),
    gettext_noop("cat"),
    gettext_noop("click a cell's name-free space: the rolls up to it light like a plan"),
    gettext_noop("dashed"),
    gettext_noop("green name"),
    gettext_noop("if dupe"),
    gettext_noop("if dupe:"),
    gettext_noop("legend"),
    gettext_noop("new"),
    gettext_noop("owned"),
    gettext_noop("path"),
    gettext_noop("platinum"),
    gettext_noop("rarity %(rarity)s &middot; slot %(slot)s"),
    gettext_noop("striped"),
    gettext_noop("the Uber a guaranteed multi awards if started on that cell"),
    gettext_noop("the reroll branch (its own dice &amp; landing)"),
    gettext_noop("wishlisted"),
    gettext_noop(
        "you land here next &mdash; the first cat one more roll would give after the lit draws"
    ),
    # Rarities, long and as the cells abbreviate them.
    gettext_noop("Rare"),
    gettext_noop("Super Rare"),
    gettext_noop("Uber Super Rare"),
    gettext_noop("Legend Rare"),
    # The plans.
    gettext_noop("%(n)s catfood"),
    gettext_noop("%(n)s plans"),
    gettext_noop("%(n)s-roll"),
    gettext_noop("%(n)s-roll (guaranteed)"),
    gettext_noop("Apply this plan"),
    gettext_noop(
        "Best plan found, not a proven cheapest one. Past %(limit)s cats the search for the "
        "whole set is bounded - an exact one would take 2^N searches - so a cheaper plan may "
        "exist. Every smaller row here IS exact."
    ),
    gettext_noop("Clear"),
    gettext_noop("Next step"),
    gettext_noop("No reachable plan with given resources."),
    gettext_noop("Not found"),
    gettext_noop("Only plans with"),
    gettext_noop("Previous step"),
    gettext_noop("Single pull"),
    gettext_noop("Steps"),
    gettext_noop("Total &middot; %(total)s"),
    gettext_noop("Walk the plan step by step"),
    gettext_noop("Working out this plan&hellip;"),
    gettext_noop("best found"),
    gettext_noop("free"),
    gettext_noop("gets"),
    gettext_noop("same rolls"),
    # The Normal Capsules.
    gettext_noop("Dark Catseye"),
    gettext_noop(
        "Following the track dupes here: the previous pull obtains this same item, so this "
        "cell rerolls into the branch value and jumps tracks"
    ),
    gettext_noop(
        "No %(target)s reachable with those rolls. Give a machine more budget, or try again "
        "after your next real pulls move the seed."
    ),
    gettext_noop("Pick at least one capsule machine to roll."),
    gettext_noop(
        "Rolled %(cell)s? Jump the seed to just after it (its clean roll; a dupe's branch has "
        "its own dice)"
    ),
    gettext_noop(
        "You rolled this plan: the seed jumps to just after its final pull and its tickets "
        "come off your stash"
    ),
    gettext_noop("a planned pull"),
    gettext_noop("an upgrade (Special Skill), not a cat"),
    gettext_noop("aqua"),
    gettext_noop("blue"),
    gettext_noop("for"),
    gettext_noop("gold"),
    gettext_noop("red"),
    gettext_noop("target"),
    gettext_noop("the 1% Catseye-event jackpot"),
    gettext_noop("the machine's rarer rate bands, scarcest last"),
    gettext_noop("what it collects"),
)

# The cells' short rarity labels, keyed "short rarity:<English>" (see Request::t_keyed).
SHORT_RARITIES = ("Rare", "Super", "Uber", "Legend")

# The counted ones, (singular, plural) as English words them.
ENGINE_PLURALS = (
    ("%(n)s ticket", "%(n)s tickets"),
    ("%(n)s platinum ticket", "%(n)s platinum tickets"),
    ("%(n)s legend ticket", "%(n)s legend tickets"),
    ("%(n)s&times; single pull", "%(n)s&times; single pulls"),
    ("%(n)s&times; pull", "%(n)s&times; pulls"),
    ("%(n)s Normal Cat Ticket", "%(n)s Normal Cat Tickets"),
    ("%(n)s Lucky Ticket", "%(n)s Lucky Tickets"),
    ("%(n)s Lucky Ticket G", "%(n)s Lucky Ticket Gs"),
    (
        "This plan gets %(size)s of the %(total)s cat you searched for",
        "This plan gets %(size)s of the %(total)s cats you searched for",
    ),
)


def engine_text() -> dict[str, str]:
    """{English: translation} for the engine strings the interface language translates;
    English itself, translating nothing, sends nothing. A counted message sends each English
    form its own translation - the engine picks the form by English's rule."""
    text = {english: gettext(english) for english in ENGINE_TEXT}
    for singular, plural in ENGINE_PLURALS:
        text[singular] = ngettext(singular, plural, 1)
        text[plural] = ngettext(singular, plural, 2)

    shorts = {
        f"short rarity:{short}": (short, pgettext("short rarity", short))
        for short in SHORT_RARITIES
    }

    return {english: local for english, local in text.items() if local != english} | {
        key: local for key, (short, local) in shorts.items() if local != short
    }
