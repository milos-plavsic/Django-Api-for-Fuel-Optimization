import csv
from django.core.management.base import BaseCommand
from optimizer.models import FuelStop
from django.conf import settings
import os

class Command(BaseCommand):
    help = 'Import fuel stops from geocoded CSV'

    def handle(self, *args, **options):
        csv_file = os.path.join(settings.BASE_DIR, '..', 'geocoded_fuel_stops.csv')
        
        if not os.path.exists(csv_file):
            self.stdout.write(self.style.ERROR(f'File not found: {csv_file}'))
            return

        with open(csv_file, mode='r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            count = 0
            for row in reader:
                try:
                    FuelStop.objects.update_or_create(
                        opis_id=int(row['OPIS Truckstop ID']),
                        defaults={
                            'name': row['Truckstop Name'],
                            'address': row['Address'],
                            'city': row['City'],
                            'state': row['State'],
                            'retail_price': float(row['Retail Price']),
                            'latitude': float(row['Latitude']) if row['Latitude'] else None,
                            'longitude': float(row['Longitude']) if row['Longitude'] else None,
                        }
                    )
                    count += 1
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"Error importing row {row['OPIS Truckstop ID']}: {e}"))

        self.stdout.write(self.style.SUCCESS(f'Successfully imported {count} fuel stops'))
