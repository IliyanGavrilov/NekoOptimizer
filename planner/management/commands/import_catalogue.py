from planner.management.base import RegionCommand
from planner.services import fetch_catalogue, import_cats


class Command(RegionCommand):
    help = "Populate the catalogue with every scheduled banner's cats from the gacha pools."

    def handle(self, *args, **options):
        result = fetch_catalogue()
        created = import_cats(result.banners, result.dates)

        self.stdout.write(self.style.SUCCESS(f"Imported {created} new cats."))
