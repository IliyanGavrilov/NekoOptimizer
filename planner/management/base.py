from django.core.management.base import BaseCommand

from neko.region import CODES, DEFAULT_REGION, using


class RegionCommand(BaseCommand):
    """A command that works on one game version: its committed data files and its own
    catalogue rows. The chosen region stays active for the whole run, so everything the
    command touches - loaders and models alike - resolves to that version."""

    def add_arguments(self, parser):
        parser.add_argument(
            "--region", choices=CODES, default=DEFAULT_REGION, help="Game version to work on."
        )

    def execute(self, *args, **options):
        with using(options.get("region") or DEFAULT_REGION):
            return super().execute(*args, **options)
