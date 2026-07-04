from django.core.management.base import BaseCommand

from neko.bcdata import load_records
from planner.services import import_units


class Command(BaseCommand):
    help = "Load the unit catalogue from neko/data/units.json into the database."

    def handle(self, *args, **options):
        created = import_units(load_records())

        self.stdout.write(self.style.SUCCESS(f"Imported {created} new units."))
