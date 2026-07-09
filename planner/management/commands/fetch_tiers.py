from django.core.management.base import BaseCommand

from neko.tierdata import TIERS_PATH, refresh


class Command(BaseCommand):
    help = "Fetch the cumulative tier list from battlecatstierlist.com into tiers.json."

    def handle(self, *args, **options):
        total, unmatched = refresh()
        self.stdout.write(self.style.SUCCESS(f"Wrote {total} tier entries to {TIERS_PATH}."))
        for name in unmatched:
            self.stdout.write(self.style.WARNING(f"No catalogue match for {name!r}."))
