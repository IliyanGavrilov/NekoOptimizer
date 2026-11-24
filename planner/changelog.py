# What's new, newest first: what a player would notice, in their words. Add an entry
# when something they'd see changes.

from datetime import date

from django.utils.translation import gettext_lazy as _

CHANGES = (
    (
        date(2026, 11, 19),
        (
            _("On phones the header takes two short rows, and the page links swipe sideways."),
            _("Collection's A-Z view has a section per letter, and a row of letters jumps to one."),
            _("Every on/off option is now a tick box."),
            _("Platinum and Legend Capsules no longer mark their cats as new."),
            _("The banner search also matches a banner's subtitle."),
        ),
    ),
    (
        date(2026, 11, 18),
        (
            _(
                "A new look across the site, and a simpler Collection: one toolbar of drop-downs, "
                "with a Missing filter."
            ),
            _("A cat's popup lists the banners it drops from."),
            _(
                "On Resources, a talent with levels takes a slider, so you can plan it short of "
                "its max."
            ),
            _(
                "The seed field starts empty instead of at 0, which rolled the same cats on every "
                "banner."
            ),
        ),
    ),
    (
        date(2026, 11, 17),
        (
            _("Explore mode no longer runs out of memory with many banners and targets."),
            _("Forms the game data hadn't caught up on yet can now be planned on Resources."),
        ),
    ),
    (
        date(2026, 11, 12),
        (
            _("Collab and one-off banners show their official titles, in each version's language."),
            _("Cats too new for the main game data are now listed."),
        ),
    ),
    (
        date(2026, 11, 11),
        (
            _("Each version's tier lists use that version's own cat names."),
            _("On narrow windows the Rolls and Normal Capsules tables scroll in their own pane."),
        ),
    ),
    (
        date(2026, 10, 31),
        (
            _(
                "The site now speaks Japanese, Traditional Chinese and Korean. Each game "
                "version opens in its own language; pick another in the header."
            ),
            _("Each game version has its own pages: /jp/, /tw/ and /kr/."),
            _(
                "Your first visit opens the version your browser's language points to: "
                "Japanese, Traditional Chinese or Korean, else English."
            ),
            _("The Seed Finder's checks now show as you pick each cat."),
            _("Fest and set names use each game version's own names, taken from the game's data."),
            _(
                "A short welcome for first visits, guide links on the pages that need them, "
                "and a page of game words explained."
            ),
        ),
    ),
    (
        date(2026, 10, 30),
        (
            _(
                "Your seeds are saved to your profile. A new device or a cleared browser no "
                "longer loses them, and a line under the seed shows when it's saved."
            ),
            _(
                "The Seed Finder checks your entry for the usual mistakes before it searches, "
                "and saves the seed it finds."
            ),
            _("Opening someone else's link no longer replaces your own seed until you choose to."),
            _("New step-by-step guides."),
        ),
    ),
    (
        date(2026, 10, 16),
        (
            _("Import your collection from screenshots of the in-game Cat Guide."),
            _("The seed search and the rolls run in your browser, so they're much faster."),
        ),
    ),
)
