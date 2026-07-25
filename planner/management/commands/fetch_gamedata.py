from pathlib import Path

from neko.gamedata import refresh
from planner.management.base import RegionCommand


class Command(RegionCommand):
    help = "Fetch combos, talents, evolution costs, item names, and cannon recipes into neko/data/."

    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument("--tarball", help="Use a downloaded BCData tarball instead.")

    def handle(self, *args, **options):
        region = options["region"]
        tarball = Path(options["tarball"]).read_bytes() if options["tarball"] else None
        for name, count in refresh(tarball, region).items():
            self.stdout.write(self.style.SUCCESS(f"Wrote {count} records to {region}/{name}."))
