from pathlib import Path

from neko.gachadata import events_path, refresh
from planner.management.base import RegionCommand


class Command(RegionCommand):
    help = "Fetch the gacha schedule (godfat event TSVs) and pools (BCData) into data files."

    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument(
            "--tarball", help="Use a downloaded BCData tarball instead of fetching."
        )

    def handle(self, *args, **options):
        region = options["region"]
        tarball = Path(options["tarball"]).read_bytes() if options["tarball"] else None
        events, pools = refresh(region, tarball=tarball)

        self.stdout.write(
            self.style.SUCCESS(
                f"Wrote {events} events and {pools} pools to {events_path(region).parent}."
            )
        )
