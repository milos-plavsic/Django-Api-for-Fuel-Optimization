import os
import django
import sys

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'fuel_project.settings')
django.setup()

from optimizer.services import FuelOptimizationService

def run_demo():
    start = "Nashville, TN"
    finish = "Dallas, TX"
    
    print(f"--- Fuel Optimization Demo ---")
    print(f"Route: {start} to {finish}")
    print(f"Vehicle Range: 500 miles | MPG: 10")
    print("-" * 30)
    
    try:
        # 1. Get Route
        print("Fetching route geometry from OSRM...")
        geometry, total_distance = FuelOptimizationService.get_route(start, finish)
        print(f"Total Distance: {total_distance:.2f} miles")
        
        # 2. Optimize Fuel
        print("Optimizing fuel stops...")
        route_coords = geometry['coordinates']
        fuel_stops, total_cost, opt_level = FuelOptimizationService.optimize_fuel_plan(route_coords, total_distance)
        
        # 3. Output Results
        print("-" * 30)
        print(f"Optimization Level: {opt_level}")
        if not fuel_stops:
            print("No fuel stops needed (destination reachable on one tank) or no stops found.")
        else:
            print(f"Found {len(fuel_stops)} optimal fuel stops:")
            for i, stop in enumerate(fuel_stops, 1):
                print(f"Stop {i}: {stop['name']} at {stop['address']}, {stop['city']}, {stop['state']}")
                print(f"        Price: ${stop['price']:.2f} | Distance: {stop['distance_along_route']:.2f} miles")
        
        print("-" * 30)
        print(f"Total Fuel Cost: ${total_cost:.2f}")
        print("-" * 30)
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    run_demo()
