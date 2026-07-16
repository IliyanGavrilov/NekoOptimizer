from pathlib import Path

from django.core.management.base import BaseCommand

from neko.gachadata import EVENTS_PATH, refresh


class Command(BaseCommand):
    help = "Fetch the gacha schedule (godfat event TSVs) and pools (BCData) into data files."

    def add_arguments(self, parser):
        parser.add_argument(
            "--tarball", help="Use a downloaded BCData tarball instead of fetching."
        )

    def handle(self, *args, **options):
        tarball = Path(options["tarball"]).read_bytes() if options["tarball"] else None
        events, pools = refresh(tarball=tarball)

        self.stdout.write(
            self.style.SUCCESS(f"Wrote {events} events and {pools} pools to {EVENTS_PATH.parent}.")
        )
