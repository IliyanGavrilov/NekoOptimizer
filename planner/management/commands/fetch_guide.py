from django.core.management.base import BaseCommand

from neko.guidedata import GUIDE_PATH, refresh


class Command(BaseCommand):
    help = "Fetch the in-game Cat Guide order per region from the wiki into guide_order.json."

    def handle(self, *args, **options):
        for region, (count, unmatched) in refresh().items():
            self.stdout.write(self.style.SUCCESS(f"{region}: {count} units resolved."))
            if unmatched:
                self.stdout.write(f"{region}: unmatched: {', '.join(unmatched)}")
        self.stdout.write(self.style.SUCCESS(f"Wrote {GUIDE_PATH}."))
