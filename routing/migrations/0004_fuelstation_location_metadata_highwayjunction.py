from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("routing", "0003_postalcodelocation"),
    ]

    operations = [
        migrations.AddField(
            model_name="fuelstation",
            name="location_confidence",
            field=models.FloatField(default=0.0),
        ),
        migrations.AddField(
            model_name="fuelstation",
            name="location_source",
            field=models.CharField(db_index=True, default="unknown", max_length=30),
        ),
        migrations.CreateModel(
            name="HighwayJunction",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("state", models.CharField(db_index=True, max_length=2)),
                ("highway", models.CharField(db_index=True, max_length=20)),
                ("exit_number", models.CharField(db_index=True, max_length=20)),
                ("latitude", models.FloatField()),
                ("longitude", models.FloatField()),
                ("name", models.CharField(blank=True, max_length=255)),
            ],
            options={
                "constraints": [
                    models.UniqueConstraint(
                        fields=("state", "highway", "exit_number", "latitude", "longitude"),
                        name="unique_highway_junction",
                    )
                ],
            },
        ),
    ]
