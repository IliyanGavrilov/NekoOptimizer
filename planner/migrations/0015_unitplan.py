import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("planner", "0014_cannonplan_current_levels"),
    ]

    operations = [
        migrations.RenameModel(
            old_name="EvolvePlan",
            new_name="UnitPlan",
        ),
        migrations.AlterField(
            model_name="unitplan",
            name="unit",
            field=models.OneToOneField(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="plan",
                to="planner.unit",
            ),
        ),
    ]
