from django.db import models


class Location(models.Model):
    normalized_text = models.CharField(max_length=255, unique=True, db_index=True)
    display_name = models.CharField(max_length=255)
    latitude = models.FloatField()
    longitude = models.FloatField()
    kind = models.CharField(max_length=20, default="place")
    state = models.CharField(max_length=2, blank=True, db_index=True)

    def __str__(self):
        return self.display_name


class FuelStation(models.Model):
    external_id = models.CharField(max_length=100, unique=True)
    name = models.CharField(max_length=255)
    address = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=2, blank=True)
    postal_code = models.CharField(max_length=10, blank=True, db_index=True)
    price_per_gallon = models.DecimalField(max_digits=8, decimal_places=4)
    latitude = models.FloatField(db_index=True)
    longitude = models.FloatField(db_index=True)
    location_source = models.CharField(max_length=30, default="unknown", db_index=True)
    location_confidence = models.FloatField(default=0.0)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)

    def __str__(self):
        return f"{self.name} ({self.price_per_gallon})"


class PostalCodeLocation(models.Model):
    postal_code = models.CharField(max_length=5, db_index=True)
    display_name = models.CharField(max_length=255)
    latitude = models.FloatField()
    longitude = models.FloatField()
    state = models.CharField(max_length=2, blank=True, db_index=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("postal_code", "display_name", "latitude", "longitude"),
                name="unique_postal_location",
            )
        ]

    def __str__(self):
        return self.display_name


class HighwayJunction(models.Model):
    state = models.CharField(max_length=2, db_index=True)
    highway = models.CharField(max_length=20, db_index=True)
    exit_number = models.CharField(max_length=20, db_index=True)
    latitude = models.FloatField()
    longitude = models.FloatField()
    name = models.CharField(max_length=255, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("state", "highway", "exit_number", "latitude", "longitude"),
                name="unique_highway_junction",
            )
        ]


class PlaceLocation(models.Model):
    normalized_name = models.CharField(max_length=255, db_index=True)
    display_name = models.CharField(max_length=255)
    state = models.CharField(max_length=2, db_index=True)
    latitude = models.FloatField()
    longitude = models.FloatField()
    postal_code_count = models.PositiveIntegerField(default=1)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("normalized_name", "state"),
                name="unique_place_state",
            )
        ]
