from django.conf import settings
from django.db import migrations


def move_state(apps, schema_editor):
    """Hand the single global collection, plans, seeds and game version to one profile,
    claimed by the first superuser so logging in picks it back up."""
    Profile = apps.get_model("planner", "Profile")
    Unit = apps.get_model("planner", "Unit")
    Region = apps.get_model("planner", "Region")
    User = apps.get_model(settings.AUTH_USER_MODEL)
    owned = list(Unit.objects.filter(owned=True))
    wanted = list(Unit.objects.filter(wanted=True))
    plans = [
        apps.get_model("planner", name).objects.all()
        for name in ("UnitPlan", "TalentPlan", "CannonPlan", "Seed")
    ]
    region = Region.objects.first()
    if not (owned or wanted or region or any(rows.exists() for rows in plans)):
        return

    profile = Profile.objects.create(
        user=User.objects.filter(is_superuser=True).order_by("pk").first(),
        region=region.code if region else "en",
    )
    profile.owned.set(owned)
    profile.wanted.set(wanted)
    for rows in plans:
        rows.update(profile=profile)


def restore_state(apps, schema_editor):
    Profile = apps.get_model("planner", "Profile")
    Region = apps.get_model("planner", "Region")
    profile = Profile.objects.order_by("pk").first()
    if profile is None:
        return

    profile.owned.update(owned=True)
    profile.wanted.update(wanted=True)
    Region.objects.update_or_create(pk=1, defaults={"code": profile.region})


class Migration(migrations.Migration):
    dependencies = [("planner", "0017_profile")]

    operations = [migrations.RunPython(move_state, restore_state)]
