import csv
import pandas as pd
from django.core.management.base import BaseCommand
from optimizer.models import FuelStop
from django.conf import settings
import os

class Command(BaseCommand):
    help = 'Import fuel stops from geocoded_fuel_stops_v2.csv merged with fuel_stops.txt'

    def handle(self, *args, **options):
        geocoded_file = os.path.join(settings.BASE_DIR, '..', 'geocoded_fuel_stops_v2.csv')
        original_file = os.path.join(settings.BASE_DIR, '..', 'fuel_stops.txt')
        
        if not os.path.exists(geocoded_file):
            self.stdout.write(self.style.ERROR(f'File not found: {geocoded_file}'))
            return
        if not os.path.exists(original_file):
            self.stdout.write(self.style.ERROR(f'File not found: {original_file}'))
            return

        # Load geocoded data
        geo_df = pd.read_csv(geocoded_file)
        # Create a key for merging
        geo_df['key'] = geo_df['Truckstop Name'] + "|" + geo_df['Address'] + "|" + geo_df['City'] + "|" + geo_df['State']
        geo_map = geo_df.set_index('key')[['Latitude', 'Longitude']].to_dict('index')

        # Load original data
        orig_df = pd.read_csv(original_file, sep='\t')
        
        count = 0
        for _, row in orig_df.iterrows():
            key = str(row['Truckstop Name']) + "|" + str(row['Address']) + "|" + str(row['City']) + "|" + str(row['State'])
            
            if key in geo_map:
                lat = geo_map[key]['Latitude']
                lon = geo_map[key]['Longitude']
                
                if pd.isna(lat) or pd.isna(lon):
                    continue

                try:
                    FuelStop.objects.update_or_create(
                        opis_id=int(row['OPIS Truckstop ID']),
                        defaults={
                            'name': row['Truckstop Name'],
                            'address': row['Address'],
                            'city': row['City'],
                            'state': row['State'],
                            'retail_price': float(row['Retail Price']),
                            'latitude': float(lat),
                            'longitude': float(lon),
                        }
                    )
                    count += 1
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"Error importing row {row['OPIS Truckstop ID']}: {e}"))

        self.stdout.write(self.style.SUCCESS(f'Successfully imported {count} fuel stops'))
