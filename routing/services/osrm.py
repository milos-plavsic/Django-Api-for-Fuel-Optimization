import requests
from django.conf import settings
from django.core.cache import cache


class RoutingProviderError(Exception):
    pass


def get_routes(start, finish, max_routes=1):
    coordinate_key = ":".join(f"{value:.5f}" for value in (*start, *finish))
    cache_key = f"osrm-routes:{max_routes}:{coordinate_key}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached, 0

    coordinates = f"{start[0]},{start[1]};{finish[0]},{finish[1]}"
    url = f"{settings.OSRM_BASE_URL}/route/v1/driving/{coordinates}"
    try:
        response = requests.get(
            url,
            params={
                "overview": "full",
                "geometries": "geojson",
                "steps": "false",
                "alternatives": "false" if max_routes == 1 else str(max_routes),
            },
            timeout=settings.OSRM_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("code") != "Ok" or not payload.get("routes"):
            raise RoutingProviderError("No drivable route was found.")
        result = [
            {
                "geometry": route["geometry"],
                "distance_miles": route["distance"] / 1609.344,
                "duration_seconds": route["duration"],
                "toll_cost": None,
                "toll_currency": None,
            }
            for route in payload["routes"][:max_routes]
        ]
    except (requests.RequestException, KeyError, TypeError, ValueError) as exc:
        raise RoutingProviderError("The routing provider could not return a route.") from exc

    try:
        cache.set(cache_key, result, settings.ROUTE_CACHE_SECONDS)
    except MemoryError:
        pass
    return result, 1


def get_route(start, finish):
    routes, external_calls = get_routes(start, finish, max_routes=1)
    return routes[0], external_calls
