from django.core.management.base import BaseCommand

from planner.services import fetch_catalogue, import_cats


class Command(BaseCommand):
    help = "Populate the catalogue from every godfat banner for a seed, not just the active ones."

    def add_arguments(self, parser):
        parser.add_argument("seed", type=int)

    def handle(self, *args, **options):
        result = fetch_catalogue(options["seed"])
        created = import_cats(result.banners, result.dates)
        self.stdout.write(self.style.SUCCESS(f"Imported {created} new cats."))
