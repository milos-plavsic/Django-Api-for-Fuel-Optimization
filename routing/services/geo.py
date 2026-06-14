import math
import re
import unicodedata

import numpy as np


EARTH_RADIUS_MILES = 3958.8


def normalize_location(value):
    text = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def is_us_coordinate(latitude, longitude):
    boxes = (
        (24.0, 50.0, -125.0, -66.0),   # contiguous US
        (51.0, 72.0, -180.0, -129.0),  # Alaska
        (18.0, 23.0, -161.0, -154.0),  # Hawaii
    )
    return any(
        min_lat <= latitude <= max_lat and min_lon <= longitude <= max_lon
        for min_lat, max_lat, min_lon, max_lon in boxes
    )


def haversine(a, b):
    lon1, lat1 = a
    lon2, lat2 = b
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    value = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    return 2 * EARTH_RADIUS_MILES * math.atan2(math.sqrt(value), math.sqrt(1 - value))


def route_cumulative_miles(coordinates, route_distance_miles):
    values = np.radians(np.asarray(coordinates, dtype=float))
    if len(values) < 2:
        return [0.0] * len(values)
    longitude_delta = np.diff(values[:, 0])
    latitude_delta = np.diff(values[:, 1])
    segment = (
        np.sin(latitude_delta / 2) ** 2
        + np.cos(values[:-1, 1])
        * np.cos(values[1:, 1])
        * np.sin(longitude_delta / 2) ** 2
    )
    segment = np.clip(segment, 0, 1)
    segment_miles = 2 * EARTH_RADIUS_MILES * np.arctan2(
        np.sqrt(segment),
        np.sqrt(1 - segment),
    )
    raw = np.concatenate(([0.0], np.cumsum(segment_miles)))
    if not raw[-1]:
        return raw.tolist()
    return (raw * (route_distance_miles / raw[-1])).tolist()


def nearest_route_point(point, coordinates, cumulative):
    longitude_scale = math.cos(math.radians(point[1]))
    best_index = min(
        range(len(coordinates)),
        key=lambda index: (
            ((point[0] - coordinates[index][0]) * longitude_scale) ** 2
            + (point[1] - coordinates[index][1]) ** 2
        ),
    )
    return cumulative[best_index], haversine(point, coordinates[best_index])


def simplify_route(coordinates, tolerance=0.002, max_points=2000):
    if len(coordinates) <= 2:
        return coordinates

    tolerance_squared = tolerance * tolerance
    simplified = [coordinates[0]]
    for point in coordinates[1:-1]:
        previous = simplified[-1]
        if (
            (point[0] - previous[0]) ** 2 + (point[1] - previous[1]) ** 2
            >= tolerance_squared
        ):
            simplified.append(point)
    simplified.append(coordinates[-1])

    if len(simplified) <= max_points:
        return simplified
    step = (len(simplified) - 1) / (max_points - 1)
    indexes = [round(index * step) for index in range(max_points)]
    return [simplified[index] for index in indexes]
