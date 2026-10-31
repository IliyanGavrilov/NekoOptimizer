# What's new, newest first: what a player would notice, in their words. Add an entry
# when something they'd see changes.

from datetime import date

from django.utils.translation import gettext_lazy as _

CHANGES = (
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
