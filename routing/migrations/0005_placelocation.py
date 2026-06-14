from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("routing", "0004_fuelstation_location_metadata_highwayjunction"),
    ]

    operations = [
        migrations.CreateModel(
            name="PlaceLocation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("normalized_name", models.CharField(db_index=True, max_length=255)),
                ("display_name", models.CharField(max_length=255)),
                ("state", models.CharField(db_index=True, max_length=2)),
                ("latitude", models.FloatField()),
                ("longitude", models.FloatField()),
            ],
            options={
                "constraints": [
                    models.UniqueConstraint(
                        fields=("normalized_name", "state"),
                        name="unique_place_state",
                    )
                ],
            },
        ),
    ]
