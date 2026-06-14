import csv
from collections import defaultdict
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from routing.models import Location, PlaceLocation, PostalCodeLocation
from routing.services.geo import normalize_location


class Command(BaseCommand):
    help = "Import the GeoNames US postal-code TSV into the local geocoding database."

    def add_arguments(self, parser):
        parser.add_argument("tsv_path", type=Path)

    def handle(self, *args, **options):
        path = options["tsv_path"]
        if not path.exists():
            raise CommandError(f"File does not exist: {path}")

        locations = {}
        candidates = []
        places = defaultdict(list)
        with path.open(newline="", encoding="utf-8") as stream:
            reader = csv.reader(stream, delimiter="\t")
            for row in reader:
                if len(row) < 11 or row[0] != "US":
                    continue
                postal_code, place_name, state, state_code = row[1], row[2], row[3], row[4]
                try:
                    latitude = float(row[9])
                    longitude = float(row[10])
                except ValueError:
                    continue
                region = state_code or state
                display_name = f"{postal_code} - {place_name}" + (f", {region}" if region else "")
                candidates.append(
                    PostalCodeLocation(
                        postal_code=postal_code,
                        display_name=display_name,
                        latitude=latitude,
                        longitude=longitude,
                        state=state_code,
                    )
                )
                if state_code:
                    places[(normalize_location(place_name), state_code)].append(
                        (latitude, longitude, place_name)
                    )
                locations.setdefault(
                    postal_code,
                    Location(
                        normalized_text=postal_code,
                        display_name=display_name,
                        latitude=latitude,
                        longitude=longitude,
                        kind="postal_code",
                        state=state_code,
                    ),
                )

        PostalCodeLocation.objects.all().delete()
        PostalCodeLocation.objects.bulk_create(candidates, batch_size=1000)
        PlaceLocation.objects.all().delete()
        PlaceLocation.objects.bulk_create(
            [
                PlaceLocation(
                    normalized_name=normalized_name,
                    display_name=f"{values[0][2]}, {state_code}",
                    state=state_code,
                    latitude=sum(value[0] for value in values) / len(values),
                    longitude=sum(value[1] for value in values) / len(values),
                    postal_code_count=len(values),
                )
                for (normalized_name, state_code), values in places.items()
            ],
            batch_size=1000,
        )
        Location.objects.filter(kind="postal_code").delete()
        Location.objects.bulk_create(locations.values(), batch_size=1000)
        ambiguous = len(candidates) - len(locations)
        self.stdout.write(
            self.style.SUCCESS(
                f"Imported {len(candidates)} postal locations for {len(locations)} ZIP codes; "
                f"{ambiguous} additional ambiguous records retained."
            )
        )
