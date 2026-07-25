from django.core.management.base import BaseCommand

from planner.icons import ICONS_DIR, ITEMS_DIR, refresh, refresh_items


class Command(BaseCommand):
    help = "Download every unit's form icons and every grind material's icon into static/."

    def handle(self, *args, **options):
        saved, missing = refresh()
        self.stdout.write(self.style.SUCCESS(f"{saved} icons under {ICONS_DIR}."))
        if missing:
            self.stdout.write(f"{missing} forms the source has no icon for.")

        saved, missing = refresh_items()
        self.stdout.write(self.style.SUCCESS(f"{saved} material icons under {ITEMS_DIR}."))
        if missing:
            self.stdout.write(f"{missing} materials the source has no icon for.")
