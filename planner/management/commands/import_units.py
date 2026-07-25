from neko.bcdata import load_records
from planner.management.base import RegionCommand
from planner.services import import_units


class Command(RegionCommand):
    help = "Load one region's catalogue from neko/data/<region>/units.json into the database."

    def handle(self, *args, **options):
        created = import_units(load_records())

        self.stdout.write(self.style.SUCCESS(f"Imported {created} new units."))
