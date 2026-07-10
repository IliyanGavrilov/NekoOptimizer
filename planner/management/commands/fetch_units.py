import json
from pathlib import Path

from django.core.management.base import BaseCommand

from neko.bcdata import UNITS_PATH, catalogue_from_tarball, catalogue_records, download_catalogue


class Command(BaseCommand):
    help = "Fetch the latest unit catalogue from the live BCData mirror into units.json."

    def add_arguments(self, parser):
        parser.add_argument("--tarball", help="Use a downloaded BCData tarball instead.")

    def handle(self, *args, **options):
        if options["tarball"]:
            path = Path(options["tarball"])
            version, catalogue = path.name, catalogue_from_tarball(path.read_bytes())
        else:
            version, catalogue = download_catalogue()
        records = catalogue_records(catalogue)
        UNITS_PATH.write_text(json.dumps(records, indent=2), encoding="utf-8")

        self.stdout.write(
            self.style.SUCCESS(f"Wrote {len(records)} units (game {version}) to {UNITS_PATH}.")
        )
