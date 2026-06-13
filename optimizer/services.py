import requests
import math
import numpy as np
import logging
from scipy.spatial import KDTree
from django.conf import settings
from django.core.cache import cache
from .models import FuelStop

logger = logging.getLogger(__name__)

# Global variables for KD-Tree singleton
_STOPS_TREE = None
_STOPS_LIST = None

def get_stops_data():
    """Lazily initializes and returns the KD-Tree and stops list singleton."""
    global _STOPS_TREE, _STOPS_LIST
    if _STOPS_TREE is None or _STOPS_LIST is None:
        logger.info("Initializing KD-Tree for fuel stops...")
        stops_qs = FuelStop.objects.all().only(
            'id', 'name', 'address', 'city', 'state', 'retail_price', 'latitude', 'longitude'
        )
        _STOPS_LIST = list(stops_qs)
        if _STOPS_LIST:
            coords = np.array([[s.longitude, s.latitude] for s in _STOPS_LIST])
            _STOPS_TREE = KDTree(coords)
            logger.info(f"KD-Tree successfully initialized with {len(_STOPS_LIST)} stops.")
        else:
            logger.warning("No fuel stops found in database during KD-Tree initialization.")
    return _STOPS_TREE, _STOPS_LIST

class FuelOptimizationService:
    OSRM_BASE_URL = "http://router.project-osrm.org/route/v1/driving/"

    @staticmethod
    def geocode(location):
        cache_key = f"geocode_{location.replace(' ', '_')}"
        cached = cache.get(cache_key)
        if cached:
            return cached

        url = f"https://nominatim.openstreetmap.org/search?q={location}&format=json&limit=1"
        headers = {'User-Agent': 'FuelOptimizationAPI/1.0'}
        try:
            response = requests.get(url, headers=headers)
            if response.status_code == 200 and response.json():
                data = response.json()[0]
                coords = (float(data['lon']), float(data['lat']))
                cache.set(cache_key, coords, 86400) # 24h
                return coords
        except Exception as e:
            logger.error(f"Geocoding error for {location}: {e}")
        return None

    @staticmethod
    def get_route(start_loc, end_loc):
        cache_key = f"route_{start_loc.replace(' ', '_')}_{end_loc.replace(' ', '_')}"
        cached = cache.get(cache_key)
        if cached:
            return cached

        start_coords = FuelOptimizationService.geocode(start_loc)
        end_coords = FuelOptimizationService.geocode(end_loc)

        if not start_coords or not end_coords:
            logger.error(f"Failed to geocode locations: {start_loc} -> {end_loc}")
            raise ValueError("Could not geocode one or both locations.")

        osrm_url = f"{FuelOptimizationService.OSRM_BASE_URL}{start_coords[0]},{start_coords[1]};{end_coords[0]},{end_coords[1]}?overview=full&geometries=geojson"
        try:
            response = requests.get(osrm_url)
            if response.status_code == 200:
                data = response.json()
                if data['code'] == 'Ok':
                    route = data['routes'][0]
                    geometry = route['geometry']
                    distance_meters = route['distance']
                    distance_miles = distance_meters * 0.000621371
                    result = (geometry, distance_miles)
                    cache.set(cache_key, result, 86400) # 24h as per infra refinement
                    return result
        except Exception as e:
            logger.error(f"OSRM request failed: {e}")
        
        raise Exception("Failed to fetch route from OSRM.")

    @staticmethod
    def ramer_douglas_peucker(points, epsilon):
        """Simplifies a path using RDP algorithm."""
        if len(points) < 3:
            return points

        def d2(p, a, b):
            # distance squared from point p to line segment ab
            ax, ay = a
            bx, by = b
            px, py = p
            dx, dy = bx - ax, by - ay
            if dx == 0 and dy == 0:
                return (px - ax)**2 + (py - ay)**2
            t = ((px - ax) * dx + (py - ay) * dy) / (dx**2 + dy**2)
            t = max(0, min(1, t))
            return (px - (ax + t * dx))**2 + (py - (ay + t * dy))**2

        dmax = 0
        index = 0
        for i in range(1, len(points) - 1):
            d = d2(points[i], points[0], points[-1])
            if d > dmax:
                index = i
                dmax = d

        if dmax > epsilon**2:
            res1 = FuelOptimizationService.ramer_douglas_peucker(points[:index+1], epsilon)
            res2 = FuelOptimizationService.ramer_douglas_peucker(points[index:], epsilon)
            return res1[:-1] + res2
        else:
            return [points[0], points[-1]]

    @staticmethod
    def find_stops_along_route(route_coords, corridor_width_miles=10):
        """Uses KD-Tree for efficient spatial search along the route."""
        # 1. Simplify route for spatial query efficiency
        simplified_route = FuelOptimizationService.ramer_douglas_peucker(route_coords, 0.01)
        
        # 2. Get stops data from singleton
        tree, stops_list = get_stops_data()
        
        if not tree:
            return []

        # 3. Find stops within corridor_width_miles of any simplified route point
        # approx 0.015 degrees per mile
        radius_deg = corridor_width_miles * 0.015
        relevant_indices = set()
        for pt in simplified_route:
            indices = tree.query_ball_point(pt, radius_deg)
            relevant_indices.update(indices)
        
        return [stops_list[i] for i in relevant_indices]

    @staticmethod
    def haversine(lon1, lat1, lon2, lat2):
        R = 3958.8 # miles
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        return R * c

    @staticmethod
    def optimize_fuel_plan(route_coords, total_distance, mpg=10, fuel_capacity=50, current_fuel=50, safety_reserve_pct=0.1, corridor_width_miles=10):
        """
        Implements Dynamic Programming to find the Global Minimum cost.
        Nodes: Start (0), End (N+1), and FuelStops along the route.
        Edges: A -> B is valid if fuel needed <= usable capacity.
        """
        logger.info(f"Optimizing fuel plan for {total_distance:.2f} miles route.")
        
        safety_reserve_amt = fuel_capacity * safety_reserve_pct
        max_usable_fuel = fuel_capacity - safety_reserve_amt
        max_range = max_usable_fuel * mpg
        
        # Usable fuel currently in tank
        initial_usable_fuel = max(0.0, current_fuel - safety_reserve_amt)
        initial_max_range = initial_usable_fuel * mpg

        all_stops = FuelOptimizationService.find_stops_along_route(route_coords, corridor_width_miles=corridor_width_miles)
        logger.info(f"Found {len(all_stops)} potential stops in corridor.")
        
        # Precompute cumulative distances along route for more accurate projection
        cum_dist = [0.0]
        for i in range(1, len(route_coords)):
            d = FuelOptimizationService.haversine(
                route_coords[i-1][0], route_coords[i-1][1],
                route_coords[i][0], route_coords[i][1]
            )
            cum_dist.append(cum_dist[-1] + d)
        
        # Project stops onto route
        stops_with_dist = []
        for stop in all_stops:
            min_dist_sq = float('inf')
            closest_idx = 0
            for i, pt in enumerate(route_coords):
                d_sq = (stop.longitude - pt[0])**2 + (stop.latitude - pt[1])**2
                if d_sq < min_dist_sq:
                    min_dist_sq = d_sq
                    closest_idx = i
            
            dist_along_route = cum_dist[closest_idx]
            detour_dist = FuelOptimizationService.haversine(
                stop.longitude, stop.latitude, 
                route_coords[closest_idx][0], route_coords[closest_idx][1]
            )
            
            stops_with_dist.append({
                'obj': stop,
                'dist': dist_along_route,
                'detour': detour_dist,
                'price': float(stop.retail_price)
            })
        
        stops_with_dist.sort(key=lambda x: x['dist'])

        # Nodes: 0=Start, 1..N=Stops, N+1=End
        nodes = [{'dist': 0, 'price': 0, 'detour': 0}] + stops_with_dist + [{'dist': cum_dist[-1], 'price': 0, 'detour': 0}]
        n = len(nodes)
        
        inf = float('inf')
        min_cost = [inf] * n
        parent = [-1] * n
        min_cost[0] = 0
        
        for i in range(1, n):
            for j in range(i):
                # Calculate distance from j to i considering detours
                d_segment = nodes[i]['dist'] - nodes[j]['dist']
                d_total = d_segment + nodes[j]['detour'] + nodes[i]['detour']
                
                reachable = False
                cost = 0.0
                
                if j == 0:
                    # From start
                    if d_total <= initial_max_range:
                        reachable = True
                        if i < n - 1: # Stopping at i
                            fuel_at_i = current_fuel - (d_total / mpg)
                            fuel_to_buy = fuel_capacity - fuel_at_i
                            cost = fuel_to_buy * nodes[i]['price']
                        else: # Going to end
                            cost = 0.0
                else:
                    # From a previous stop j
                    if d_total <= max_range:
                        reachable = True
                        if i < n - 1: # Stopping at i
                            # Since we filled up at j, we buy what we consumed
                            fuel_to_buy = d_total / mpg
                            cost = fuel_to_buy * nodes[i]['price']
                        else: # Going to end
                            cost = 0.0
                
                if reachable and min_cost[j] + cost < min_cost[i]:
                    min_cost[i] = min_cost[j] + cost
                    parent[i] = j

        # Path reconstruction
        stops_to_make = []
        total_detour = 0.0
        curr = parent[n-1]
        while curr > 0:
            node = nodes[curr]
            stop_obj = node['obj']
            total_detour += node['detour'] * 2 # In and out
            stops_to_make.append({
                "name": stop_obj.name,
                "address": stop_obj.address,
                "city": stop_obj.city,
                "state": stop_obj.state,
                "price": node['price'],
                "distance_along_route": node['dist'],
                "detour_miles": node['detour'],
                "latitude": stop_obj.latitude,
                "longitude": stop_obj.longitude
            })
            curr = parent[curr]
        
        stops_to_make.reverse()
        logger.info(f"Optimization complete. Total stops: {len(stops_to_make)}, Total cost: ${min_cost[n-1]:.2f}")
        return stops_to_make, min_cost[n-1], total_detour, "Global DP"


