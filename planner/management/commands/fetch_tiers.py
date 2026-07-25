from django.core.management.base import BaseCommand

from neko.tierdata import TIERS_PATH, refresh


class Command(BaseCommand):
    help = "Fetch the cumulative and per-set tier lists from battlecatstierlist.com."

    def handle(self, *args, **options):
        total, lists, unmatched = refresh()
        self.stdout.write(
            self.style.SUCCESS(f"Wrote {total} entries over {lists} per-set lists to {TIERS_PATH}.")
        )
        for name in unmatched:
            self.stdout.write(self.style.WARNING(f"No catalogue match for {name!r}."))
