from pathlib import Path

from neko.statsdata import refresh, stats_path
from planner.management.base import RegionCommand


class Command(RegionCommand):
    help = "Fetch unit stats from the BCData mirror and battlecatsinfo into stats.json."

    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument("--tarball", help="Use a downloaded BCData tarball instead.")

    def handle(self, *args, **options):
        region = options["region"]
        tarball = Path(options["tarball"]).read_bytes() if options["tarball"] else None
        total = refresh(tarball, region)
        self.stdout.write(
            self.style.SUCCESS(f"Wrote stats for {total} units to {stats_path(region)}.")
        )
