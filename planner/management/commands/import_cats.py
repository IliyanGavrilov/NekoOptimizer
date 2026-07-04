from django.core.management.base import BaseCommand

from planner.services import fetch_banners, import_cats


class Command(BaseCommand):
    help = "Populate the cat catalogue by rolling the active banners for a seed."

    def add_arguments(self, parser):
        parser.add_argument("seed", type=int)

    def handle(self, *args, **options):
        result = fetch_banners(options["seed"])
        created = import_cats(result.banners, result.dates)

        self.stdout.write(self.style.SUCCESS(f"Imported {created} new cats."))
