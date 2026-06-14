import re

from routing.models import HighwayJunction

from .geo import haversine


HIGHWAY_PATTERN = re.compile(r"\b(?P<kind>I|US|SR|ST|CR)-?\s*(?P<number>\d+)\b", re.IGNORECASE)
EXIT_PATTERN = re.compile(r"\bEXIT\s+(?P<exit>\d+[A-Z]?(?:-[A-Z])?)\b", re.IGNORECASE)


def normalize_highway(kind, number):
    kind = kind.upper()
    if kind == "ST":
        kind = "SR"
    return f"{kind}-{int(number)}"


def parse_station_address(address):
    highways = [
        normalize_highway(match.group("kind"), match.group("number"))
        for match in HIGHWAY_PATTERN.finditer(address)
    ]
    exit_match = EXIT_PATTERN.search(address)
    return {
        "highways": list(dict.fromkeys(highways)),
        "exit_number": exit_match.group("exit").upper() if exit_match else None,
    }


def resolve_station_coordinates(address, state, city_coordinates):
    parsed = parse_station_address(address)
    city_point = [city_coordinates[1], city_coordinates[0]] if city_coordinates else None
    if parsed["exit_number"]:
        candidates = HighwayJunction.objects.filter(
            state=state,
            exit_number=parsed["exit_number"],
            highway__in=parsed["highways"],
        )
        if city_coordinates:
            candidates = sorted(
                candidates,
                key=lambda junction: haversine(
                    [junction.longitude, junction.latitude],
                    city_point,
                ),
            )
        else:
            candidates = list(candidates)
        if candidates:
            junction = candidates[0]
            return junction.latitude, junction.longitude, "osm_highway_exit", 0.95

    if parsed["highways"] and city_coordinates:
        candidates = HighwayJunction.objects.filter(
            state=state,
            highway__in=parsed["highways"],
        )
        grouped = {}
        for junction in candidates:
            key = (junction.latitude, junction.longitude)
            grouped.setdefault(key, set()).add(junction.highway)
        if grouped:
            latitude, longitude = min(
                grouped,
                key=lambda point: (
                    -len(grouped[point].intersection(parsed["highways"])),
                    haversine([point[1], point[0]], city_point),
                ),
            )
            distance = haversine([longitude, latitude], city_point)
            if distance <= 75:
                matched_highways = len(grouped[(latitude, longitude)].intersection(parsed["highways"]))
                confidence = 0.75 if matched_highways > 1 else 0.6
                return latitude, longitude, "osm_highway_near_city", confidence

    if city_coordinates:
        return city_coordinates[0], city_coordinates[1], "city_centroid", 0.35
    return None
