import hashlib
import json

from django.conf import settings
from django.core.cache import cache
from django.db.models import Count, Max

from routing.models import FuelStation

from .optimizer import MPG, MAX_RANGE_MILES


PLAN_ALGORITHM_VERSION = "fuel-price-routes-v3"


def fuel_data_revision():
    revision = FuelStation.objects.aggregate(count=Count("id"), latest=Max("updated_at"))
    latest = revision["latest"].isoformat() if revision["latest"] else "empty"
    return f"{revision['count']}:{latest}"


def plan_cache_key(start_coordinates, finish_coordinates, solution="primary", route_count=1):
    payload = {
        "start": [round(value, 5) for value in start_coordinates],
        "finish": [round(value, 5) for value in finish_coordinates],
        "algorithm": PLAN_ALGORITHM_VERSION,
        "solution": solution,
        "route_count": route_count,
        "fuel_revision": fuel_data_revision(),
        "corridor": settings.STATION_CORRIDOR_MILES,
        "range": MAX_RANGE_MILES,
        "mpg": MPG,
        "response_route_tolerance": settings.RESPONSE_ROUTE_SIMPLIFY_TOLERANCE,
        "response_route_max_points": settings.RESPONSE_ROUTE_MAX_POINTS,
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return f"completed-plan:{digest}"


def get_cached_plan(key):
    return cache.get(key)


def cache_plan(key, result):
    try:
        cache.set(key, result, settings.PLAN_CACHE_SECONDS)
    except MemoryError:
        pass
