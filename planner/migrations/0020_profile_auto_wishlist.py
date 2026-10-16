from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("planner", "0019_profile_owns_state"),
    ]

    operations = [
        migrations.AddField(
            model_name="profile",
            name="auto_wishlist",
            field=models.BooleanField(default=False),
        ),
    ]
