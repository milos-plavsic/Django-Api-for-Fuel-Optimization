import csv
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from routing.models import HighwayJunction
from routing.services.station_location import normalize_highway


class Command(BaseCommand):
    help = "Import decoded highway junctions from a CSV for offline station geocoding."

    def add_arguments(self, parser):
        parser.add_argument("csv_path", type=Path)

    def handle(self, *args, **options):
        path = options["csv_path"]
        if not path.exists():
            raise CommandError(f"File does not exist: {path}")
        junctions = []
        with path.open(newline="", encoding="utf-8-sig") as stream:
            for row in csv.DictReader(stream):
                try:
                    highway = row["highway"].strip().upper()
                    if "-" not in highway:
                        highway = normalize_highway(row["highway_type"], highway)
                    junctions.append(
                        HighwayJunction(
                            state=row["state"].strip().upper(),
                            highway=highway,
                            exit_number=row["exit_number"].strip().upper(),
                            latitude=float(row["latitude"]),
                            longitude=float(row["longitude"]),
                            name=row.get("name", "").strip(),
                        )
                    )
                except (KeyError, TypeError, ValueError):
                    continue
        HighwayJunction.objects.bulk_create(junctions, ignore_conflicts=True, batch_size=1000)
        self.stdout.write(self.style.SUCCESS(f"Imported {len(junctions)} highway junction rows."))
