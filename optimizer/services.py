import requests
import math
from django.conf import settings
from .models import FuelStop

class FuelOptimizationService:
    OSRM_BASE_URL = "http://router.project-osrm.org/route/v1/driving/"

    @staticmethod
    def get_route(start_loc, end_loc):
        """
        Calls OSRM API to get the route between start_loc and end_loc.
        Expects locations as "City, State".
        """
        # First, geocode the city/state names to lat/lon if needed.
        # For simplicity in this implementation, we assume start_loc and end_loc 
        # can be geocoded or we use a geocoding service.
        # Let's use Nominatim for geocoding.
        
        def geocode(location):
            url = f"https://nominatim.openstreetmap.org/search?q={location}&format=json&limit=1"
            headers = {'User-Agent': 'FuelOptimizationAPI/1.0'}
            response = requests.get(url, headers=headers)
            if response.status_code == 200 and response.json():
                data = response.json()[0]
                return float(data['lon']), float(data['lat'])
            return None

        start_coords = geocode(start_loc)
        end_coords = geocode(end_loc)

        if not start_coords or not end_coords:
            raise ValueError("Could not geocode one or both locations.")

        osrm_url = f"{FuelOptimizationService.OSRM_BASE_URL}{start_coords[0]},{start_coords[1]};{end_coords[0]},{end_coords[1]}?overview=full&geometries=geojson"
        response = requests.get(osrm_url)
        if response.status_code == 200:
            data = response.json()
            if data['code'] == 'Ok':
                route = data['routes'][0]
                geometry = route['geometry']
                distance_meters = route['distance']
                distance_miles = distance_meters * 0.000621371
                return geometry, distance_miles
        
        raise Exception("Failed to fetch route from OSRM.")

    @staticmethod
    def find_stops_along_route(route_coords):
        """
        Finds FuelStop objects within ~5km of any point on the route.
        route_coords is a list of [lon, lat] pairs.
        """
        # To avoid excessive DB queries, we can use a bounding box approach first
        # then refine with distance calculation if necessary.
        # For a more "state-of-the-art" approach, we'd use PostGIS, 
        # but with SQLite we'll do a simple approximation.
        
        lons = [c[0] for c in route_coords]
        lats = [c[1] for c in route_coords]
        
        min_lon, max_lon = min(lons), max(lons)
        min_lat, max_lat = min(lats), max(lats)
        
        # Add a small buffer (~5km is roughly 0.045 degrees)
        buffer = 0.045
        relevant_stops = FuelStop.objects.filter(
            longitude__range=(min_lon - buffer, max_lon + buffer),
            latitude__range=(min_lat - buffer, max_lat + buffer)
        )
        
        stops_along_route = []
        for stop in relevant_stops:
            # Check if stop is near any point on the route
            # For efficiency, we can sample the route points or use a more robust path-distance algorithm
            is_near = False
            for i in range(0, len(route_coords), max(1, len(route_coords) // 100)):
                point = route_coords[i]
                dist = FuelOptimizationService.haversine(stop.longitude, stop.latitude, point[0], point[1])
                if dist <= 5.0: # 5km
                    is_near = True
                    break
            if is_near:
                stops_along_route.append(stop)
                
        return stops_along_route

    @staticmethod
    def haversine(lon1, lat1, lon2, lat2):
        # Calculate distance in km
        R = 6371
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        return R * c

    @staticmethod
    def optimize_fuel_plan(route_coords, total_distance):
        """
        Optimizes fuel stops along the route.
        Start with full tank (500 miles). MPG = 10.
        Logic: Every 400-450 miles, identify reachable stops within next 50-100 miles.
        Select the CHEAPEST one.
        """
        mpg = 10
        tank_capacity = 500
        current_fuel_range = tank_capacity
        total_cost = 0.0
        stops_to_make = []
        
        all_stops = FuelOptimizationService.find_stops_along_route(route_coords)
        if not all_stops:
            return [], 0.0

        # Map stops to their approximate distance along the route
        # This is a simplified approach
        stops_with_dist = []
        for stop in all_stops:
            # Find closest point on route to get approx distance
            min_dist = float('inf')
            closest_idx = 0
            for i, pt in enumerate(route_coords):
                d = FuelOptimizationService.haversine(stop.longitude, stop.latitude, pt[0], pt[1])
                if d < min_dist:
                    min_dist = d
                    closest_idx = i
            
            # Distance along route in miles
            dist_along_route = (closest_idx / len(route_coords)) * total_distance
            stops_with_dist.append((stop, dist_along_route))
            
        stops_with_dist.sort(key=lambda x: x[1])
        
        current_pos = 0
        while current_pos + current_fuel_range < total_distance:
            # Need to refuel
            # Search for stops between (current_pos + 400) and (current_pos + 500)
            window_start = current_pos + 400
            window_end = current_pos + 500
            
            reachable_stops = [s for s in stops_with_dist if window_start <= s[1] <= window_end]
            
            if not reachable_stops:
                # If no stops in preferred window, take the cheapest reachable stop before running out
                reachable_stops = [s for s in stops_with_dist if current_pos < s[1] <= window_end]
            
            if not reachable_stops:
                # Still no stops? This route might be impossible with these constraints
                # or our stop data is sparse. Take the last available stop if any.
                break
                
            # Select cheapest
            cheapest_stop_data = min(reachable_stops, key=lambda x: x[0].retail_price)
            stop_obj = cheapest_stop_data[0]
            stop_dist = cheapest_stop_data[1]
            
            # Calculate fuel needed to fill up (assuming we fill up to 500 miles range)
            # For simplicity, let's say we fill the whole tank
            # Cost = tank_capacity / mpg * price (simplified)
            # Actual cost would depend on how much we consumed.
            fuel_consumed = (stop_dist - current_pos) / mpg
            cost = float(fuel_consumed) * float(stop_obj.retail_price)
            
            stops_to_make.append({
                "name": stop_obj.name,
                "address": stop_obj.address,
                "city": stop_obj.city,
                "state": stop_obj.state,
                "price": float(stop_obj.retail_price),
                "distance_along_route": stop_dist
            })
            total_cost += cost
            
            current_pos = stop_dist
            current_fuel_range = tank_capacity
            
        return stops_to_make, total_cost
