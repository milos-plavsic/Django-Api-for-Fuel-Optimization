from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("routing", "0005_placelocation"),
    ]

    operations = [
        migrations.AddField(
            model_name="placelocation",
            name="postal_code_count",
            field=models.PositiveIntegerField(default=1),
        ),
    ]
