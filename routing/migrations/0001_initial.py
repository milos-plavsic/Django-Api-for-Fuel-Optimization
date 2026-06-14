from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    operations = [
        migrations.CreateModel(
            name="FuelStation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("external_id", models.CharField(max_length=100, unique=True)),
                ("name", models.CharField(max_length=255)),
                ("address", models.CharField(blank=True, max_length=255)),
                ("city", models.CharField(blank=True, max_length=100)),
                ("state", models.CharField(blank=True, max_length=2)),
                ("postal_code", models.CharField(blank=True, db_index=True, max_length=10)),
                ("price_per_gallon", models.DecimalField(decimal_places=4, max_digits=8)),
                ("latitude", models.FloatField(db_index=True)),
                ("longitude", models.FloatField(db_index=True)),
            ],
        ),
        migrations.CreateModel(
            name="Location",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("normalized_text", models.CharField(db_index=True, max_length=255, unique=True)),
                ("display_name", models.CharField(max_length=255)),
                ("latitude", models.FloatField()),
                ("longitude", models.FloatField()),
                ("kind", models.CharField(default="place", max_length=20)),
            ],
        ),
    ]
