import asyncio
import json

from django.core.management.base import BaseCommand

from neko.bcdata import UNITS_PATH, catalogue_records, download_catalogue


class Command(BaseCommand):
    help = "Fetch the canonical unit catalogue from BCData into neko/data/units.json."

    def handle(self, *args, **options):
        catalogue = asyncio.run(download_catalogue())
        records = catalogue_records(catalogue)
        UNITS_PATH.write_text(json.dumps(records, indent=2), encoding="utf-8")
        self.stdout.write(self.style.SUCCESS(f"Wrote {len(records)} units to {UNITS_PATH}."))
