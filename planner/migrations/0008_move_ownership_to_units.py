from django.db import migrations

PROVISIONAL_BASE = 1_000_000  # synthetic ids for cats not yet in the catalogue


def move_ownership(apps, schema_editor):
    Cat = apps.get_model("planner", "Cat")
    Unit = apps.get_model("planner", "Unit")
    last = Unit.objects.filter(unit_id__gte=PROVISIONAL_BASE).order_by("-unit_id").first()
    next_id = (last.unit_id + 1) if last else PROVISIONAL_BASE
    for cat in Cat.objects.all():
        unit = cat.unit
        if unit is None:
            unit = Unit.objects.create(
                unit_id=next_id, name=cat.name, rarity=cat.rarity, canonical=False
            )
            next_id += 1
            cat.unit = unit
            cat.save(update_fields=["unit"])
        if cat.owned or cat.wanted:
            unit.owned, unit.wanted = cat.owned, cat.wanted
            unit.save(update_fields=["owned", "wanted"])


def restore_ownership(apps, schema_editor):
    Cat = apps.get_model("planner", "Cat")
    for cat in Cat.objects.filter(unit__isnull=False):
        cat.owned, cat.wanted = cat.unit.owned, cat.unit.wanted
        cat.save(update_fields=["owned", "wanted"])


class Migration(migrations.Migration):
    dependencies = [("planner", "0007_unit_canonical_unit_owned_unit_wanted")]

    operations = [migrations.RunPython(move_ownership, restore_ownership)]
