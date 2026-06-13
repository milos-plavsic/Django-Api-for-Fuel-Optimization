from django.shortcuts import render
from django.views import View
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .services import FuelOptimizationService

class IndexView(View):
    def get(self, request):
        return render(request, 'index.html')

class RouteOptimizationView(APIView):
    def get(self, request):
        start = request.query_params.get('start')
        finish = request.query_params.get('finish')

        if not start or not finish:
            return Response(
                {"error": "Please provide 'start' and 'finish' query parameters."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            geometry, total_distance = FuelOptimizationService.get_route(start, finish)
            route_coords = geometry['coordinates']
            
            stops, total_cost, strategy = FuelOptimizationService.optimize_fuel_plan(route_coords, total_distance)
            
            return Response({
                "route": geometry,
                "total_distance_miles": total_distance,
                "fuel_stops": stops,
                "total_fuel_cost": total_cost,
                "strategy_used": strategy
            }, status=status.HTTP_200_OK)
            
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({"error": "An error occurred during route optimization."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
