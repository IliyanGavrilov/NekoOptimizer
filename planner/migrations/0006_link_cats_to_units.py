from django.db import migrations


def link_cats(apps, schema_editor):
    Cat = apps.get_model("planner", "Cat")
    Unit = apps.get_model("planner", "Unit")
    units = {unit.name: unit.pk for unit in Unit.objects.all()}
    for cat in Cat.objects.filter(unit__isnull=True):
        unit_pk = units.get(cat.name)
        if unit_pk is not None:
            cat.unit_id = unit_pk
            cat.save(update_fields=["unit"])


def unlink_cats(apps, schema_editor):
    Cat = apps.get_model("planner", "Cat")
    Cat.objects.update(unit=None)


class Migration(migrations.Migration):
    dependencies = [("planner", "0005_cat_unit")]

    operations = [migrations.RunPython(link_cats, unlink_cats)]
