from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("routing", "0002_location_state"),
    ]

    operations = [
        migrations.CreateModel(
            name="PostalCodeLocation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("postal_code", models.CharField(db_index=True, max_length=5)),
                ("display_name", models.CharField(max_length=255)),
                ("latitude", models.FloatField()),
                ("longitude", models.FloatField()),
                ("state", models.CharField(blank=True, db_index=True, max_length=2)),
            ],
            options={
                "constraints": [
                    models.UniqueConstraint(
                        fields=("postal_code", "display_name", "latitude", "longitude"),
                        name="unique_postal_location",
                    )
                ],
            },
        ),
    ]
