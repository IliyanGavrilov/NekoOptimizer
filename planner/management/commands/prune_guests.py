from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from planner.models import Profile

# A profile is saved by the request that changes something, which writes the change right
# after: only sweep ones old enough that no such request can still be running.
GRACE = timedelta(days=1)


class Command(BaseCommand):
    help = "Delete guest profiles that hold nothing (see Profile.objects.empty_guests)."

    def handle(self, *args, **options):
        cutoff = timezone.now() - GRACE
        _, deleted = Profile.objects.empty_guests().filter(created__lt=cutoff).delete()
        count = deleted.get(Profile._meta.label, 0)
        self.stdout.write(self.style.SUCCESS(f"Deleted {count} empty guest profiles."))
