from pathlib import Path

from django.core.management.base import BaseCommand

from neko.statsdata import STATS_PATH, refresh


class Command(BaseCommand):
    help = "Fetch unit stats from the BCData mirror and battlecatsinfo into stats.json."

    def add_arguments(self, parser):
        parser.add_argument("--tarball", help="Use a downloaded BCData tarball instead.")

    def handle(self, *args, **options):
        tarball = Path(options["tarball"]).read_bytes() if options["tarball"] else None
        total = refresh(tarball)
        self.stdout.write(self.style.SUCCESS(f"Wrote stats for {total} units to {STATS_PATH}."))
