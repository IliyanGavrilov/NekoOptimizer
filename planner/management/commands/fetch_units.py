import json
from pathlib import Path

from neko.bcdata import catalogue_from_tarball, catalogue_records, download_catalogue, units_path
from planner.management.base import RegionCommand


class Command(RegionCommand):
    help = "Fetch the latest unit catalogue from the live BCData mirror into units.json."

    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument("--tarball", help="Use a downloaded BCData tarball instead.")

    def handle(self, *args, **options):
        region = options["region"]
        if options["tarball"]:
            path = Path(options["tarball"])
            version = path.name
            catalogue = catalogue_from_tarball(path.read_bytes(), region)
        else:
            version, catalogue = download_catalogue(region)
        records = catalogue_records(catalogue)
        target = units_path(region)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")

        self.stdout.write(
            self.style.SUCCESS(f"Wrote {len(records)} units (game {version}) to {target}.")
        )
