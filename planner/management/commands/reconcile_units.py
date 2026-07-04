from django.core.management.base import BaseCommand

from planner.services import reconcile_provisional_units


class Command(BaseCommand):
    help = "Merge provisional stand-in units into their now-canonical namesakes."

    def handle(self, *args, **options):
        merged, orphaned = reconcile_provisional_units()

        self.stdout.write(
            self.style.SUCCESS(f"Merged {merged} provisional units into canonical ones.")
        )

        for name in orphaned:
            self.stdout.write(f"  still provisional (no canonical match): {name}")
