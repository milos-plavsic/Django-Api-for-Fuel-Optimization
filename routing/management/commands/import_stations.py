import csv
from collections import defaultdict
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from routing.models import FuelStation, Location, PostalCodeLocation
from routing.services.geo import normalize_location
from routing.services.station_location import resolve_station_coordinates


ALIASES = {
    "external_id": ("external_id", "opis_id", "opis truckstop id"),
    "name": ("name", "truckstop name"),
    "address": ("address",),
    "city": ("city",),
    "state": ("state",),
    "postal_code": ("postal_code", "zip", "zipcode"),
    "price_per_gallon": ("price_per_gallon", "retail_price", "retail price"),
    "latitude": ("latitude", "lat"),
    "longitude": ("longitude", "lng", "lon"),
}


def normalized_row(row):
    source = {key.strip().lower(): value for key, value in row.items()}
    return {
        target: next((source[name] for name in names if source.get(name) not in (None, "")), "")
        for target, names in ALIASES.items()
    }


def local_place_coordinates():
    grouped = defaultdict(list)
    for location in PostalCodeLocation.objects.exclude(state="").iterator():
        prefix = f"{location.postal_code} - "
        if not location.display_name.startswith(prefix):
            continue
        place = location.display_name[len(prefix):]
        suffix = f", {location.state}"
        if place.endswith(suffix):
            place = place[:-len(suffix)]
        grouped[(normalize_location(place), location.state.upper())].append(
            (location.latitude, location.longitude)
        )
    return {
        key: (
            sum(latitude for latitude, _ in coordinates) / len(coordinates),
            sum(longitude for _, longitude in coordinates) / len(coordinates),
        )
        for key, coordinates in grouped.items()
    }


class Command(BaseCommand):
    help = "Import the supplied fuel-price CSV and create local place aliases."

    def add_arguments(self, parser):
        parser.add_argument("csv_path", type=Path)

    def handle(self, *args, **options):
        path = options["csv_path"]
        if not path.exists():
            raise CommandError(f"File does not exist: {path}")

        place_coordinates = local_place_coordinates()
        imported = 0
        skipped = 0
        with path.open(newline="", encoding="utf-8-sig") as stream:
            for raw in csv.DictReader(stream):
                row = normalized_row(raw)
                try:
                    price = float(row["price_per_gallon"])
                except (TypeError, ValueError):
                    skipped += 1
                    continue
                try:
                    latitude = float(row["latitude"])
                    longitude = float(row["longitude"])
                    location_source = "provided_coordinates"
                    location_confidence = 1.0
                except (TypeError, ValueError):
                    city_coordinates = place_coordinates.get(
                        (normalize_location(row["city"]), row["state"].upper())
                    )
                    resolved = resolve_station_coordinates(
                        row["address"],
                        row["state"].upper(),
                        city_coordinates,
                    )
                    if resolved is None:
                        skipped += 1
                        continue
                    latitude, longitude, location_source, location_confidence = resolved
                external_id = row["external_id"] or f"{row['name']}:{latitude}:{longitude}"
                FuelStation.objects.update_or_create(
                    external_id=external_id,
                    defaults={
                        "name": row["name"] or "Fuel station",
                        "address": row["address"],
                        "city": row["city"],
                        "state": row["state"].upper(),
                        "postal_code": row["postal_code"],
                        "price_per_gallon": price,
                        "latitude": latitude,
                        "longitude": longitude,
                        "location_source": location_source,
                        "location_confidence": location_confidence,
                    },
                )
                aliases = []
                if row["city"] and row["state"]:
                    aliases.append((f"{row['city']}, {row['state']}", "place"))
                if row["postal_code"]:
                    aliases.append((row["postal_code"], "postal_code"))
                for display_name, kind in aliases:
                    Location.objects.get_or_create(
                        normalized_text=normalize_location(display_name),
                        defaults={
                            "display_name": display_name,
                            "latitude": latitude,
                            "longitude": longitude,
                            "kind": kind,
                            "state": row["state"].upper(),
                        },
                    )
                imported += 1
        self.stdout.write(
            self.style.SUCCESS(
                f"Imported {imported} fuel-price rows; skipped {skipped} rows without a local US place match."
            )
        )
