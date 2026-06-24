from django.core.management.base import BaseCommand

from planner.services import fetch_banners, import_cats


class Command(BaseCommand):
    help = "Populate the cat catalogue by scraping godfat's active banners for a seed."

    def add_arguments(self, parser):
        parser.add_argument("seed", type=int)

    def handle(self, *args, **options):
        created = import_cats(fetch_banners(options["seed"]).banners)
        self.stdout.write(self.style.SUCCESS(f"Imported {created} new cats."))
