from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):
    dependencies = [
        ("routing", "0006_placelocation_postal_code_count"),
    ]

    operations = [
        migrations.AddField(
            model_name="fuelstation",
            name="updated_at",
            field=models.DateTimeField(
                auto_now=True,
                db_index=True,
                default=django.utils.timezone.now,
            ),
            preserve_default=False,
        ),
    ]
