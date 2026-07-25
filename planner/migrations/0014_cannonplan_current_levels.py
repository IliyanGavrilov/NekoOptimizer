from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("planner", "0013_regions"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="cannonplan",
            name="cannon_goal",
        ),
        migrations.RemoveField(
            model_name="cannonplan",
            name="base_goal",
        ),
        migrations.RemoveField(
            model_name="cannonplan",
            name="deco_goal",
        ),
    ]
