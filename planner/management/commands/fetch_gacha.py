from django.core.management.base import BaseCommand

from neko.gachadata import EVENTS_PATH, refresh


class Command(BaseCommand):
    help = "Fetch the gacha schedule (godfat event TSVs) and pools (BCData) into data files."

    def handle(self, *args, **options):
        events, pools = refresh()
        self.stdout.write(
            self.style.SUCCESS(f"Wrote {events} events and {pools} pools to {EVENTS_PATH.parent}.")
        )
