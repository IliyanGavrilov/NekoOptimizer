from django.core.management.base import BaseCommand

from planner.icons import ICONS_DIR, refresh


class Command(BaseCommand):
    help = "Download every catalogue unit's form icons from battlecatsinfo into static/."

    def handle(self, *args, **options):
        saved, missing = refresh()
        self.stdout.write(self.style.SUCCESS(f"{saved} icons under {ICONS_DIR}."))
        if missing:
            self.stdout.write(f"{missing} forms the source has no icon for.")
