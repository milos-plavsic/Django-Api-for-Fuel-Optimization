from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("routing", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="location",
            name="state",
            field=models.CharField(blank=True, db_index=True, max_length=2),
        ),
    ]
