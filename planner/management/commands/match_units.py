from django.core.management.base import BaseCommand

from planner.services import unit_match_report


class Command(BaseCommand):
    help = "Report which scraped cat names map to a canonical unit, and which don't."

    def handle(self, *args, **options):
        matches, unmatched = unit_match_report()
        total = len(matches) + len(unmatched)
        self.stdout.write(self.style.SUCCESS(f"Matched {len(matches)}/{total} cat names to units."))
        for name in unmatched:
            self.stdout.write(f"  unmatched: {name}")
