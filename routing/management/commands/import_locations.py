import csv
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from routing.models import Location
from routing.services.geo import is_us_coordinate, normalize_location


class Command(BaseCommand):
    help = "Import a local US geocoding CSV with text, latitude, longitude, and optional kind."

    def add_arguments(self, parser):
        parser.add_argument("csv_path", type=Path)

    def handle(self, *args, **options):
        path = options["csv_path"]
        if not path.exists():
            raise CommandError(f"File does not exist: {path}")
        imported = 0
        with path.open(newline="", encoding="utf-8-sig") as stream:
            for row in csv.DictReader(stream):
                try:
                    latitude = float(row["latitude"])
                    longitude = float(row["longitude"])
                    text = row["text"].strip()
                except (KeyError, TypeError, ValueError):
                    continue
                if not text or not is_us_coordinate(latitude, longitude):
                    continue
                Location.objects.update_or_create(
                    normalized_text=normalize_location(text),
                    defaults={
                        "display_name": row.get("display_name") or text,
                        "latitude": latitude,
                        "longitude": longitude,
                        "kind": row.get("kind") or "place",
                        "state": (row.get("state") or "").upper(),
                    },
                )
                imported += 1
        self.stdout.write(self.style.SUCCESS(f"Imported {imported} locations."))
