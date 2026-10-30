from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("planner", "0020_profile_auto_wishlist"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="seed",
            name="unique_seed_per_region",
        ),
        migrations.AddField(
            model_name="seed",
            name="kind",
            field=models.CharField(
                choices=[("rare", "Rare gacha"), ("normal", "Normal Capsules")],
                default="rare",
                max_length=6,
            ),
        ),
        migrations.AddField(
            model_name="seed",
            name="last",
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddConstraint(
            model_name="seed",
            constraint=models.UniqueConstraint(
                fields=("profile", "region", "kind"), name="unique_seed_per_region_kind"
            ),
        ),
    ]
