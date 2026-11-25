from datetime import date

from django.core.management.base import BaseCommand

from neko.gachadata import load_events, load_pools, unshipped
from neko.region import CODES


class Command(BaseCommand):
    help = "List every version's live or upcoming banners that have no pool in the data yet."

    def handle(self, *args, **options):
        today = date.today()
        for region in CODES:
            for event in unshipped(load_events(region), load_pools(region), today):
                self.stdout.write(f"{region} {event.start} pool {event.pool_id}: {event.name}")
