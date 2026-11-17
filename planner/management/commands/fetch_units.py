import json
from pathlib import Path

from neko.bcdata import catalogue_from_tarball, catalogue_records, download_catalogue, units_path
from neko.bcinfo import download_units, fill_forms
from planner.management.base import RegionCommand


class Command(RegionCommand):
    help = (
        "Fetch the latest unit catalogue from the live BCData mirror into units.json, "
        "with the units and forms it hasn't caught up on yet from battlecatsinfo."
    )

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
        filled = fill_forms(catalogue, download_units(region))
        added = len(filled) - len(catalogue)
        records = catalogue_records(filled)
        target = units_path(region)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")

        self.stdout.write(
            self.style.SUCCESS(
                f"Wrote {len(records)} units (game {version}, {added} from battlecatsinfo) "
                f"to {target}."
            )
        )
