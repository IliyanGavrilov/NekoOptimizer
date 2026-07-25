from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("planner", "0015_unitplan"),
    ]

    operations = [
        migrations.AddField(
            model_name="cannonplan",
            name="base_on",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="cannonplan",
            name="deco_on",
            field=models.BooleanField(default=False),
        ),
    ]
