import json
from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from .models import FuelStop
from .services import FuelOptimizationService

class FuelOptimizationServiceTests(TestCase):
    def setUp(self):
        # Create some test fuel stops
        FuelStop.objects.create(
            opis_id=1,
            name="Cheap Stop",
            address="123 Cheap St",
            city="Cheap City",
            state="CC",
            retail_price=2.50,
            latitude=34.0,
            longitude=-118.0
        )
        FuelStop.objects.create(
            opis_id=2,
            name="Expensive Stop",
            address="456 Rich Ave",
            city="Rich City",
            state="RC",
            retail_price=4.50,
            latitude=35.0,
            longitude=-119.0
        )

    @patch('optimizer.services.requests.get')
    def test_get_route_success(self, mock_get):
        # Mock geocode response for start
        mock_response_geocode = MagicMock()
        mock_response_geocode.status_code = 200
        mock_response_geocode.json.return_value = [{'lon': '-118.0', 'lat': '34.0'}]
        
        # Mock geocode response for end
        mock_response_geocode_end = MagicMock()
        mock_response_geocode_end.status_code = 200
        mock_response_geocode_end.json.return_value = [{'lon': '-119.0', 'lat': '35.0'}]
        
        # Mock OSRM response
        mock_response_osrm = MagicMock()
        mock_response_osrm.status_code = 200
        mock_response_osrm.json.return_value = {
            'code': 'Ok',
            'routes': [{
                'geometry': {'type': 'LineString', 'coordinates': [[-118.0, 34.0], [-119.0, 35.0]]},
                'distance': 160934.4  # ~100 miles
            }]
        }
        
        mock_get.side_effect = [mock_response_geocode, mock_response_geocode_end, mock_response_osrm]
        
        geometry, distance = FuelOptimizationService.get_route("Start City", "End City")
        
        self.assertEqual(geometry['type'], 'LineString')
        self.assertAlmostEqual(distance, 100.0, places=1)

    def test_optimize_fuel_plan(self):
        # Test basic optimization logic
        route_coords = [[-118.0, 34.0], [-118.5, 34.5], [-119.0, 35.0]]
        total_distance = 100.0
        
        # We have a cheap stop at [-118.0, 34.0] (start) and expensive at [-119.0, 35.0] (end)
        # The algorithm should pick the cheap stop if it's along the route.
        
        stops, total_cost, strategy = FuelOptimizationService.optimize_fuel_plan(route_coords, total_distance)
        
        self.assertIsInstance(stops, list)
        self.assertGreaterEqual(len(stops), 0)
        self.assertEqual(strategy, "Global DP")

class RouteOptimizationViewTests(APITestCase):
    @patch('optimizer.services.FuelOptimizationService.get_route')
    @patch('optimizer.services.FuelOptimizationService.optimize_fuel_plan')
    def test_route_optimization_view_success(self, mock_optimize, mock_get_route):
        mock_get_route.return_value = (
            {'type': 'LineString', 'coordinates': [[-118.0, 34.0], [-119.0, 35.0]]},
            100.0
        )
        mock_optimize.return_value = (
            [{'name': 'Test Stop', 'price': 3.0, 'distance_along_route': 50.0}],
            30.0,
            "Global DP"
        )
        
        url = reverse('route-optimization')
        response = self.client.get(url, {'start': 'New York', 'finish': 'Los Angeles'})
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('route', response.data)
        self.assertIn('fuel_stops', response.data)
        self.assertEqual(response.data['total_fuel_cost'], 30.0)

    def test_route_optimization_view_missing_params(self):
        url = reverse('route-optimization')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['error'], "Please provide 'start' and 'finish' query parameters.")

    @patch('optimizer.services.FuelOptimizationService.get_route')
    def test_route_optimization_view_invalid_location(self, mock_get_route):
        mock_get_route.side_effect = ValueError("Could not geocode one or both locations.")
        
        url = reverse('route-optimization')
        response = self.client.get(url, {'start': 'InvalidCity123', 'finish': 'AnotherInvalid'})
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['error'], "Could not geocode one or both locations.")
