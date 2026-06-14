from django.test import TestCase

from routing.models import HighwayJunction
from routing.services.station_location import parse_station_address, resolve_station_coordinates


class StationLocationTests(TestCase):
    def test_parses_exit_and_multiple_highways(self):
        parsed = parse_station_address("I-44, EXIT 283 & US-69")
        self.assertEqual(parsed["highways"], ["I-44", "US-69"])
        self.assertEqual(parsed["exit_number"], "283")

    def test_highway_exit_beats_city_centroid(self):
        HighwayJunction.objects.create(
            state="OK",
            highway="I-44",
            exit_number="283",
            latitude=36.5,
            longitude=-95.2,
        )
        result = resolve_station_coordinates(
            "I-44, EXIT 283 & US-69",
            "OK",
            (36.0, -95.0),
        )
        self.assertEqual(result, (36.5, -95.2, "osm_highway_exit", 0.95))

    def test_city_centroid_is_explicit_fallback(self):
        result = resolve_station_coordinates("US-46", "NJ", (40.9, -75.0))
        self.assertEqual(result, (40.9, -75.0, "city_centroid", 0.35))

    def test_highway_only_address_uses_nearest_highway_junction(self):
        HighwayJunction.objects.create(
            state="NJ",
            highway="US-46",
            exit_number="1",
            latitude=40.91,
            longitude=-75.01,
        )
        result = resolve_station_coordinates("US-46", "NJ", (40.9, -75.0))
        self.assertEqual(result, (40.91, -75.01, "osm_highway_near_city", 0.6))
