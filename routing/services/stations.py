import numpy as np
from django.conf import settings
from scipy.spatial import cKDTree

from routing.models import FuelStation

from .geo import EARTH_RADIUS_MILES, route_cumulative_miles


def sampled_route(coordinates, cumulative, max_points=1000):
    if len(coordinates) <= max_points:
        return coordinates, cumulative
    step = max(1, len(coordinates) // (max_points - 1))
    indexes = list(range(0, len(coordinates), step))
    if indexes[-1] != len(coordinates) - 1:
        indexes.append(len(coordinates) - 1)
    return (
        [coordinates[index] for index in indexes],
        [cumulative[index] for index in indexes],
    )


def cheapest_colocated_stations(stations):
    cheapest = {}
    for station in stations:
        key = (round(station["latitude"], 5), round(station["longitude"], 5))
        existing = cheapest.get(key)
        if existing is None or station["price_per_gallon"] < existing["price_per_gallon"]:
            cheapest[key] = station
    return list(cheapest.values())


def remove_dominated_stations(stations):
    by_route_mile = {}
    for station in stations:
        by_route_mile.setdefault(station["route_mile"], []).append(station)

    result = []
    for colocated in by_route_mile.values():
        for candidate in colocated:
            if not any(
                other is not candidate
                and other["price_per_gallon"] <= candidate["price_per_gallon"]
                and other["detour_miles"] <= candidate["detour_miles"]
                and (
                    other["price_per_gallon"] < candidate["price_per_gallon"]
                    or other["detour_miles"] < candidate["detour_miles"]
                )
                for other in colocated
            ):
                result.append(candidate)
    return result


def spherical_coordinates(coordinates):
    values = np.radians(np.asarray(coordinates, dtype=float))
    longitudes = values[:, 0]
    latitudes = values[:, 1]
    cos_latitudes = np.cos(latitudes)
    return np.column_stack(
        (
            cos_latitudes * np.cos(longitudes),
            cos_latitudes * np.sin(longitudes),
            np.sin(latitudes),
        )
    )


def project_stations_onto_route(stations, route_coordinates, route_cumulative):
    if not stations:
        return []

    route_tree = cKDTree(spherical_coordinates(route_coordinates))
    station_coordinates = [
        [station["longitude"], station["latitude"]] for station in stations
    ]
    chord_distances, nearest_indexes = route_tree.query(
        spherical_coordinates(station_coordinates),
        workers=-1,
    )
    arc_distances = 2 * EARTH_RADIUS_MILES * np.arcsin(
        np.clip(chord_distances / 2, 0, 1)
    )

    return [
        (
            station,
            route_cumulative[int(nearest_index)],
            float(detour),
        )
        for station, nearest_index, detour in zip(
            stations,
            nearest_indexes,
            arc_distances,
        )
    ]


def stations_along_route(route_geometry, route_distance_miles):
    coordinates = route_geometry["coordinates"]
    cumulative = route_cumulative_miles(coordinates, route_distance_miles)
    search_coordinates, search_cumulative = sampled_route(coordinates, cumulative)
    longitudes = [point[0] for point in coordinates]
    latitudes = [point[1] for point in coordinates]
    margin = settings.STATION_CORRIDOR_MILES / 50

    candidates = list(
        FuelStation.objects.filter(
            longitude__gte=min(longitudes) - margin,
            longitude__lte=max(longitudes) + margin,
            latitude__gte=min(latitudes) - margin,
            latitude__lte=max(latitudes) + margin,
        ).values(
            "id",
            "name",
            "address",
            "city",
            "state",
            "postal_code",
            "latitude",
            "longitude",
            "location_source",
            "location_confidence",
            "price_per_gallon",
        )
    )

    result = []
    for station, route_mile, detour in project_stations_onto_route(
            candidates,
            search_coordinates,
            search_cumulative,
        ):
        if detour <= settings.STATION_CORRIDOR_MILES:
            result.append(
                {
                    **station,
                    "price_per_gallon": float(station["price_per_gallon"]),
                    "route_mile": route_mile,
                    "detour_miles": detour,
                }
            )
    stations = cheapest_colocated_stations(result)
    stations = remove_dominated_stations(stations)
    return sorted(stations, key=lambda station: station["route_mile"])
