from unittest.mock import Mock, patch

from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from routing.models import FuelStation, Location, PlaceLocation, PostalCodeLocation


class UiTests(TestCase):
    def test_index_page_loads(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Fuel Route Planner")
        self.assertContains(response, "/api/route/")
        self.assertContains(response, "Fueling stops")
        self.assertContains(response, 'id="stop-count"')
        self.assertContains(response, "/api/route-alternative/")
        self.assertContains(response, "/api/route-three/")
        self.assertContains(response, "/api/route-milp/")
        self.assertContains(response, 'id="optimization-method"')
        self.assertContains(response, 'id="route-count"')
        self.assertContains(response, 'id="request-json"')
        self.assertContains(response, 'id="response-json"')
        self.assertNotContains(response, 'id="plan-cache"')


class RouteApiTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        Location.objects.create(
            normalized_text="new york ny",
            display_name="New York, NY",
            latitude=40.7128,
            longitude=-74.0060,
        )
        Location.objects.create(
            normalized_text="19103",
            display_name="19103 - Philadelphia, PA",
            latitude=39.9526,
            longitude=-75.1652,
            kind="postal_code",
            state="PA",
        )
        PostalCodeLocation.objects.create(
            postal_code="19103",
            display_name="19103 - Philadelphia, PA",
            latitude=39.9526,
            longitude=-75.1652,
            state="PA",
        )

    @patch("routing.services.osrm.requests.get")
    def test_text_and_postal_code_use_exactly_one_external_call(self, request_get):
        request_get.return_value = Mock(
            json=lambda: {
                "code": "Ok",
                "routes": [{
                    "distance": 160934.4,
                    "duration": 7200,
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [[-74.0060, 40.7128], [-75.1652, 39.9526]],
                    },
                }],
            },
            raise_for_status=lambda: None,
        )
        response = self.client.post(
            "/api/route/",
            {"start": "New York, NY", "finish": "19103"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["routing_api_calls"], 1)
        self.assertEqual(response.data["solution"], "primary")
        self.assertEqual(response.data["routes_evaluated"], 1)
        self.assertEqual(response.data["routes_requested"], 1)
        self.assertEqual(response.data["optimization_method"], "fuel_price_greedy")
        self.assertNotIn("plan_cache_hit", response.data)
        self.assertEqual(request_get.call_count, 1)

        cached_response = self.client.post(
            "/api/route/",
            {"start": "New York, NY", "finish": "19103"},
            format="json",
        )
        self.assertEqual(cached_response.data["routing_api_calls"], 0)
        self.assertNotIn("plan_cache_hit", cached_response.data)
        self.assertEqual(request_get.call_count, 1)

    @patch("routing.services.osrm.requests.get")
    def test_two_route_solution_evaluates_routes_from_one_call(self, request_get):
        request_get.return_value = Mock(
            json=lambda: {
                "code": "Ok",
                "routes": [
                    {
                        "distance": 160934.4,
                        "duration": 7200,
                        "geometry": {
                            "type": "LineString",
                            "coordinates": [[-74.0060, 40.7128], [-75.1652, 39.9526]],
                        },
                    },
                    {
                        "distance": 177027.84,
                        "duration": 7600,
                        "geometry": {
                            "type": "LineString",
                            "coordinates": [[-74.0060, 40.7128], [-75.0, 40.1], [-75.1652, 39.9526]],
                        },
                    },
                ],
            },
            raise_for_status=lambda: None,
        )
        response = self.client.post(
            "/api/route-alternative/",
            {"start": "New York, NY", "finish": "19103"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["solution"], "two_routes")
        self.assertEqual(response.data["routes_evaluated"], 2)
        self.assertEqual(response.data["routing_api_calls"], 1)
        self.assertEqual(request_get.call_count, 1)

    def test_invalid_text_is_declined_without_external_call(self):
        with patch("routing.services.osrm.requests.get") as request_get:
            response = self.client.post(
                "/api/route/",
                {"start": "not a real place", "finish": "19103"},
                format="json",
            )
        self.assertEqual(response.status_code, 400)
        request_get.assert_not_called()

    def test_route_count_must_be_between_one_and_five(self):
        response = self.client.post(
            "/api/route/",
            {"start": "New York, NY", "finish": "19103", "route_count": 6},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    @patch("routing.services.osrm.requests.get")
    def test_requested_route_count_is_sent_and_all_returned_routes_are_evaluated(
        self,
        request_get,
    ):
        route = {
            "distance": 160934.4,
            "duration": 7200,
            "geometry": {
                "type": "LineString",
                "coordinates": [[-74.0060, 40.7128], [-75.1652, 39.9526]],
            },
        }
        request_get.return_value = Mock(
            json=lambda: {"code": "Ok", "routes": [route, route]},
            raise_for_status=lambda: None,
        )
        response = self.client.post(
            "/api/route-milp/",
            {"start": "New York, NY", "finish": "19103", "route_count": 5},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["routes_requested"], 5)
        self.assertEqual(response.data["routes_evaluated"], 2)
        self.assertEqual(request_get.call_args.kwargs["params"]["alternatives"], "true")


    def test_coordinates_outside_us_are_declined(self):
        response = self.client.post(
            "/api/route/",
            {
                "start": {"latitude": 48.8566, "longitude": 2.3522},
                "finish": {"latitude": 40.7128, "longitude": -74.0060},
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_postal_code_with_matching_state_resolves(self):
        from routing.services.resolver import resolve_location

        location = resolve_location("pa 19103")
        self.assertEqual(location["display_name"], "19103 - Philadelphia, PA")

    def test_postal_code_with_wrong_state_is_declined(self):
        from rest_framework.exceptions import ValidationError
        from routing.services.resolver import resolve_location

        with self.assertRaisesMessage(ValidationError, "does not match MA"):
            resolve_location("MA 19103")

    def test_ambiguous_postal_code_is_declined_without_state(self):
        from rest_framework.exceptions import ValidationError
        from routing.services.resolver import resolve_location

        PostalCodeLocation.objects.bulk_create([
            PostalCodeLocation(
                postal_code="96860",
                display_name="96860 - Jbphh, HI",
                latitude=21.316,
                longitude=-157.8677,
                state="HI",
            ),
            PostalCodeLocation(
                postal_code="96860",
                display_name="96860 - FPO AA",
                latitude=21.3448,
                longitude=-157.9774,
                state="",
            ),
        ])
        with self.assertRaisesMessage(ValidationError, "is ambiguous"):
            resolve_location("96860")
        self.assertEqual(resolve_location("HI 96860")["display_name"], "96860 - Jbphh, HI")

    def test_unique_bare_city_resolves(self):
        from routing.services.resolver import resolve_location

        PlaceLocation.objects.create(
            normalized_name="bakersfield",
            display_name="Bakersfield, CA",
            state="CA",
            latitude=35.37,
            longitude=-119.02,
        )
        self.assertEqual(resolve_location("Bakersfield")["display_name"], "Bakersfield, CA")

    def test_ambiguous_bare_city_requires_state(self):
        from rest_framework.exceptions import ValidationError
        from routing.services.resolver import resolve_location

        PlaceLocation.objects.bulk_create([
            PlaceLocation(
                normalized_name="springfield",
                display_name="Springfield, IL",
                state="IL",
                latitude=39.8,
                longitude=-89.6,
            ),
            PlaceLocation(
                normalized_name="springfield",
                display_name="Springfield, MO",
                state="MO",
                latitude=37.2,
                longitude=-93.3,
            ),
        ])
        with self.assertRaisesMessage(ValidationError, "is ambiguous"):
            resolve_location("Springfield")
        self.assertEqual(resolve_location("Springfield MO")["display_name"], "Springfield, MO")

    def test_dominant_bare_city_resolves(self):
        from routing.services.resolver import resolve_location

        PlaceLocation.objects.bulk_create([
            PlaceLocation(
                normalized_name="bakersfield",
                display_name="Bakersfield, CA",
                state="CA",
                latitude=35.37,
                longitude=-119.02,
                postal_code_count=20,
            ),
            PlaceLocation(
                normalized_name="bakersfield",
                display_name="Bakersfield, MO",
                state="MO",
                latitude=36.5,
                longitude=-92.1,
                postal_code_count=1,
            ),
        ])
        location = resolve_location("Bakersfield")
        self.assertEqual(location["display_name"], "Bakersfield, CA")
        self.assertEqual(location["source"], "dominant_place")


class FuelPlanTests(TestCase):
    def test_milp_solution_returns_optimal_fuel_price_plan(self):
        from routing.services.milp_optimizer import optimize_fuel_stops_milp

        stations = [
            {"route_mile": 400, "detour_miles": 0, "price_per_gallon": 4.0, "name": "A"},
            {"route_mile": 700, "detour_miles": 0, "price_per_gallon": 3.0, "name": "B"},
        ]
        result = optimize_fuel_stops_milp(stations, 900)
        self.assertEqual(result["total_fuel_cost"], 140.0)
        self.assertEqual(result["optimization_method"], "milp_fuel_price")
        self.assertTrue(result["optimization_optimality_proven"])

    def test_station_purchases_are_priced_where_fuel_is_bought(self):
        from routing.services.optimizer import optimize_fuel_stops

        stations = [
            {"route_mile": 400, "detour_miles": 0, "price_per_gallon": 4.0, "name": "A"},
            {"route_mile": 700, "detour_miles": 0, "price_per_gallon": 3.0, "name": "B"},
        ]
        result = optimize_fuel_stops(stations, 900)
        self.assertEqual([stop["name"] for stop in result["fuel_stops"]], ["A", "B"])
        self.assertEqual(result["total_fuel_cost"], 140.0)

    def test_departure_skips_expensive_reachable_station(self):
        from routing.services.optimizer import optimize_fuel_stops

        stations = [
            {"route_mile": 100, "detour_miles": 0, "price_per_gallon": 5.0, "name": "Expensive"},
            {"route_mile": 400, "detour_miles": 0, "price_per_gallon": 3.0, "name": "Cheap"},
        ]
        result = optimize_fuel_stops(stations, 700)
        self.assertEqual([stop["name"] for stop in result["fuel_stops"]], ["Cheap"])

    def test_impossible_route_returns_explicit_error(self):
        from routing.services.optimizer import NoFeasibleFuelPlan, optimize_fuel_stops

        with self.assertRaises(NoFeasibleFuelPlan) as context:
            optimize_fuel_stops([], 501)
        self.assertEqual(context.exception.last_reachable_mile, 0)
        self.assertEqual(context.exception.next_available_mile, 501)
        self.assertEqual(context.exception.gap_miles, 501)

    def test_optimizer_avoids_cheapest_station_that_leads_to_dead_end(self):
        from routing.services.optimizer import optimize_fuel_stops

        stations = [
            {"route_mile": 100, "detour_miles": 390, "price_per_gallon": 2.0, "name": "Dead end"},
            {"route_mile": 450, "detour_miles": 0, "price_per_gallon": 4.0, "name": "Viable A"},
            {"route_mile": 900, "detour_miles": 0, "price_per_gallon": 3.0, "name": "Viable B"},
        ]
        result = optimize_fuel_stops(stations, 1200)
        self.assertEqual([stop["name"] for stop in result["fuel_stops"]], ["Viable A", "Viable B"])

    def test_route_sampling_preserves_endpoints_and_distances(self):
        from routing.services.stations import sampled_route

        coordinates = [[float(index), 0.0] for index in range(2500)]
        cumulative = [float(index) for index in range(2500)]
        sampled_coordinates, sampled_cumulative = sampled_route(coordinates, cumulative)
        self.assertLessEqual(len(sampled_coordinates), 1251)
        self.assertEqual(sampled_coordinates[0], coordinates[0])
        self.assertEqual(sampled_coordinates[-1], coordinates[-1])
        self.assertEqual(sampled_cumulative[-1], cumulative[-1])

    def test_colocated_stations_keep_only_cheapest_price(self):
        from routing.services.stations import cheapest_colocated_stations

        stations = [
            {"latitude": 40.0, "longitude": -75.0, "price_per_gallon": 3.5, "name": "High"},
            {"latitude": 40.0, "longitude": -75.0, "price_per_gallon": 3.0, "name": "Low"},
        ]
        result = cheapest_colocated_stations(stations)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["name"], "Low")

    def test_dominated_station_at_same_route_point_is_removed(self):
        from routing.services.stations import remove_dominated_stations

        stations = [
            {
                "route_mile": 100.0,
                "detour_miles": 1.0,
                "price_per_gallon": 3.0,
                "name": "Dominant",
            },
            {
                "route_mile": 100.0,
                "detour_miles": 2.0,
                "price_per_gallon": 3.5,
                "name": "Dominated",
            },
            {
                "route_mile": 100.0,
                "detour_miles": 0.5,
                "price_per_gallon": 4.0,
                "name": "Shorter detour",
            },
        ]
        result = remove_dominated_stations(stations)
        self.assertEqual(
            {station["name"] for station in result},
            {"Dominant", "Shorter detour"},
        )

    def test_spatial_projection_finds_nearest_route_point(self):
        from routing.services.stations import project_stations_onto_route

        stations = [{"longitude": -100.01, "latitude": 40.01}]
        projected = project_stations_onto_route(
            stations,
            [[-100.0, 40.0], [-99.0, 40.0]],
            [0.0, 53.0],
        )
        self.assertEqual(projected[0][1], 0.0)
        self.assertLess(projected[0][2], 1.0)

    def test_response_route_simplification_preserves_endpoints_and_limit(self):
        from routing.services.geo import simplify_route

        coordinates = [
            [index / 1000, (index % 5) / 1000]
            for index in range(5000)
        ]
        result = simplify_route(coordinates, tolerance=0.0001, max_points=200)
        self.assertEqual(result[0], coordinates[0])
        self.assertEqual(result[-1], coordinates[-1])
        self.assertLessEqual(len(result), 200)

    def test_global_plan_avoids_descending_price_micro_stops(self):
        from routing.services.optimizer import optimize_fuel_stops

        stations = [
            {"route_mile": mile, "detour_miles": 0, "price_per_gallon": price, "name": str(mile)}
            for mile, price in [(400, 3.10), (410, 3.09), (420, 3.08), (500, 3.07), (900, 3.05)]
        ]
        result = optimize_fuel_stops(stations, 1000)
        self.assertLessEqual(len(result["fuel_stops"]), 2)
        self.assertTrue(all(stop["gallons_purchased"] > 1 for stop in result["fuel_stops"]))
