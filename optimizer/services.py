import requests
import math
import numpy as np
from scipy.spatial import KDTree
from django.conf import settings
from django.core.cache import cache
from .models import FuelStop

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
        except Exception:
            pass
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
                result = (geometry, distance_miles)
                cache.set(cache_key, result, 3600) # 1h
                return result
        
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
    def find_stops_along_route(route_coords):
        """Uses KD-Tree for efficient spatial search along the route."""
        # 1. Simplify route for spatial query efficiency
        # epsilon ~ 0.01 deg is roughly 1km
        simplified_route = FuelOptimizationService.ramer_douglas_peucker(route_coords, 0.01)
        
        # 2. Get all stops from DB (caching KD-Tree would be better if data is static)
        stops_cache_key = "all_fuel_stops_kdtree"
        cached_data = cache.get(stops_cache_key)
        
        if cached_data:
            tree, stops_list = cached_data
        else:
            stops_qs = FuelStop.objects.all().only('id', 'name', 'address', 'city', 'state', 'retail_price', 'latitude', 'longitude')
            stops_list = list(stops_qs)
            if not stops_list:
                return []
            coords = np.array([[s.longitude, s.latitude] for s in stops_list])
            tree = KDTree(coords)
            cache.set(stops_cache_key, (tree, stops_list), 3600)

        # 3. Find stops within ~3 miles (0.045 degrees approx) of any simplified route point
        relevant_indices = set()
        for pt in simplified_route:
            indices = tree.query_ball_point(pt, 0.045)
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
    def optimize_fuel_plan(route_coords, total_distance):
        """
        Implements Dynamic Programming to find the Global Minimum cost.
        Nodes: Start (0), End (N+1), and FuelStops along the route.
        Edges: A -> B is valid if dist(A, B) <= 500 miles.
        Cost(A, B) = (dist(A, B) / 10 MPG) * Price(B).
        """
        mpg = 10
        tank_capacity = 500
        
        all_stops = FuelOptimizationService.find_stops_along_route(route_coords)
        
        # Project stops onto route to get distances
        # For Dijkstra/DP, we need stops ordered by distance from start
        stops_with_dist = []
        for stop in all_stops:
            # Find closest point on route
            # Using simple distance to closest route point
            min_dist = float('inf')
            closest_idx = 0
            for i, pt in enumerate(route_coords):
                d = (stop.longitude - pt[0])**2 + (stop.latitude - pt[1])**2
                if d < min_dist:
                    min_dist = d
                    closest_idx = i
            
            dist_along_route = (closest_idx / (len(route_coords)-1)) * total_distance
            # Calculate detour cost: Stop is some distance off route
            detour_dist = FuelOptimizationService.haversine(stop.longitude, stop.latitude, route_coords[closest_idx][0], route_coords[closest_idx][1])
            
            stops_with_dist.append({
                'obj': stop,
                'dist': dist_along_route,
                'detour': detour_dist
            })
        
        stops_with_dist.sort(key=lambda x: x['dist'])

        # Nodes: 0 is start, 1..N are stops, N+1 is destination
        nodes = [{'dist': 0, 'price': 0, 'detour': 0}] + stops_with_dist + [{'dist': total_distance, 'price': 0, 'detour': 0}]
        n = len(nodes)
        
        # DP: min_cost[i] = minimum cost to reach node i with full tank
        # Actually, simpler to think: min_cost[i] is min cost to reach i and refuel there.
        # But we start with full tank, so cost to reach 0 is 0.
        
        inf = float('inf')
        min_cost = [inf] * n
        parent = [-1] * n
        min_cost[0] = 0
        
        for i in range(1, n):
            for j in range(i):
                # Distance from node j to node i
                # If we are at node j (refueled), can we reach node i?
                # Distance includes detour to j and detour to i if they are stops
                d = nodes[i]['dist'] - nodes[j]['dist']
                
                # If d > 500, we can't reach i from j directly
                if d > tank_capacity:
                    continue
                
                # Cost to go from j to i and refuel at i
                # Fuel consumed = d / 10
                fuel_consumed = d / mpg
                price = float(nodes[i]['obj'].retail_price) if i < n-1 else 0
                trip_cost = fuel_consumed * price
                
                if min_cost[j] + trip_cost < min_cost[i]:
                    min_cost[i] = min_cost[j] + trip_cost
                    parent[i] = j

        # Path reconstruction
        stops_to_make = []
        curr = parent[n-1] # Last stop before destination
        while curr > 0:
            node = nodes[curr]
            stop_obj = node['obj']
            stops_to_make.append({
                "name": stop_obj.name,
                "address": stop_obj.address,
                "city": stop_obj.city,
                "state": stop_obj.state,
                "price": float(stop_obj.retail_price),
                "distance_along_route": node['dist']
            })
            curr = parent[curr]
        
        stops_to_make.reverse()
        return stops_to_make, min_cost[n-1], "Global DP"
