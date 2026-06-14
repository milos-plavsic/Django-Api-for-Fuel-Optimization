import csv
import tempfile
from pathlib import Path

from django.core.management import call_command
from django.test import TestCase

from routing.models import FuelStation, PostalCodeLocation


class ImportStationsTests(TestCase):
    def test_price_row_without_coordinates_uses_local_city_match(self):
        PostalCodeLocation.objects.create(
            postal_code="12345",
            display_name="12345 - Example City, NY",
            latitude=42.8,
            longitude=-73.9,
            state="NY",
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "prices.csv"
            with path.open("w", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(
                    stream,
                    fieldnames=[
                        "OPIS Truckstop ID",
                        "Truckstop Name",
                        "Address",
                        "City",
                        "State",
                        "Retail Price",
                    ],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "OPIS Truckstop ID": "1",
                        "Truckstop Name": "Example Fuel",
                        "Address": "I-1 Exit 1",
                        "City": "Example City",
                        "State": "NY",
                        "Retail Price": "3.25",
                    }
                )

            call_command("import_stations", path)

        station = FuelStation.objects.get(external_id="1")
        self.assertEqual(station.latitude, 42.8)
        self.assertEqual(station.longitude, -73.9)
