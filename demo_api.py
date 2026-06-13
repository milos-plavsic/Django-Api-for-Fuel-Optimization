import os
import django
import sys
import logging
import argparse

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'fuel_project.settings')
django.setup()

from optimizer.services import FuelOptimizationService

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("demo_api")

def run_demo(start, finish, mpg, fuel_capacity, current_fuel, safety_reserve):
    logger.info("--- Fuel Optimization Diagnostic Tool ---")
    logger.info(f"Route: {start} to {finish}")
    logger.info(f"Vehicle Profile: {mpg} MPG, {fuel_capacity} gal capacity, {current_fuel} gal current fuel")
    logger.info("-" * 50)
    
    try:
        # 1. Get Route
        logger.info("Fetching route geometry from OSRM...")
        geometry, total_distance = FuelOptimizationService.get_route(start, finish)
        logger.info(f"Total Distance: {total_distance:.2f} miles")
        
        # 2. Optimize Fuel
        logger.info("Running optimization algorithm...")
        route_coords = geometry['coordinates']
        fuel_stops, total_cost, total_detour, strategy = FuelOptimizationService.optimize_fuel_plan(
            route_coords, total_distance,
            mpg=mpg,
            fuel_capacity=fuel_capacity,
            current_fuel=current_fuel,
            safety_reserve_pct=safety_reserve
        )
        
        # 3. Output Results
        logger.info("-" * 50)
        logger.info(f"Strategy Used: {strategy}")
        logger.info(f"Total Detour: {total_detour:.2f} miles")
        
        if not fuel_stops:
            logger.info("Result: No fuel stops needed or none found within range.")
        else:
            logger.info(f"Result: Found {len(fuel_stops)} optimal fuel stops:")
            for i, stop in enumerate(fuel_stops, 1):
                logger.info(f"  Stop {i}: {stop['name']} ({stop['city']}, {stop['state']})")
                logger.info(f"          Price: ${stop['price']:.3f} | Dist: {stop['distance_along_route']:.1f} mi | Detour: {stop['detour_miles']:.2f} mi")
        
        logger.info("-" * 50)
        logger.info(f"FINAL TOTAL COST: ${total_cost:.2f}")
        logger.info("-" * 50)
        
    except Exception as e:
        logger.error(f"Diagnostic failed with error: {e}", exc_info=True)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fuel Optimization API Diagnostic Tool")
    parser.add_argument("--start", type=str, default="Nashville, TN", help="Start location")
    parser.add_argument("--finish", type=str, default="Dallas, TX", help="Finish location")
    parser.add_argument("--mpg", type=float, default=6.0, help="Miles per gallon")
    parser.add_argument("--capacity", type=float, default=150.0, help="Fuel capacity in gallons")
    parser.add_argument("--fuel", type=float, default=150.0, help="Current fuel in gallons")
    parser.add_argument("--reserve", type=float, default=0.1, help="Safety reserve percentage (0.0-1.0)")

    args = parser.parse_args()
    
    run_demo(args.start, args.finish, args.mpg, args.capacity, args.fuel, args.reserve)
